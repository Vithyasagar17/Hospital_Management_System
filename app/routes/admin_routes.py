from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
from sqlalchemy import or_, func, and_
from app import db
from app.models import Doctor, Patient, Appointment, Specialization, User, AuditLog, Department, Ward, Bed
from app.routes.auth_decorator import role_required
from app.activity import log_activity, notify_user
from app.security import send_verification_email, validate_password
from app.analytics import build_scheduling_analytics, normalize_window
from app.departments import department_rows, department_snapshot
from app.inpatient import (
    ADMIN_SETTABLE_BED_STATUSES, WARD_TYPES,
    department_bed_snapshot, hospital_bed_snapshot, ward_snapshot,
)
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
    total_departments = Department.query.filter_by(is_active=True).count()
    total_patients = Patient.query.filter_by(is_blacklisted=False).count()
    total_appointments = Appointment.query.count()
    bed_snapshot = hospital_bed_snapshot()
    appointments_today = Appointment.query.filter(
        Appointment.date >= datetime.combine(today, datetime.min.time()),
        Appointment.date < datetime.combine(tomorrow, datetime.min.time())
    ).count()

    status_counts = {
        status: Appointment.query.filter_by(status=status).count()
        for status in ['Pending', 'Confirmed', 'Completed', 'Cancelled', 'No Show']
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
        total_departments=total_departments,
        total_patients=total_patients,
        total_appointments=total_appointments,
        bed_snapshot=bed_snapshot,
        appointments_today=appointments_today,
        status_counts=status_counts,
        recent_appointments=recent_appointments,
        recent_audit=recent_audit,
        audit_24h=audit_24h,
        chart_labels=chart_labels,
        chart_values=chart_values,
    )


@admin_bp.route('/scheduling-analytics')
@login_required
@role_required('Admin')
def scheduling_analytics():
    days = normalize_window(request.args.get('days', 30))
    analytics = build_scheduling_analytics(days=days)
    return render_template('admin_scheduling_analytics.html', analytics=analytics, days=days)


@admin_bp.route('/overview')
@login_required
@role_required('Admin')
def admin_overview():
    doctors = Doctor.query.filter_by(is_blacklisted=False).order_by(Doctor.name).all()
    patients = Patient.query.filter_by(is_blacklisted=False).order_by(Patient.name).all()
    appointments = Appointment.query.order_by(Appointment.date.desc()).all()
    return render_template('admin_overview.html', doctors=doctors, patients=patients, appointments=appointments)


@admin_bp.route('/departments', methods=['GET', 'POST'])
@login_required
@role_required('Admin')
def departments():
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        code = request.form.get('code', '').strip().upper()
        description = request.form.get('description', '').strip()
        location = request.form.get('location', '').strip()

        if not name or not code:
            flash('Department name and code are required.', 'warning')
            return redirect(url_for('admin.departments'))
        if len(code) > 20:
            flash('Department code must be 20 characters or fewer.', 'warning')
            return redirect(url_for('admin.departments'))

        duplicate = Department.query.filter(or_(
            func.lower(Department.name) == name.lower(),
            func.lower(Department.code) == code.lower(),
        )).first()
        if duplicate:
            flash('A department with that name or code already exists.', 'warning')
            return redirect(url_for('admin.departments'))

        department = Department(
            name=name, code=code, description=description or None,
            location=location or None, is_active=True,
        )
        db.session.add(department)
        db.session.flush()
        log_activity('department_created', f'Created department {name} ({code}).', 'Department', department.id)
        db.session.commit()
        flash(f'Department {name} created.', 'success')
        return redirect(url_for('admin.department_detail', department_id=department.id))

    status = request.args.get('status', 'active')
    q = request.args.get('q', '').strip()
    rows = department_rows()
    if status in {'active', 'inactive'}:
        want_active = status == 'active'
        rows = [row for row in rows if row['department'].is_active is want_active]
    if q:
        q_lower = q.lower()
        rows = [row for row in rows if q_lower in row['department'].name.lower() or q_lower in row['department'].code.lower()]
    return render_template('admin_departments.html', rows=rows, status=status, q=q)


@admin_bp.route('/department/<int:department_id>', methods=['GET', 'POST'])
@login_required
@role_required('Admin')
def department_detail(department_id):
    department = Department.query.get_or_404(department_id)

    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        code = request.form.get('code', '').strip().upper()
        description = request.form.get('description', '').strip()
        location = request.form.get('location', '').strip()
        head_doctor_id = request.form.get('head_doctor_id', type=int)

        if not name or not code:
            flash('Department name and code are required.', 'warning')
            return redirect(url_for('admin.department_detail', department_id=department.id))
        if len(name) > 120 or len(code) > 20:
            flash('Department name or code is too long.', 'warning')
            return redirect(url_for('admin.department_detail', department_id=department.id))

        duplicate = Department.query.filter(
            Department.id != department.id,
            or_(func.lower(Department.name) == name.lower(), func.lower(Department.code) == code.lower()),
        ).first()
        if duplicate:
            flash('Another department already uses that name or code.', 'warning')
            return redirect(url_for('admin.department_detail', department_id=department.id))

        head = None
        if head_doctor_id:
            head = Doctor.query.filter_by(id=head_doctor_id, department_id=department.id, is_blacklisted=False).first()
            if not head:
                flash('Department head must be an active doctor assigned to this department.', 'warning')
                return redirect(url_for('admin.department_detail', department_id=department.id))

        old_head_id = department.head_doctor_id
        department.name = name
        department.code = code
        department.description = description or None
        department.location = location or None
        department.head_doctor_id = head.id if head else None
        log_activity(
            'department_updated',
            f'Updated department {name} ({code}); head {old_head_id or "none"} → {department.head_doctor_id or "none"}.',
            'Department', department.id,
        )
        if head and old_head_id != head.id:
            notify_user(head.id, 'Department leadership assignment', f'You are now the head of {name}.', 'success', '/doctor/profile')
        db.session.commit()
        flash(f'Department {name} updated.', 'success')
        return redirect(url_for('admin.department_detail', department_id=department.id))

    snapshot = department_snapshot(department.id)
    inpatient_snapshot = department_bed_snapshot(department.id)
    doctors = Doctor.query.filter_by(department_id=department.id).order_by(Doctor.name).all()
    head_candidates = [doctor for doctor in doctors if not doctor.is_blacklisted]
    recent_appointments = Appointment.query.join(Doctor, Appointment.doctor_id == Doctor.id).filter(
        Doctor.department_id == department.id
    ).order_by(Appointment.date.desc()).limit(8).all()
    return render_template(
        'admin_department_detail.html', department=department, snapshot=snapshot, inpatient_snapshot=inpatient_snapshot,
        doctors=doctors, head_candidates=head_candidates, recent_appointments=recent_appointments,
    )


@admin_bp.route('/department/<int:department_id>/toggle', methods=['POST'])
@login_required
@role_required('Admin')
def toggle_department(department_id):
    department = Department.query.get_or_404(department_id)
    if department.is_active:
        assigned = Doctor.query.filter_by(department_id=department.id).count()
        active_wards = Ward.query.filter_by(department_id=department.id, is_active=True).count()
        if assigned:
            flash('Reassign all doctors before deactivating this department.', 'warning')
            return redirect(url_for('admin.department_detail', department_id=department.id))
        if active_wards:
            flash('Deactivate all wards before deactivating this department.', 'warning')
            return redirect(url_for('admin.department_detail', department_id=department.id))
        department.is_active = False
        department.head_doctor_id = None
        action = 'department_deactivated'
        message = f'Department {department.name} deactivated.'
    else:
        department.is_active = True
        action = 'department_reactivated'
        message = f'Department {department.name} reactivated.'
    log_activity(action, message, 'Department', department.id)
    db.session.commit()
    flash(message, 'success')
    return redirect(url_for('admin.departments', status='active' if department.is_active else 'inactive'))


@admin_bp.route('/wards', methods=['GET', 'POST'])
@login_required
@role_required('Admin')
def wards():
    departments = Department.query.filter_by(is_active=True).order_by(Department.name).all()

    if request.method == 'POST':
        department_id = request.form.get('department_id', type=int)
        name = request.form.get('name', '').strip()
        code = request.form.get('code', '').strip().upper()
        ward_type = request.form.get('ward_type', 'General').strip()
        location = request.form.get('location', '').strip()

        department = Department.query.filter_by(id=department_id, is_active=True).first()
        if not department or not name or not code:
            flash('Active department, ward name, and ward code are required.', 'warning')
            return redirect(url_for('admin.wards'))
        if ward_type not in WARD_TYPES:
            flash('Choose a valid ward type.', 'warning')
            return redirect(url_for('admin.wards'))
        if len(name) > 120 or len(code) > 30 or len(location) > 120:
            flash('Ward name, code, or location is too long.', 'warning')
            return redirect(url_for('admin.wards'))

        duplicate = Ward.query.filter(or_(
            func.lower(Ward.code) == code.lower(),
            and_(Ward.department_id == department.id, func.lower(Ward.name) == name.lower()),
        )).first()
        if duplicate:
            flash('That ward code already exists, or this department already has a ward with that name.', 'warning')
            return redirect(url_for('admin.wards'))

        ward = Ward(
            department_id=department.id,
            name=name,
            code=code,
            ward_type=ward_type,
            location=location or None,
            is_active=True,
        )
        db.session.add(ward)
        db.session.flush()
        log_activity('ward_created', f'Created ward {name} ({code}) in {department.name}.', 'Ward', ward.id)
        db.session.commit()
        flash(f'Ward {name} created.', 'success')
        return redirect(url_for('admin.ward_detail', ward_id=ward.id))

    q = request.args.get('q', '').strip()
    status = request.args.get('status', 'active')
    department_id = request.args.get('department_id', type=int)
    query = Ward.query.join(Department, Ward.department_id == Department.id)
    if status in {'active', 'inactive'}:
        query = query.filter(Ward.is_active.is_(status == 'active'))
    if department_id:
        query = query.filter(Ward.department_id == department_id)
    if q:
        query = query.filter(or_(
            Ward.name.ilike(f'%{q}%'), Ward.code.ilike(f'%{q}%'),
            Ward.location.ilike(f'%{q}%'), Department.name.ilike(f'%{q}%'),
        ))
    rows = [ward_snapshot(ward.id) for ward in query.order_by(Department.name, Ward.name).all()]
    all_departments = Department.query.order_by(Department.name).all()
    return render_template(
        'admin_wards.html', rows=rows, departments=departments, all_departments=all_departments,
        ward_types=WARD_TYPES, q=q, status=status, department_id=department_id,
    )


@admin_bp.route('/ward/<int:ward_id>', methods=['GET', 'POST'])
@login_required
@role_required('Admin')
def ward_detail(ward_id):
    ward = Ward.query.get_or_404(ward_id)
    departments = Department.query.order_by(Department.name).all()

    if request.method == 'POST':
        department_id = request.form.get('department_id', type=int)
        name = request.form.get('name', '').strip()
        code = request.form.get('code', '').strip().upper()
        ward_type = request.form.get('ward_type', 'General').strip()
        location = request.form.get('location', '').strip()
        target_department = Department.query.filter_by(id=department_id, is_active=True).first()

        if not target_department or not name or not code:
            flash('Active department, ward name, and ward code are required.', 'warning')
            return redirect(url_for('admin.ward_detail', ward_id=ward.id))
        if ward_type not in WARD_TYPES:
            flash('Choose a valid ward type.', 'warning')
            return redirect(url_for('admin.ward_detail', ward_id=ward.id))

        duplicate = Ward.query.filter(
            Ward.id != ward.id,
            or_(
                func.lower(Ward.code) == code.lower(),
                and_(Ward.department_id == target_department.id, func.lower(Ward.name) == name.lower()),
            ),
        ).first()
        if duplicate:
            flash('Another ward already uses that code, or the target department already has that name.', 'warning')
            return redirect(url_for('admin.ward_detail', ward_id=ward.id))

        if target_department.id != ward.department_id:
            protected_beds = Bed.query.filter(
                Bed.ward_id == ward.id,
                Bed.status.in_(['Reserved', 'Occupied']),
            ).count()
            if protected_beds:
                flash('A ward with reserved or occupied beds cannot be moved to another department.', 'warning')
                return redirect(url_for('admin.ward_detail', ward_id=ward.id))

        old_department_id = ward.department_id
        ward.department_id = target_department.id
        ward.name = name
        ward.code = code
        ward.ward_type = ward_type
        ward.location = location or None
        log_activity(
            'ward_updated',
            f'Updated ward {name} ({code}); department {old_department_id} → {ward.department_id}.',
            'Ward', ward.id,
        )
        db.session.commit()
        flash(f'Ward {name} updated.', 'success')
        return redirect(url_for('admin.ward_detail', ward_id=ward.id))

    snapshot = ward_snapshot(ward.id)
    beds = Bed.query.filter_by(ward_id=ward.id).order_by(Bed.bed_number).all()
    return render_template(
        'admin_ward_detail.html', ward=ward, snapshot=snapshot, beds=beds,
        departments=departments, ward_types=WARD_TYPES,
        bed_statuses=ADMIN_SETTABLE_BED_STATUSES,
    )


@admin_bp.route('/ward/<int:ward_id>/toggle', methods=['POST'])
@login_required
@role_required('Admin')
def toggle_ward(ward_id):
    ward = Ward.query.get_or_404(ward_id)
    if ward.is_active:
        protected_beds = Bed.query.filter(
            Bed.ward_id == ward.id,
            Bed.status.in_(['Reserved', 'Occupied']),
        ).count()
        if protected_beds:
            flash('A ward with reserved or occupied beds cannot be deactivated.', 'warning')
            return redirect(url_for('admin.ward_detail', ward_id=ward.id))
        ward.is_active = False
        action = 'ward_deactivated'
        message = f'Ward {ward.name} deactivated.'
    else:
        if not ward.department or not ward.department.is_active:
            flash('Reactivate the parent department before reactivating this ward.', 'warning')
            return redirect(url_for('admin.ward_detail', ward_id=ward.id))
        ward.is_active = True
        action = 'ward_reactivated'
        message = f'Ward {ward.name} reactivated.'
    log_activity(action, message, 'Ward', ward.id)
    db.session.commit()
    flash(message, 'success')
    return redirect(url_for('admin.ward_detail', ward_id=ward.id))


@admin_bp.route('/ward/<int:ward_id>/beds', methods=['POST'])
@login_required
@role_required('Admin')
def add_bed(ward_id):
    ward = Ward.query.get_or_404(ward_id)
    bed_number = request.form.get('bed_number', '').strip().upper()
    status = request.form.get('status', 'Available').strip()
    notes = request.form.get('notes', '').strip()

    if not ward.is_active:
        flash('Reactivate the ward before adding beds.', 'warning')
        return redirect(url_for('admin.ward_detail', ward_id=ward.id))
    if not bed_number or len(bed_number) > 30:
        flash('Bed number is required and must be 30 characters or fewer.', 'warning')
        return redirect(url_for('admin.ward_detail', ward_id=ward.id))
    if status not in ADMIN_SETTABLE_BED_STATUSES:
        flash('Occupied beds can only be assigned through the admission workflow.', 'warning')
        return redirect(url_for('admin.ward_detail', ward_id=ward.id))
    duplicate = Bed.query.filter(
        Bed.ward_id == ward.id,
        func.lower(Bed.bed_number) == bed_number.lower(),
    ).first()
    if duplicate:
        flash('That bed number already exists in this ward.', 'warning')
        return redirect(url_for('admin.ward_detail', ward_id=ward.id))

    bed = Bed(ward_id=ward.id, bed_number=bed_number, status=status, notes=notes or None)
    db.session.add(bed)
    db.session.flush()
    log_activity('bed_created', f'Created bed {bed_number} in {ward.name}; status {status}.', 'Bed', bed.id)
    db.session.commit()
    flash(f'Bed {bed_number} added to {ward.name}.', 'success')
    return redirect(url_for('admin.ward_detail', ward_id=ward.id))


@admin_bp.route('/bed/<int:bed_id>/update', methods=['POST'])
@login_required
@role_required('Admin')
def update_bed(bed_id):
    bed = Bed.query.get_or_404(bed_id)
    bed_number = request.form.get('bed_number', '').strip().upper()
    status = request.form.get('status', bed.status).strip()
    notes = request.form.get('notes', '').strip()

    if not bed_number or len(bed_number) > 30:
        flash('Bed number is required and must be 30 characters or fewer.', 'warning')
        return redirect(url_for('admin.ward_detail', ward_id=bed.ward_id))
    if bed.status == 'Occupied':
        flash('Occupied beds are controlled by the admission and discharge workflow.', 'warning')
        return redirect(url_for('admin.ward_detail', ward_id=bed.ward_id))
    if status not in ADMIN_SETTABLE_BED_STATUSES:
        flash('Occupied status can only be set by the admission workflow.', 'warning')
        return redirect(url_for('admin.ward_detail', ward_id=bed.ward_id))
    if status == 'Reserved' and not bed.ward.is_active:
        flash('Beds in an inactive ward cannot be reserved.', 'warning')
        return redirect(url_for('admin.ward_detail', ward_id=bed.ward_id))

    duplicate = Bed.query.filter(
        Bed.ward_id == bed.ward_id,
        Bed.id != bed.id,
        func.lower(Bed.bed_number) == bed_number.lower(),
    ).first()
    if duplicate:
        flash('That bed number already exists in this ward.', 'warning')
        return redirect(url_for('admin.ward_detail', ward_id=bed.ward_id))

    old_number, old_status = bed.bed_number, bed.status
    bed.bed_number = bed_number
    bed.status = status
    bed.notes = notes or None
    log_activity(
        'bed_updated',
        f'Updated bed {old_number} → {bed_number} in {bed.ward.name}; status {old_status} → {status}.',
        'Bed', bed.id,
    )
    db.session.commit()
    flash(f'Bed {bed.bed_number} updated.', 'success')
    return redirect(url_for('admin.ward_detail', ward_id=bed.ward_id))


@admin_bp.route('/doctors')
@login_required
@role_required('Admin')
def admin_doctors():
    status = request.args.get('status', 'active')
    q = request.args.get('q', '').strip()
    specialization_id = request.args.get('specialization_id', type=int)
    department_id = request.args.get('department_id', type=int)

    query = Doctor.query
    query = query.filter(Doctor.is_blacklisted.is_(status == 'blacklisted'))
    if q:
        query = query.filter(or_(
            Doctor.name.ilike(f'%{q}%'),
            Doctor.specialization.has(Specialization.name.ilike(f'%{q}%')),
            Doctor.department.has(Department.name.ilike(f'%{q}%')),
        ))
    if specialization_id:
        query = query.filter(Doctor.specialization_id == specialization_id)
    if department_id:
        query = query.filter(Doctor.department_id == department_id)
    doctors = query.order_by(Doctor.name).all()
    specializations = Specialization.query.order_by(Specialization.name).all()
    departments = Department.query.order_by(Department.name).all()
    return render_template('admin_doctors.html', doctors=doctors, status=status, q=q,
                           specialization_id=specialization_id, specializations=specializations,
                           department_id=department_id, departments=departments)


@admin_bp.route('/doctor/add', methods=['GET', 'POST'])
@login_required
@role_required('Admin')
def add_doctor():
    specializations = Specialization.query.order_by(Specialization.name).all()
    departments = Department.query.filter_by(is_active=True).order_by(Department.name).all()

    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')
        name = request.form.get('name', '').strip()
        specialization_id = request.form.get('specialization_id')
        department_id = request.form.get('department_id')

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
        try:
            dept_id = int(department_id) if department_id else None
        except ValueError:
            dept_id = None
        if dept_id and not Department.query.filter_by(id=dept_id, is_active=True).first():
            flash('Choose an active department.', 'warning')
            return redirect(url_for('admin.add_doctor'))

        user = User(username=username, email=email, email_verified=False, role='Doctor', session_version=1)
        user.set_password(password)
        db.session.add(user)
        db.session.flush()
        doctor = Doctor(id=user.id, name=name, specialization_id=spec_id, department_id=dept_id)
        db.session.add(doctor)
        log_activity('doctor_created', f'Added doctor {name} ({username}).', 'Doctor', user.id)
        notify_user(user.id, 'Doctor account created', 'Your doctor workspace is ready. Complete your profile and availability.', 'success', '/doctor/dashboard')
        db.session.commit()
        send_verification_email(user)

        flash(f'Doctor {name} added. A verification link was sent to {email}.', 'success')
        return redirect(url_for('admin.admin_doctors'))

    return render_template('admin_add_doctor.html', specializations=specializations, departments=departments)


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
    if status in {'Pending', 'Confirmed', 'Completed', 'Cancelled', 'No Show'}:
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
        if status in {'Pending', 'Confirmed', 'Completed', 'Cancelled', 'No Show'}:
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
    departments = Department.query.order_by(Department.name).all()

    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        specialization_id = request.form.get('specialization_id')
        department_id = request.form.get('department_id')
        if not name:
            flash('Doctor name is required.', 'warning')
            return redirect(url_for('admin.edit_doctor', doctor_id=doctor_id))
        doctor.name = name
        try:
            doctor.specialization_id = int(specialization_id) if specialization_id else None
        except ValueError:
            doctor.specialization_id = None
        try:
            new_department_id = int(department_id) if department_id else None
        except ValueError:
            new_department_id = None
        if new_department_id and not Department.query.filter_by(id=new_department_id, is_active=True).first():
            flash('Choose an active department.', 'warning')
            return redirect(url_for('admin.edit_doctor', doctor_id=doctor_id))
        old_department_id = doctor.department_id
        if old_department_id != new_department_id:
            for led_department in Department.query.filter_by(head_doctor_id=doctor.id).all():
                led_department.head_doctor_id = None
            doctor.department_id = new_department_id
            notify_user(doctor.id, 'Department assignment updated', 'Your hospital department assignment has changed. Open your profile for details.', 'info', '/doctor/profile')
        log_activity('doctor_updated', f'Updated doctor profile for {name}.', 'Doctor', doctor.id)
        db.session.commit()
        flash(f'Doctor {name} updated successfully.', 'success')
        return redirect(url_for('admin.admin_doctors'))
    return render_template('admin_edit_doctor.html', doctor=doctor, specializations=specializations, departments=departments)


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
    for department in Department.query.filter_by(head_doctor_id=doctor.id).all():
        department.head_doctor_id = None
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
