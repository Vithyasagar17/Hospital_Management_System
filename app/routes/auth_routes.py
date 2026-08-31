from datetime import datetime, timedelta

from flask import Blueprint, abort, current_app, flash, redirect, render_template, request, session, url_for
from flask_login import current_user, login_required, login_user, logout_user
from sqlalchemy import or_

from app import db
from app.activity import log_activity, notify_role
from app.models import Doctor, LoginAttempt, Notification, Patient, Specialization, User
from app.security import (
    client_ip, ip_fingerprint, is_safe_next_url, login_window_start, make_token,
    read_token, send_password_reset_email, send_verification_email, validate_password,
)


auth_bp = Blueprint('auth', __name__)


def _account_blacklisted(user):
    if user.role == 'Doctor':
        profile = db.session.get(Doctor, user.id)
        return bool(profile and profile.is_blacklisted)
    if user.role == 'Patient':
        profile = db.session.get(Patient, user.id)
        return bool(profile and profile.is_blacklisted)
    return False


def _record_login_attempt(username, success):
    uname = (username or '').lower()[:100]
    LoginAttempt.query.filter(LoginAttempt.attempted_at < datetime.utcnow() - timedelta(days=2)).delete(synchronize_session=False)
    if success:
        LoginAttempt.query.filter_by(username=uname, success=False).delete(synchronize_session=False)
    db.session.add(LoginAttempt(
        username=uname,
        ip_fingerprint=ip_fingerprint(client_ip()),
        success=success,
    ))


def _rate_limited(username):
    since = login_window_start()
    uname = (username or '').lower()[:100]
    ip_key = ip_fingerprint(client_ip())
    per_user = LoginAttempt.query.filter_by(username=uname, success=False).filter(LoginAttempt.attempted_at >= since).count()
    per_ip = LoginAttempt.query.filter_by(ip_fingerprint=ip_key, success=False).filter(LoginAttempt.attempted_at >= since).count()
    return (
        per_user >= int(current_app.config.get('LOGIN_MAX_FAILURES_PER_USER', 5)) or
        per_ip >= int(current_app.config.get('LOGIN_MAX_FAILURES_PER_IP', 20))
    )


@auth_bp.route('/')
def index():
    return redirect(url_for('auth.login'))


@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for(f'{current_user.role.lower()}.{current_user.role.lower()}_dashboard'))

    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        user = User.query.filter_by(username=username).first()

        if _rate_limited(username):
            flash(
                'Too many sign-in attempts. Please wait about 15 minutes before trying again.',
                'danger'
            )
            return render_template('login.html'), 429

        if user and user.locked_until and user.locked_until > datetime.utcnow():
            flash('Too many failed attempts. This account is temporarily locked.', 'danger')
            return render_template('login.html'), 429

        valid = bool(user and user.check_password(password))
        if not valid:
            _record_login_attempt(username, False)
            if user:
                user.failed_login_count = (user.failed_login_count or 0) + 1
                if user.failed_login_count >= 5:
                    user.locked_until = datetime.utcnow() + timedelta(minutes=int(current_app.config.get('LOGIN_LOCK_MINUTES', 15)))
                    user.failed_login_count = 0
                    log_activity('account_temporarily_locked', f'Account {user.username} locked after repeated failed sign-ins.', 'User', user.id, actor=user)
            db.session.commit()
            flash('Invalid username or password.', 'danger')
            return render_template('login.html')

        if _account_blacklisted(user):
            flash('This account is currently disabled. Contact an administrator.', 'danger')
            return render_template('login.html'), 403

        if user.email and not user.email_verified:
            flash('Verify your email address before signing in. You can resend the verification email below.', 'warning')
            return redirect(url_for('auth.resend_verification', username=user.username))

        _record_login_attempt(username, True)
        user.failed_login_count = 0
        user.locked_until = None
        user.last_login_at = datetime.utcnow()
        session.clear()
        login_user(user)
        session['session_version'] = user.session_version
        session.permanent = True
        log_activity('login', f'{user.username} signed in.', 'User', user.id, actor=user)
        db.session.commit()

        next_url = request.args.get('next')
        if is_safe_next_url(next_url):
            return redirect(next_url)
        if user.role == 'Admin':
            return redirect(url_for('admin.admin_dashboard'))
        if user.role == 'Doctor':
            return redirect(url_for('doctor.doctor_dashboard'))
        return redirect(url_for('patient.patient_dashboard'))

    return render_template('login.html')


@auth_bp.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')
        role = request.form.get('role', 'Patient')
        name = request.form.get('name', '').strip()
        contact = request.form.get('contact', '').strip()
        address = request.form.get('address', '').strip()

        password_ok, password_error = validate_password(password)
        if role not in {'Patient', 'Doctor'}:
            flash('Invalid registration role.', 'warning')
        elif not username or not email or not password:
            flash('Username, email, and password are required.', 'warning')
        elif '@' not in email or len(email) > 255:
            flash('Enter a valid email address.', 'warning')
        elif not password_ok:
            flash(password_error, 'warning')
        elif not name:
            flash('Full name is required.', 'warning')
        elif User.query.filter(or_(User.username == username, User.email == email)).first():
            flash('That username or email is already registered.', 'warning')
        else:
            user = User(username=username, email=email, email_verified=False, role=role, session_version=1)
            user.set_password(password)
            db.session.add(user)
            db.session.flush()
            if role == 'Patient':
                db.session.add(Patient(id=user.id, name=name, contact=contact or None, address=address or None))
            else:
                spec_id = request.form.get('specialization')
                try:
                    spec_id = int(spec_id) if spec_id else None
                except ValueError:
                    spec_id = None
                db.session.add(Doctor(id=user.id, name=name, specialization_id=spec_id))
            log_activity('register', f'New {role.lower()} account created: {username}.', 'User', user.id, actor=user)
            notify_role('Admin', 'New account registered', f'{name or username} registered as {role}.', 'info', '/admin/search')
            db.session.commit()
            sent = send_verification_email(user)
            flash('Account created. Verify your email before signing in.' if sent else 'Account created, but the verification message could not be sent. Contact an administrator.', 'success' if sent else 'warning')
            return redirect(url_for('auth.login'))

    specializations = Specialization.query.order_by(Specialization.name).all()
    return render_template('register.html', specializations=specializations)


@auth_bp.route('/verify-email/<token>')
def verify_email(token):
    payload = read_token(token, 'verify-email', 24 * 60 * 60)
    if not payload:
        flash('That verification link is invalid or has expired.', 'danger')
        return redirect(url_for('auth.login'))
    user = db.session.get(User, payload.get('uid'))
    if not user or user.email != payload.get('email'):
        abort(400)
    user.email_verified = True
    log_activity('email_verified', f'{user.username} verified their email address.', 'User', user.id, actor=user)
    db.session.commit()
    flash('Email verified. You can now sign in.', 'success')
    return redirect(url_for('auth.login'))


@auth_bp.route('/verify-email/resend', methods=['GET', 'POST'])
def resend_verification():
    username = request.values.get('username', '').strip()
    if request.method == 'POST':
        identifier = request.form.get('identifier', '').strip().lower()
        user = User.query.filter(or_(User.username == identifier, User.email == identifier)).first()
        if user and user.email and not user.email_verified:
            send_verification_email(user)
        flash('If that account needs verification, a new message has been sent.', 'info')
        return redirect(url_for('auth.login'))
    return render_template('resend_verification.html', username=username)


@auth_bp.route('/forgot-password', methods=['GET', 'POST'])
def forgot_password():
    if request.method == 'POST':
        identifier = request.form.get('identifier', '').strip().lower()
        user = User.query.filter(or_(User.username == identifier, User.email == identifier)).first()
        if user and user.email and user.email_verified:
            send_password_reset_email(user)
            log_activity('password_reset_requested', f'Password reset requested for {user.username}.', 'User', user.id, actor=user)
            db.session.commit()
        flash('If a verified account matches that information, a reset link has been sent.', 'info')
        return redirect(url_for('auth.login'))
    return render_template('forgot_password.html')


@auth_bp.route('/reset-password/<token>', methods=['GET', 'POST'])
def reset_password(token):
    payload = read_token(token, 'reset-password', 30 * 60)
    if not payload:
        flash('That password reset link is invalid or has expired.', 'danger')
        return redirect(url_for('auth.forgot_password'))
    user = db.session.get(User, payload.get('uid'))
    if not user or user.email != payload.get('email') or user.session_version != payload.get('sv'):
        abort(400)
    if request.method == 'POST':
        password = request.form.get('password', '')
        confirm = request.form.get('confirm_password', '')
        valid, message = validate_password(password)
        if password != confirm:
            flash('The passwords do not match.', 'warning')
        elif not valid:
            flash(message, 'warning')
        else:
            user.set_password(password)
            user.session_version += 1
            user.failed_login_count = 0
            user.locked_until = None
            log_activity('password_reset_completed', f'Password reset completed for {user.username}.', 'User', user.id, actor=user)
            db.session.commit()
            flash('Password reset successfully. Sign in with your new password.', 'success')
            return redirect(url_for('auth.login'))
    return render_template('reset_password.html')


@auth_bp.route('/account/security')
@login_required
def security_settings():
    return render_template('security_settings.html')


@auth_bp.route('/account/email', methods=['POST'])
@login_required
def update_email():
    email = request.form.get('email', '').strip().lower()
    current_password = request.form.get('current_password', '')
    if not current_user.check_password(current_password):
        flash('Your current password is required to change the account email.', 'danger')
        return redirect(url_for('auth.security_settings'))
    if not email or '@' not in email or len(email) > 255:
        flash('Enter a valid email address.', 'warning')
        return redirect(url_for('auth.security_settings'))
    owner = User.query.filter(User.email == email, User.id != current_user.id).first()
    if owner:
        flash('That email address is already used by another account.', 'warning')
        return redirect(url_for('auth.security_settings'))
    if current_user.email == email and current_user.email_verified:
        flash('That email address is already verified on your account.', 'info')
        return redirect(url_for('auth.security_settings'))
    current_user.email = email
    current_user.email_verified = False
    log_activity('account_email_changed', f'{current_user.username} changed the account email and verification is pending.', 'User', current_user.id)
    db.session.commit()
    sent = send_verification_email(current_user)
    flash('Email updated. A verification link has been sent.' if sent else 'Email updated, but the verification message could not be sent.', 'success' if sent else 'warning')
    return redirect(url_for('auth.security_settings'))


@auth_bp.route('/account/change-password', methods=['GET', 'POST'])
@login_required
def change_password():
    if request.method == 'POST':
        current_password = request.form.get('current_password', '')
        new_password = request.form.get('new_password', '')
        confirm = request.form.get('confirm_password', '')
        valid, message = validate_password(new_password)
        if not current_user.check_password(current_password):
            flash('Your current password is incorrect.', 'danger')
        elif new_password != confirm:
            flash('The new passwords do not match.', 'warning')
        elif not valid:
            flash(message, 'warning')
        else:
            current_user.set_password(new_password)
            current_user.session_version += 1
            new_version = current_user.session_version
            log_activity('password_changed', f'{current_user.username} changed their password.', 'User', current_user.id)
            db.session.commit()
            session['session_version'] = new_version
            flash('Password changed. Other existing sessions have been invalidated.', 'success')
            return redirect(url_for('auth.security_settings'))
    return render_template('change_password.html')


@auth_bp.route('/notifications')
@login_required
def notifications():
    state = request.args.get('state', 'all')
    query = Notification.query.filter_by(user_id=current_user.id)
    if state == 'unread':
        query = query.filter_by(is_read=False)
    elif state == 'read':
        query = query.filter_by(is_read=True)
    return render_template('notifications.html', notifications=query.order_by(Notification.created_at.desc()).all(), state=state)


@auth_bp.route('/notifications/<int:notification_id>/open')
@login_required
def open_notification(notification_id):
    note = Notification.query.get_or_404(notification_id)
    if note.user_id != current_user.id:
        abort(403)
    if not note.is_read:
        note.is_read = True
        db.session.commit()
    if note.target_url and note.target_url.startswith('/') and not note.target_url.startswith('//'):
        return redirect(note.target_url)
    return redirect(url_for('auth.notifications'))


@auth_bp.route('/notifications/<int:notification_id>/read', methods=['POST'])
@login_required
def mark_notification_read(notification_id):
    note = Notification.query.get_or_404(notification_id)
    if note.user_id != current_user.id:
        abort(403)
    note.is_read = True
    db.session.commit()
    return redirect(request.referrer or url_for('auth.notifications'))


@auth_bp.route('/notifications/read-all', methods=['POST'])
@login_required
def mark_all_notifications_read():
    Notification.query.filter_by(user_id=current_user.id, is_read=False).update({'is_read': True})
    db.session.commit()
    flash('All notifications marked as read.', 'success')
    return redirect(request.referrer or url_for('auth.notifications'))


@auth_bp.route('/logout', methods=['POST'])
@login_required
def logout():
    log_activity('logout', f'{current_user.username} signed out.', 'User', current_user.id)
    db.session.commit()
    logout_user()
    session.clear()
    return redirect(url_for('auth.login'))
