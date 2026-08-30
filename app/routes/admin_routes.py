from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
from sqlalchemy import or_
from app import db
from app.models import Doctor, Patient, Appointment, Specialization, User, AuditLog
from app.routes.auth_decorator import role_required
from app.activity import log_activity, notify_user
from app.security import send_verification_email, validate_password
from datetime import datetime, timedelta

admin_bp = Blueprint('admin', __name__, url_prefix='/admin')


def _parse_date(value):
    if not value:
        return None
    try:
        return datetime.strptime(value, '%Y-%m-%d').date()
    except ValueError:
        return None


@admin_bp.route('/dashboard')
@login_required
@role_required('Admin')
def admin_dashboard():
    today = datetime.now().date()
    tomorrow = today + timedelta(days=1)
    week_start = today - timedelta(days=6)

    total_doctors = Doctor.query.filter_by(is_blacklisted=False).count()
    total_patients = Patient.query.filter_by(is_blacklisted=False).count()
    total_appointments = Appointment.query.count()
    appointments_today = Appointment.query.filter(
        Appointment.date >= datetime.combine(today, datetime.min.time()),
        Appointment.date < datetime.combine(tomorrow, datetime.min.time())
    ).count()

    status_counts = {
        status: Appointment.query.filter_by(status=status).count()
        for status in ['Pending', 'Confirmed', 'Completed', 'Cancelled']
    }

    recent_appointments = Appointment.query.order_by(Appointment.created_at.desc()).limit(6).all()
    recent_audit = AuditLog.query.order_by(AuditLog.created_at.desc()).limit(6).all()
    audit_24h = AuditLog.query.filter(AuditLog.created_at >= datetime.utcnow() - timedelta(hours=24)).count()
    week_appointments = Appointment.query.filter(
        Appointment.date >= datetime.combine(week_start, datetime.min.time()),
        Appointment.date < datetime.combine(tomorrow, datetime.min.time())
    ).all()

    chart_labels = []
    chart_values = []
    for offset in range(7):
        day = week_start + timedelta(days=offset)
        chart_labels.append(day.strftime('%a'))
        chart_values.append(sum(1 for appt in week_appointments if appt.date and appt.date.date() == day))

    return render_template(
        'admin_dashboard.html',
        total_doctors=total_doctors,
        total_patients=total_patients,
        total_appointments=total_appointments,
        appointments_today=appointments_today,
        status_counts=status_counts,
        recent_appointments=recent_appointments,
        recent_audit=recent_audit,
        audit_24h=audit_24h,
        chart_labels=chart_labels,
        chart_values=chart_values,
    )


@admin_bp.route('/overview')
@login_required
@role_required('Admin')
def admin_overview():
    doctors = Doctor.query.filter_by(is_blacklisted=False).order_by(Doctor.name).all()
    patients = Patient.query.filter_by(is_blacklisted=False).order_by(Patient.name).all()
    appointments = Appointment.query.order_by(Appointment.date.desc()).all()
    return render_template('admin_overview.html', doctors=doctors, patients=patients, appointments=appointments)


@admin_bp.route('/doctors')
@login_required
@role_required('Admin')
def admin_doctors():
    status = request.args.get('status', 'active')
    q = request.args.get('q', '').strip()
    specialization_id = request.args.get('specialization_id', type=int)

    query = Doctor.query
    query = query.filter(Doctor.is_blacklisted.is_(status == 'blacklisted'))
    if q:
        query = query.filter(Doctor.name.ilike(f'%{q}%'))
    if specialization_id:
        query = query.filter(Doctor.specialization_id == specialization_id)
    doctors = query.order_by(Doctor.name).all()
    specializations = Specialization.query.order_by(Specialization.name).all()
    return render_template('admin_doctors.html', doctors=doctors, status=status, q=q,
                           specialization_id=specialization_id, specializations=specializations)


@admin_bp.route('/doctor/add', methods=['GET', 'POST'])
@login_required
@role_required('Admin')
def add_doctor():
    specializations = Specialization.query.order_by(Specialization.name).all()

    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')
        name = request.form.get('name', '').strip()
        specialization_id = request.form.get('specialization_id')

        password_ok, password_error = validate_password(password)
        if not username or not email or not password or not name:
            flash('Username, email, password, and name are required.', 'warning')
            return redirect(url_for('admin.add_doctor'))
        if not password_ok:
            flash(password_error, 'warning')
            return redirect(url_for('admin.add_doctor'))
        if User.query.filter(or_(User.username == username, User.email == email)).first():
            flash('Username or email already exists.', 'warning')
            return redirect(url_for('admin.add_doctor'))

        try:
            spec_id = int(specialization_id) if specialization_id else None
        except ValueError:
            spec_id = None

        user = User(username=username, email=email, email_verified=False, role='Doctor', session_version=1)
        user.set_password(password)
        db.session.add(user)
        db.session.flush()
        doctor = Doctor(id=user.id, name=name, specialization_id=spec_id)
        db.session.add(doctor)
        log_activity('doctor_created', f'Added doctor {name} ({username}).', 'Doctor', user.id)
        notify_user(user.id, 'Doctor account created', 'Your doctor workspace is ready. Complete your profile and availability.', 'success', '/doctor/dashboard')
        db.session.commit()
        send_verification_email(user)

        flash(f'Doctor {name} added. A verification link was sent to {email}.', 'success')
        return redirect(url_for('admin.admin_doctors'))

    return render_template('admin_add_doctor.html', specializations=specializations)


@admin_bp.route('/patients')
@login_required
@role_required('Admin')
def admin_patients():
    status = request.args.get('status', 'active')
    q = request.args.get('q', '').strip()
    min_age = request.args.get('min_age', type=int)
    max_age = request.args.get('max_age', type=int)

    query = Patient.query.filter(Patient.is_blacklisted.is_(status == 'blacklisted'))
    if q:
        query = query.filter(or_(
            Patient.name.ilike(f'%{q}%'),
            Patient.contact.ilike(f'%{q}%'),
            Patient.address.ilike(f'%{q}%')
        ))
    if min_age is not None:
        query = query.filter(Patient.age >= min_age)
    if max_age is not None:
        query = query.filter(Patient.age <= max_age)
    patients = query.order_by(Patient.name).all()
    return render_template('admin_patients.html', patients=patients, status=status, q=q,
                           min_age=min_age, max_age=max_age)


@admin_bp.route('/appointments')
@login_required
@role_required('Admin')
def admin_appointments():
    status = request.args.get('status', 'all')
    q = request.args.get('q', '').strip()
    date_from_raw = request.args.get('date_from', '')
    date_to_raw = request.args.get('date_to', '')
    date_from = _parse_date(date_from_raw)
    date_to = _parse_date(date_to_raw)

    query = Appointment.query.join(Doctor, Appointment.doctor_id == Doctor.id).join(Patient, Appointment.patient_id == Patient.id)
    if status in {'Pending', 'Confirmed', 'Completed', 'Cancelled'}:
        query = query.filter(Appointment.status == status)
    if q:
        query = query.filter(or_(
            Doctor.name.ilike(f'%{q}%'),
            Patient.name.ilike(f'%{q}%'),
            Appointment.reason.ilike(f'%{q}%')
        ))
    if date_from:
        query = query.filter(Appointment.date >= datetime.combine(date_from, datetime.min.time()))
    if date_to:
        query = query.filter(Appointment.date < datetime.combine(date_to + timedelta(days=1), datetime.min.time()))
    appointments = query.order_by(Appointment.date.desc()).all()
    return render_template('admin_appointments.html', appointments=appointments, status=status, q=q,
                           date_from=date_from_raw, date_to=date_to_raw)


@admin_bp.route('/search')
@login_required
@role_required('Admin')
def search():
    q = request.args.get('q', '').strip()
    search_type = request.args.get('type', 'all')
    status = request.args.get('status', 'all')
    specialization_id = request.args.get('specialization_id', type=int)
    date_from_raw = request.args.get('date_from', '')
    date_to_raw = request.args.get('date_to', '')
    date_from = _parse_date(date_from_raw)
    date_to = _parse_date(date_to_raw)

    results = {'doctors': [], 'patients': [], 'appointments': []}

    if search_type in ['all', 'doctor']:
        dq = Doctor.query
        if q:
            dq = dq.filter(or_(Doctor.name.ilike(f'%{q}%'), Doctor.specialization.has(Specialization.name.ilike(f'%{q}%'))))
        if specialization_id:
            dq = dq.filter(Doctor.specialization_id == specialization_id)
        if status == 'active':
            dq = dq.filter(Doctor.is_blacklisted.is_(False))
        elif status == 'blacklisted':
            dq = dq.filter(Doctor.is_blacklisted.is_(True))
        results['doctors'] = dq.order_by(Doctor.name).limit(100).all()

    if search_type in ['all', 'patient']:
        pq = Patient.query
        if q:
            clauses = [Patient.name.ilike(f'%{q}%'), Patient.contact.ilike(f'%{q}%'), Patient.address.ilike(f'%{q}%')]
            if q.isdigit():
                clauses.append(Patient.id == int(q))
            pq = pq.filter(or_(*clauses))
        if status == 'active':
            pq = pq.filter(Patient.is_blacklisted.is_(False))
        elif status == 'blacklisted':
            pq = pq.filter(Patient.is_blacklisted.is_(True))
        results['patients'] = pq.order_by(Patient.name).limit(100).all()

    if search_type in ['all', 'appointment']:
        aq = Appointment.query.join(Doctor, Appointment.doctor_id == Doctor.id).join(Patient, Appointment.patient_id == Patient.id)
        if q:
            aq = aq.filter(or_(Doctor.name.ilike(f'%{q}%'), Patient.name.ilike(f'%{q}%'), Appointment.reason.ilike(f'%{q}%')))
        if status in {'Pending', 'Confirmed', 'Completed', 'Cancelled'}:
            aq = aq.filter(Appointment.status == status)
        if date_from:
            aq = aq.filter(Appointment.date >= datetime.combine(date_from, datetime.min.time()))
        if date_to:
            aq = aq.filter(Appointment.date < datetime.combine(date_to + timedelta(days=1), datetime.min.time()))
        results['appointments'] = aq.order_by(Appointment.date.desc()).limit(100).all()

    specializations = Specialization.query.order_by(Specialization.name).all()
    filters_active = bool(q or search_type != 'all' or status != 'all' or specialization_id or date_from_raw or date_to_raw)
    return render_template('admin_search.html', results=results, query=q, search_type=search_type,
                           status=status, specialization_id=specialization_id,
                           date_from=date_from_raw, date_to=date_to_raw,
                           specializations=specializations, filters_active=filters_active)


@admin_bp.route('/audit-logs')
@login_required
@role_required('Admin')
def audit_logs():
    q = request.args.get('q', '').strip()
    role = request.args.get('role', 'all')
    action = request.args.get('action', 'all')
    date_from_raw = request.args.get('date_from', '')
    date_to_raw = request.args.get('date_to', '')
    date_from = _parse_date(date_from_raw)
    date_to = _parse_date(date_to_raw)

    query = AuditLog.query
    if q:
        query = query.filter(or_(
            AuditLog.actor_username.ilike(f'%{q}%'),
            AuditLog.description.ilike(f'%{q}%'),
            AuditLog.entity_type.ilike(f'%{q}%')
        ))
    if role in {'Admin', 'Doctor', 'Patient', 'System'}:
        query = query.filter(AuditLog.actor_role == role)
    if action != 'all':
        query = query.filter(AuditLog.action == action)
    if date_from:
        query = query.filter(AuditLog.created_at >= datetime.combine(date_from, datetime.min.time()))
    if date_to:
        query = query.filter(AuditLog.created_at < datetime.combine(date_to + timedelta(days=1), datetime.min.time()))

    logs = query.order_by(AuditLog.created_at.desc()).limit(250).all()
    actions = [row[0] for row in db.session.query(AuditLog.action).distinct().order_by(AuditLog.action).all()]
    return render_template('admin_audit_logs.html', logs=logs, q=q, role=role, action=action,
                           date_from=date_from_raw, date_to=date_to_raw, actions=actions)


@admin_bp.route('/doctor/<int:doctor_id>/edit', methods=['GET', 'POST'])
@login_required
@role_required('Admin')
def edit_doctor(doctor_id):
    doctor = Doctor.query.get_or_404(doctor_id)
    specializations = Specialization.query.order_by(Specialization.name).all()

    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        specialization_id = request.form.get('specialization_id')
        if not name:
            flash('Doctor name is required.', 'warning')
            return redirect(url_for('admin.edit_doctor', doctor_id=doctor_id))
        doctor.name = name
        try:
            doctor.specialization_id = int(specialization_id) if specialization_id else None
        except ValueError:
            doctor.specialization_id = None
        log_activity('doctor_updated', f'Updated doctor profile for {name}.', 'Doctor', doctor.id)
        db.session.commit()
        flash(f'Doctor {name} updated successfully.', 'success')
        return redirect(url_for('admin.admin_doctors'))
    return render_template('admin_edit_doctor.html', doctor=doctor, specializations=specializations)


@admin_bp.route('/patient/<int:patient_id>/edit', methods=['GET', 'POST'])
@login_required
@role_required('Admin')
def edit_patient(patient_id):
    patient = Patient.query.get_or_404(patient_id)
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        contact = request.form.get('contact', '').strip()
        address = request.form.get('address', '').strip()
        age = request.form.get('age')
        gender = request.form.get('gender')
        height = request.form.get('height')
        weight = request.form.get('weight')
        if not name:
            flash('Patient name is required.', 'warning')
            return redirect(url_for('admin.edit_patient', patient_id=patient_id))
        patient.name = name
        patient.contact = contact or None
        patient.address = address or None
        try: patient.age = int(age) if age else None
        except ValueError: patient.age = None
        patient.gender = gender or None
        try: patient.height = float(height) if height else None
        except ValueError: patient.height = None
        try: patient.weight = float(weight) if weight else None
        except ValueError: patient.weight = None
        log_activity('patient_updated', f'Updated patient profile for {name}.', 'Patient', patient.id)
        db.session.commit()
        flash(f'Patient {name} updated successfully.', 'success')
        return redirect(url_for('admin.admin_patients'))
    return render_template('admin_edit_patient.html', patient=patient)


@admin_bp.route('/doctor/<int:doctor_id>/blacklist', methods=['POST'])
@login_required
@role_required('Admin')
def blacklist_doctor(doctor_id):
    doctor = Doctor.query.get_or_404(doctor_id)
    doctor.is_blacklisted = True
    log_activity('doctor_blacklisted', f'Blacklisted doctor {doctor.name}.', 'Doctor', doctor.id)
    notify_user(doctor.id, 'Account access changed', 'Your doctor account has been blacklisted by an administrator.', 'warning', '/doctor/dashboard')
    db.session.commit()
    flash(f'Doctor {doctor.name} has been blacklisted.', 'success')
    return redirect(url_for('admin.admin_doctors'))


@admin_bp.route('/patient/<int:patient_id>/blacklist', methods=['POST'])
@login_required
@role_required('Admin')
def blacklist_patient(patient_id):
    patient = Patient.query.get_or_404(patient_id)
    patient.is_blacklisted = True
    log_activity('patient_blacklisted', f'Blacklisted patient {patient.name}.', 'Patient', patient.id)
    notify_user(patient.id, 'Account access changed', 'Your patient account has been blacklisted by an administrator.', 'warning', '/patient/dashboard')
    db.session.commit()
    flash(f'Patient {patient.name} has been blacklisted.', 'success')
    return redirect(url_for('admin.admin_patients'))


@admin_bp.route('/doctor/<int:doctor_id>/unblacklist', methods=['POST'])
@login_required
@role_required('Admin')
def unblacklist_doctor(doctor_id):
    doctor = Doctor.query.get_or_404(doctor_id)
    doctor.is_blacklisted = False
    log_activity('doctor_restored', f'Restored doctor {doctor.name}.', 'Doctor', doctor.id)
    notify_user(doctor.id, 'Account restored', 'Your doctor account has been restored by an administrator.', 'success', '/doctor/dashboard')
    db.session.commit()
    flash(f'Doctor {doctor.name} has been unblacklisted.', 'success')
    return redirect(url_for('admin.admin_doctors'))


@admin_bp.route('/patient/<int:patient_id>/unblacklist', methods=['POST'])
@login_required
@role_required('Admin')
def unblacklist_patient(patient_id):
    patient = Patient.query.get_or_404(patient_id)
    patient.is_blacklisted = False
    log_activity('patient_restored', f'Restored patient {patient.name}.', 'Patient', patient.id)
    notify_user(patient.id, 'Account restored', 'Your patient account has been restored by an administrator.', 'success', '/patient/dashboard')
    db.session.commit()
    flash(f'Patient {patient.name} has been unblacklisted.', 'success')
    return redirect(url_for('admin.admin_patients'))
