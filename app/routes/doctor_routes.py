from flask import Blueprint, render_template, abort, request, redirect, url_for, flash
from flask_login import login_required, current_user
from app.routes.auth_decorator import role_required
from app.models import Doctor, Patient, Appointment, Prescription, PrescriptionItem, DoctorAvailability, AppointmentReminder
from app import db
from sqlalchemy import or_
from app.activity import log_activity, notify_user
from datetime import datetime, timedelta


doctor_bp = Blueprint('doctor', __name__, url_prefix='/doctor')


@doctor_bp.route('/dashboard')
@login_required
@role_required('Doctor')
def doctor_dashboard():
    doctor = Doctor.query.filter_by(id=current_user.id).first()
    doctor_name = doctor.name if doctor and doctor.name else current_user.username
    needs_profile = not (doctor and doctor.name)

    today = datetime.now().date()
    tomorrow = today + timedelta(days=1)
    week_end = today + timedelta(days=6)
    base_query = Appointment.query.filter_by(doctor_id=current_user.id)

    today_appointments = base_query.filter(
        Appointment.date >= datetime.combine(today, datetime.min.time()),
        Appointment.date < datetime.combine(tomorrow, datetime.min.time()),
        Appointment.status != 'Cancelled'
    ).count()
    pending_count = base_query.filter_by(status='Pending').count()
    confirmed_count = base_query.filter_by(status='Confirmed').count()
    completed_count = base_query.filter_by(status='Completed').count()

    upcoming = base_query.filter(
        Appointment.date >= datetime.now(),
        Appointment.status.in_(['Pending', 'Confirmed'])
    ).order_by(Appointment.date.asc()).limit(5).all()

    week_appointments = base_query.filter(
        Appointment.date >= datetime.combine(today, datetime.min.time()),
        Appointment.date < datetime.combine(week_end + timedelta(days=1), datetime.min.time()),
        Appointment.status != 'Cancelled'
    ).all()
    chart_labels, chart_values = [], []
    for offset in range(7):
        day = today + timedelta(days=offset)
        chart_labels.append(day.strftime('%a'))
        chart_values.append(sum(1 for appt in week_appointments if appt.date and appt.date.date() == day))

    return render_template(
        'doctor_dashboard.html', doctor_name=doctor_name, needs_profile=needs_profile,
        today_appointments=today_appointments, pending_count=pending_count,
        confirmed_count=confirmed_count, completed_count=completed_count,
        upcoming=upcoming, chart_labels=chart_labels, chart_values=chart_values
    )


@doctor_bp.route('/profile', methods=['GET', 'POST'])
@login_required
@role_required('Doctor')
def doctor_profile():
    doctor = Doctor.query.filter_by(id=current_user.id).first()
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        if not name:
            flash('Full name is required.', 'warning')
            return redirect(url_for('doctor.doctor_profile'))

        if not doctor:
            doctor = Doctor(id=current_user.id)
            db.session.add(doctor)

        doctor.name = name
        log_activity('doctor_profile_updated', f'Updated doctor profile for {name}.', 'Doctor', doctor.id)
        db.session.commit()
        return redirect(url_for('doctor.doctor_dashboard'))

    return render_template('doctor_profile.html', doctor=doctor)


@doctor_bp.route('/patients')
@login_required
@role_required('Doctor')
def doctor_patients():
    q = request.args.get('q', '').strip()
    query = Patient.query.join(Appointment, Appointment.patient_id == Patient.id).filter(Appointment.doctor_id == current_user.id).distinct()
    if q:
        query = query.filter(or_(
            Patient.name.ilike(f'%{q}%'),
            Patient.contact.ilike(f'%{q}%'),
            Patient.address.ilike(f'%{q}%')
        ))
    patients = query.order_by(Patient.name).all()
    return render_template('doctor_patients.html', patients=patients, q=q)


@doctor_bp.route('/patient/<int:patient_id>')
@login_required
@role_required('Doctor')
def doctor_view_patient(patient_id):
    patient = Patient.query.filter_by(id=patient_id).first()
    if not patient:
        abort(404)
    has_relationship = Appointment.query.filter_by(doctor_id=current_user.id, patient_id=patient_id).first()
    if not has_relationship:
        abort(403)
    return render_template('doctor_patient_view.html', patient=patient)

@doctor_bp.route('/appointments')
@login_required
@role_required('Doctor')
def view_appointments():
    status = request.args.get('status', 'all')
    q = request.args.get('q', '').strip()
    date_from_raw = request.args.get('date_from', '')
    date_to_raw = request.args.get('date_to', '')
    query = Appointment.query.join(Patient, Appointment.patient_id == Patient.id).filter(Appointment.doctor_id == current_user.id)
    if status in {'Pending', 'Confirmed', 'Completed', 'Cancelled', 'No Show'}:
        query = query.filter(Appointment.status == status)
    if q:
        query = query.filter(or_(Patient.name.ilike(f'%{q}%'), Appointment.reason.ilike(f'%{q}%')))
    try:
        if date_from_raw:
            start = datetime.strptime(date_from_raw, '%Y-%m-%d')
            query = query.filter(Appointment.date >= start)
        if date_to_raw:
            end = datetime.strptime(date_to_raw, '%Y-%m-%d') + timedelta(days=1)
            query = query.filter(Appointment.date < end)
    except ValueError:
        flash('One of the date filters was invalid and has been ignored.', 'warning')
    appointments = query.order_by(Appointment.date.desc()).all()
    return render_template('doctor_appointments.html', appointments=appointments, status=status, q=q, date_from=date_from_raw, date_to=date_to_raw, now=datetime.now())


@doctor_bp.route('/appointment/<int:appointment_id>')
@login_required
@role_required('Doctor')
def appointment_detail(appointment_id):
    appointment = Appointment.query.get_or_404(appointment_id)
    if appointment.doctor_id != current_user.id:
        abort(403)
    prescription = appointment.active_prescription
    current_reminders = AppointmentReminder.query.filter_by(
        appointment_id=appointment.id,
        user_id=current_user.id,
        scheduled_for=appointment.date,
    ).order_by(AppointmentReminder.sent_at.asc()).all()
    return render_template(
        'appointment_detail.html', appointment=appointment, prescription=prescription,
        viewer_role='Doctor', now=datetime.now(), current_reminders=current_reminders
    )


@doctor_bp.route('/prescriptions')
@login_required
@role_required('Doctor')
def prescriptions():
    q = request.args.get('q', '').strip()
    date_from_raw = request.args.get('date_from', '')
    date_to_raw = request.args.get('date_to', '')
    query = Prescription.query.join(Appointment).join(Patient, Appointment.patient_id == Patient.id).filter(Appointment.doctor_id == current_user.id, Prescription.is_deleted.is_(False))
    if q:
        query = query.filter(or_(Patient.name.ilike(f'%{q}%'), Prescription.diagnosis.ilike(f'%{q}%')))
    try:
        if date_from_raw:
            query = query.filter(Prescription.created_at >= datetime.strptime(date_from_raw, '%Y-%m-%d'))
        if date_to_raw:
            query = query.filter(Prescription.created_at < datetime.strptime(date_to_raw, '%Y-%m-%d') + timedelta(days=1))
    except ValueError:
        flash('One of the date filters was invalid and has been ignored.', 'warning')
    prescriptions = query.order_by(Prescription.created_at.desc()).all()
    return render_template('doctor_prescriptions.html', prescriptions=prescriptions, q=q, date_from=date_from_raw, date_to=date_to_raw)


@doctor_bp.route('/prescription/new', methods=['GET', 'POST'])
@login_required
@role_required('Doctor')
def new_prescription():
    appointments = Appointment.query.filter(
        Appointment.doctor_id == current_user.id,
        Appointment.status.in_(['Confirmed', 'Completed'])
    ).order_by(Appointment.date.desc()).all()
    appointment_id = request.args.get('appointment_id', type=int)

    if request.method == 'POST':
        appointment_id = request.form.get('appointment_id', type=int)
        if not appointment_id:
            flash('Please select an appointment to create a prescription for.', 'warning')
            return redirect(url_for('doctor.new_prescription'))

        appt = Appointment.query.get_or_404(appointment_id)
        if appt.doctor_id != current_user.id:
            abort(403)
        if appt.status not in ['Confirmed', 'Completed']:
            flash('A prescription can only be created for a confirmed or completed consultation.', 'warning')
            return redirect(url_for('doctor.appointment_detail', appointment_id=appt.id))
        if appt.active_prescription:
            flash('This appointment already has a prescription.', 'info')
            return redirect(url_for('doctor.prescription_detail', prescription_id=appt.active_prescription.id))

        diagnosis = request.form.get('diagnosis', '').strip()
        advice = request.form.get('advice', '').strip()
        follow_up_raw = request.form.get('follow_up_date', '').strip()
        if not diagnosis:
            flash('Diagnosis is required to create the prescription.', 'warning')
            return redirect(url_for('doctor.new_prescription', appointment_id=appt.id))

        follow_up_date = None
        if follow_up_raw:
            try:
                follow_up_date = datetime.strptime(follow_up_raw, '%Y-%m-%d').date()
            except ValueError:
                flash('Invalid follow-up date.', 'warning')
                return redirect(url_for('doctor.new_prescription', appointment_id=appt.id))

        prescription = Prescription(
            appointment_id=appt.id,
            diagnosis=diagnosis,
            advice=advice or None,
            follow_up_date=follow_up_date
        )
        db.session.add(prescription)
        db.session.flush()
        patient_name = appt.patient.name if appt.patient and appt.patient.name else 'Patient'
        log_activity('prescription_created', f'Created prescription #{prescription.id} for {patient_name}.', 'Prescription', prescription.id)
        notify_user(appt.patient_id, 'New prescription available', f'Dr. {appt.doctor.name if appt.doctor else current_user.username} created a prescription for your visit.', 'success', f'/patient/prescription/{prescription.id}')
        db.session.commit()
        flash('Prescription created. Add medicines below.', 'success')
        return redirect(url_for('doctor.prescription_detail', prescription_id=prescription.id))

    selected_appointment = None
    if appointment_id:
        selected_appointment = Appointment.query.filter_by(id=appointment_id, doctor_id=current_user.id).first()
    return render_template('new_prescription.html', appointments=appointments, selected_appointment=selected_appointment)


@doctor_bp.route('/prescription/<int:prescription_id>', methods=['GET', 'POST'])
@login_required
@role_required('Doctor')
def prescription_detail(prescription_id):
    prescription = Prescription.query.filter_by(id=prescription_id, is_deleted=False).first_or_404()
    if prescription.appointment.doctor_id != current_user.id:
        abort(403)

    if request.method == 'POST':
        medicine = request.form.get('medicine')
        dosage = request.form.get('dosage')
        frequency = request.form.get('frequency', '').strip()
        duration = request.form.get('duration', '').strip()
        quantity = request.form.get('quantity')
        instructions = request.form.get('instructions', '').strip()
        if not medicine:
            flash('Medicine name is required.', 'warning')
            return redirect(url_for('doctor.prescription_detail', prescription_id=prescription.id))
        try:
            qty = int(quantity) if quantity else None
        except ValueError:
            qty = None

        item = PrescriptionItem(
            prescription_id=prescription.id, medicine=medicine.strip(), dosage=(dosage or '').strip() or None,
            frequency=frequency or None, duration=duration or None, quantity=qty, instructions=instructions or None
        )
        db.session.add(item)
        log_activity('medicine_added', f'Added {item.medicine} to prescription #{prescription.id}.', 'Prescription', prescription.id)
        db.session.commit()
        return redirect(url_for('doctor.prescription_detail', prescription_id=prescription.id))

    return render_template('prescription_detail.html', prescription=prescription)


@doctor_bp.route('/prescription/<int:prescription_id>/edit', methods=['POST'])
@login_required
@role_required('Doctor')
def edit_prescription(prescription_id):
    prescription = Prescription.query.filter_by(id=prescription_id, is_deleted=False).first_or_404()
    if prescription.appointment.doctor_id != current_user.id:
        abort(403)

    diagnosis = request.form.get('diagnosis', '').strip()
    advice = request.form.get('advice', '').strip()
    follow_up_raw = request.form.get('follow_up_date', '').strip()
    if not diagnosis:
        flash('Diagnosis cannot be empty.', 'error')
        return redirect(url_for('doctor.prescription_detail', prescription_id=prescription.id))

    follow_up_date = None
    if follow_up_raw:
        try:
            follow_up_date = datetime.strptime(follow_up_raw, '%Y-%m-%d').date()
        except ValueError:
            flash('Invalid follow-up date.', 'warning')
            return redirect(url_for('doctor.prescription_detail', prescription_id=prescription.id))

    prescription.diagnosis = diagnosis
    prescription.advice = advice or None
    prescription.follow_up_date = follow_up_date
    prescription.updated_at = datetime.utcnow()
    log_activity('prescription_updated', f'Updated prescription #{prescription.id}.', 'Prescription', prescription.id)
    db.session.commit()
    flash('Prescription summary updated.', 'success')
    return redirect(url_for('doctor.prescription_detail', prescription_id=prescription.id))


@doctor_bp.route('/prescription/medicine/<int:item_id>/delete', methods=['POST'])
@login_required
@role_required('Doctor')
def delete_medicine(item_id):
    item = PrescriptionItem.query.get_or_404(item_id)
    if item.prescription.is_deleted or item.prescription.appointment.doctor_id != current_user.id:
        abort(403)

    prescription_id = item.prescription_id
    medicine_name = item.medicine
    db.session.delete(item)
    log_activity('medicine_removed', f'Removed {medicine_name} from prescription #{prescription_id}.', 'Prescription', prescription_id)
    db.session.commit()

    return redirect(url_for('doctor.prescription_detail', prescription_id=prescription_id))


@doctor_bp.route('/prescription/<int:prescription_id>/delete', methods=['POST'])
@login_required
@role_required('Doctor')
def delete_prescription(prescription_id):
    prescription = Prescription.query.filter_by(id=prescription_id, is_deleted=False).first_or_404()
    if prescription.appointment.doctor_id != current_user.id:
        abort(403)

    appointment_id = prescription.appointment_id
    prescription.is_deleted = True
    prescription.deleted_at = datetime.utcnow()
    prescription.deleted_by = current_user.id
    log_activity('prescription_archived', f'Archived prescription #{prescription_id} for appointment #{appointment_id}.', 'Appointment', appointment_id)
    db.session.commit()
    flash('Prescription archived. The clinical audit trail was preserved.', 'success')
    return redirect(url_for('doctor.prescriptions'))

@doctor_bp.route('/appointment/<int:appointment_id>/update', methods=['POST'])
@login_required
@role_required('Doctor')
def update_appointment_status(appointment_id):
    appointment = Appointment.query.get_or_404(appointment_id)

    if appointment.doctor_id != current_user.id:
        abort(403)

    status = request.form.get('status')
    notes = request.form.get('notes')

    # Valid status transitions
    valid_transitions = {
        'Pending': ['Confirmed', 'Cancelled'],
        'Confirmed': ['Completed', 'Cancelled', 'No Show'],
        'Completed': [],
        'Cancelled': [],
        'No Show': [],
    }

    if appointment.status not in valid_transitions or status not in valid_transitions.get(appointment.status, []):
        flash('Invalid status transition.', 'error')
        return redirect(url_for('doctor.view_appointments'))

    if status in ['Completed', 'No Show'] and appointment.date > datetime.now():
        flash('A future appointment cannot be completed or marked as a no-show yet.', 'warning')
        return redirect(request.referrer or url_for('doctor.view_appointments'))

    previous_status = appointment.status
    appointment.status = status
    if notes:
        appointment.notes = notes
    appointment.updated_at = datetime.utcnow()
    if status == 'No Show':
        appointment.no_show_at = datetime.utcnow()
    doctor_name = appointment.doctor.name if appointment.doctor else current_user.username
    log_activity('appointment_status_changed', f'Appointment #{appointment.id}: {previous_status} → {status}.', 'Appointment', appointment.id)
    notify_user(appointment.patient_id, f'Appointment {status.lower()}', f'Dr. {doctor_name} marked your appointment on {appointment.date.strftime("%d %b %Y at %I:%M %p")} as {status.lower()}.', 'success' if status in ['Confirmed', 'Completed'] else 'warning', f'/patient/appointment/{appointment.id}')
    db.session.commit()

    flash(f'Appointment marked as {status.lower()}.', 'success')
    return redirect(request.referrer or url_for('doctor.view_appointments'))


@doctor_bp.route('/appointment/<int:appointment_id>/notes', methods=['POST'])
@login_required
@role_required('Doctor')
def update_appointment_notes(appointment_id):
    appointment = Appointment.query.get_or_404(appointment_id)
    if appointment.doctor_id != current_user.id:
        abort(403)
    appointment.notes = request.form.get('notes', '').strip() or None
    appointment.updated_at = datetime.utcnow()
    log_activity('consultation_notes_updated', f'Updated consultation notes for appointment #{appointment.id}.', 'Appointment', appointment.id)
    db.session.commit()
    flash('Consultation notes saved.', 'success')
    return redirect(url_for('doctor.appointment_detail', appointment_id=appointment.id))


@doctor_bp.route('/availability', methods=['GET', 'POST'])
@login_required
@role_required('Doctor')
def manage_availability():
    doctor = Doctor.query.filter_by(id=current_user.id).first()

    if request.method == 'POST':
        date_str = request.form.get('date')
        start_time = request.form.get('start_time')
        end_time = request.form.get('end_time')
        is_available = request.form.get('is_available') == 'on'

        try:
            date = datetime.strptime(date_str, '%Y-%m-%d').date()

            if date < datetime.now().date():
                flash('Cannot set availability for past dates.', 'warning')
                return redirect(url_for('doctor.manage_availability'))

            if date > (datetime.now().date() + timedelta(days=14)):
                flash('Cannot set availability beyond 14 days.', 'warning')
                return redirect(url_for('doctor.manage_availability'))

            start_dt = datetime.strptime(start_time, '%H:%M')
            end_dt = datetime.strptime(end_time, '%H:%M')
            if start_dt >= end_dt:
                flash('End time must be later than start time.', 'warning')
                return redirect(url_for('doctor.manage_availability'))

            overlapping = DoctorAvailability.query.filter(
                DoctorAvailability.doctor_id == doctor.id,
                DoctorAvailability.date == date,
                DoctorAvailability.is_available.is_(is_available),
                DoctorAvailability.start_time < end_time,
                DoctorAvailability.end_time > start_time,
            ).filter(
                ~((DoctorAvailability.start_time == start_time) & (DoctorAvailability.end_time == end_time))
            ).first()
            if overlapping:
                kind = 'bookable' if is_available else 'blocked'
                flash(f'This {kind} window overlaps an existing {kind} window. Edit or remove the existing window first.', 'warning')
                return redirect(url_for('doctor.manage_availability'))

            availability = DoctorAvailability.query.filter_by(
                doctor_id=doctor.id,
                date=date,
                start_time=start_time,
                end_time=end_time
            ).first()

            if availability:
                availability.is_available = is_available
            else:
                availability = DoctorAvailability(
                    doctor_id=doctor.id,
                    date=date,
                    start_time=start_time,
                    end_time=end_time,
                    is_available=is_available
                )
                db.session.add(availability)

            log_activity('availability_updated', f'Updated availability for {date.isoformat()} {start_time}–{end_time} ({"bookable" if is_available else "blocked"}).', 'DoctorAvailability', availability.id)
            db.session.commit()
            flash('Availability updated successfully.', 'success')

        except (ValueError, TypeError):
            flash('Invalid date or time format.', 'error')

        return redirect(url_for('doctor.manage_availability'))

    # Get availability for the next 14 days
    today = datetime.now().date()
    next_week = today + timedelta(days=14)

    availabilities = DoctorAvailability.query.filter(
        DoctorAvailability.doctor_id == doctor.id,
        DoctorAvailability.date >= today,
        DoctorAvailability.date <= next_week
    ).order_by(DoctorAvailability.date).all()

    booked_appointments = Appointment.query.filter(
        Appointment.doctor_id == doctor.id,
        Appointment.date >= datetime.combine(today, datetime.min.time()),
        Appointment.date < datetime.combine(next_week + timedelta(days=1), datetime.min.time()),
        Appointment.status != 'Cancelled'
    ).all()
    booked_by_date = {}
    for appointment in booked_appointments:
        key = appointment.date.date().isoformat()
        booked_by_date.setdefault(key, []).append(appointment.date.strftime('%H:%M'))

    return render_template(
        'doctor_availability.html', availabilities=availabilities,
        today=today, max_date=next_week, booked_by_date=booked_by_date
    )


@doctor_bp.route('/availability/<int:availability_id>/delete', methods=['POST'])
@login_required
@role_required('Doctor')
def delete_availability(availability_id):
    availability = DoctorAvailability.query.get_or_404(availability_id)
    if availability.doctor_id != current_user.id:
        abort(403)
    description = f'Removed availability on {availability.date.isoformat()} {availability.start_time}–{availability.end_time}.'
    db.session.delete(availability)
    log_activity('availability_removed', description, 'DoctorAvailability', availability_id)
    db.session.commit()
    flash('Availability window removed.', 'success')
    return redirect(url_for('doctor.manage_availability'))


@doctor_bp.route('/patient/<int:patient_id>/history')
@login_required
@role_required('Doctor')
def view_patient_history(patient_id):
    patient = Patient.query.filter_by(id=patient_id).first()
    if not patient:
        abort(404)
    if not Appointment.query.filter_by(doctor_id=current_user.id, patient_id=patient_id).first():
        abort(403)

    # Get all completed appointments for this patient with the current doctor
    appointments = Appointment.query.filter(
        Appointment.patient_id == patient_id,
        Appointment.doctor_id == current_user.id,
        Appointment.status == 'Completed'
    ).order_by(Appointment.date.desc()).all()

    return render_template('doctor_patient_history.html', patient=patient, appointments=appointments)
