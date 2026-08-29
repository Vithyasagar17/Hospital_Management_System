from flask import Blueprint, render_template, redirect, url_for, flash, request, abort
from flask_login import login_user, logout_user, login_required, current_user
from app import db
from app.models import User, Patient, Doctor, Specialization, Notification
from app.activity import log_activity, notify_role

auth_bp = Blueprint('auth', __name__)


@auth_bp.route('/')
def index():
    return redirect(url_for('auth.login'))


@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        user = User.query.filter_by(username=username).first()
        if user and user.check_password(password):
            login_user(user)
            log_activity('login', f'{user.username} signed in.', 'User', user.id, actor=user)
            db.session.commit()
            if user.role == 'Admin':
                return redirect(url_for('admin.admin_dashboard'))
            elif user.role == 'Doctor':
                return redirect(url_for('doctor.doctor_dashboard'))
            elif user.role == 'Patient':
                return redirect(url_for('patient.patient_dashboard'))
        else:
            flash('Invalid username or password', 'danger')
    return render_template('login.html')


@auth_bp.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        role = request.form.get('role', 'Patient')

        name = request.form.get('name', '').strip()
        contact = request.form.get('contact', '').strip()
        address = request.form.get('address', '').strip()

        if not username or not password:
            flash('Username and password are required.', 'warning')
        elif role in ('Patient', 'Doctor') and not name:
            flash('Full name is required for Doctors and Patients.', 'warning')
        elif User.query.filter_by(username=username).first():
            flash('Username already exists', 'warning')
        else:
            user = User(username=username, role=role)
            user.set_password(password)
            db.session.add(user)
            db.session.flush()

            if role == 'Patient':
                patient = Patient(id=user.id, name=name or None, contact=contact or None, address=address or None)
                db.session.add(patient)
            elif role == 'Doctor':
                spec_id = request.form.get('specialization')
                try:
                    spec_id = int(spec_id) if spec_id else None
                except ValueError:
                    spec_id = None
                doctor = Doctor(id=user.id, name=name, specialization_id=spec_id)
                db.session.add(doctor)

            log_activity('register', f'New {role.lower()} account created: {username}.', 'User', user.id, actor=user)
            notify_role('Admin', 'New account registered', f'{name or username} registered as {role}.', 'info', '/admin/search')
            db.session.commit()

            if role == 'Patient':
                login_user(user)
                return redirect(url_for('patient.patient_profile'))
            return redirect(url_for('auth.login'))

    specializations = Specialization.query.order_by(Specialization.name).all()
    return render_template('register.html', specializations=specializations)


@auth_bp.route('/notifications')
@login_required
def notifications():
    state = request.args.get('state', 'all')
    query = Notification.query.filter_by(user_id=current_user.id)
    if state == 'unread':
        query = query.filter_by(is_read=False)
    elif state == 'read':
        query = query.filter_by(is_read=True)
    items = query.order_by(Notification.created_at.desc()).all()
    return render_template('notifications.html', notifications=items, state=state)


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


@auth_bp.route('/logout')
@login_required
def logout():
    log_activity('logout', f'{current_user.username} signed out.', 'User', current_user.id)
    db.session.commit()
    logout_user()
    return redirect(url_for('auth.login'))
