from flask import Blueprint, render_template, abort, request, redirect, url_for, flash
from flask_login import login_required, current_user
from app.routes.auth_decorator import role_required
from app.models import Doctor, Patient, Appointment, Prescription, PrescriptionItem, DoctorAvailability
from app import db
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
        db.session.commit()
        return redirect(url_for('doctor.doctor_dashboard'))

    return render_template('doctor_profile.html', doctor=doctor)


@doctor_bp.route('/patients')
@login_required
@role_required('Doctor')
def doctor_patients():
    patients = Patient.query.order_by(Patient.name).all()
    return render_template('doctor_patients.html', patients=patients)


@doctor_bp.route('/patient/<int:patient_id>')
@login_required
@role_required('Doctor')
def doctor_view_patient(patient_id):
    patient = Patient.query.filter_by(id=patient_id).first()
    if not patient:
        abort(404)
    return render_template('doctor_patient_view.html', patient=patient)

@doctor_bp.route('/appointments')
@login_required
@role_required('Doctor')
def view_appointments():
    status = request.args.get('status', 'all')
    query = Appointment.query.filter_by(doctor_id=current_user.id)
    if status in {'Pending', 'Confirmed', 'Completed', 'Cancelled'}:
        query = query.filter_by(status=status)
    appointments = query.order_by(Appointment.date.desc()).all()
    return render_template('doctor_appointments.html', appointments=appointments, status=status)


@doctor_bp.route('/prescriptions')
@login_required
@role_required('Doctor')
def prescriptions():
    prescriptions = Prescription.query.join(Appointment).filter(Appointment.doctor_id == current_user.id).order_by(Prescription.created_at.desc()).all()
    return render_template('doctor_prescriptions.html', prescriptions=prescriptions)


@doctor_bp.route('/prescription/new', methods=['GET', 'POST'])
@login_required
@role_required('Doctor')
def new_prescription():
    appointments = Appointment.query.filter_by(doctor_id=current_user.id, status='Confirmed').order_by(Appointment.date.desc()).all()
    if request.method == 'POST':
        appointment_id = request.form.get('appointment_id')
        if not appointment_id:
            flash('Please select an appointment to create a prescription for.', 'warning')
            return redirect(url_for('doctor.new_prescription'))

        appt = Appointment.query.get_or_404(appointment_id)
        if appt.doctor_id != current_user.id:
            abort(403)

        prescription = Prescription(appointment_id=appt.id, diagnosis='')
        db.session.add(prescription)
        db.session.commit()
        return redirect(url_for('doctor.prescription_detail', prescription_id=prescription.id))

    return render_template('new_prescription.html', appointments=appointments)


@doctor_bp.route('/prescription/<int:prescription_id>', methods=['GET', 'POST'])
@login_required
@role_required('Doctor')
def prescription_detail(prescription_id):
    prescription = Prescription.query.get_or_404(prescription_id)
    if prescription.appointment.doctor_id != current_user.id:
        abort(403)

    if request.method == 'POST':
        medicine = request.form.get('medicine')
        dosage = request.form.get('dosage')
        duration = request.form.get('duration')
        quantity = request.form.get('quantity')
        if not medicine:
            flash('Medicine name is required.', 'warning')
            return redirect(url_for('doctor.prescription_detail', prescription_id=prescription.id))
        try:
            qty = int(quantity) if quantity else None
        except ValueError:
            qty = None

        item = PrescriptionItem(prescription_id=prescription.id, medicine=medicine, dosage=dosage, duration=duration, quantity=qty)
        db.session.add(item)
        db.session.commit()
        return redirect(url_for('doctor.prescription_detail', prescription_id=prescription.id))

    return render_template('prescription_detail.html', prescription=prescription)


@doctor_bp.route('/prescription/<int:prescription_id>/edit', methods=['POST'])
@login_required
@role_required('Doctor')
def edit_prescription(prescription_id):
    prescription = Prescription.query.get_or_404(prescription_id)
    if prescription.appointment.doctor_id != current_user.id:
        abort(403)

    diagnosis = request.form.get('diagnosis')
    if diagnosis:
        prescription.diagnosis = diagnosis
        db.session.commit()
    else:
        flash('Diagnosis cannot be empty.', 'error')

    return redirect(url_for('doctor.prescription_detail', prescription_id=prescription.id))


@doctor_bp.route('/prescription/medicine/<int:item_id>/delete', methods=['POST'])
@login_required
@role_required('Doctor')
def delete_medicine(item_id):
    item = PrescriptionItem.query.get_or_404(item_id)
    if item.prescription.appointment.doctor_id != current_user.id:
        abort(403)

    prescription_id = item.prescription_id
    db.session.delete(item)
    db.session.commit()

    return redirect(url_for('doctor.prescription_detail', prescription_id=prescription_id))


@doctor_bp.route('/prescription/<int:prescription_id>/delete', methods=['POST'])
@login_required
@role_required('Doctor')
def delete_prescription(prescription_id):
    prescription = Prescription.query.get_or_404(prescription_id)
    if prescription.appointment.doctor_id != current_user.id:
        abort(403)

    db.session.delete(prescription)
    db.session.commit()
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
        'Confirmed': ['Completed', 'Cancelled'],
        'Completed': [],
        'Cancelled': []
    }

    if appointment.status not in valid_transitions or status not in valid_transitions.get(appointment.status, []):
        flash('Invalid status transition.', 'error')
        return redirect(url_for('doctor.view_appointments'))

    appointment.status = status
    if notes:
        appointment.notes = notes
    appointment.updated_at = datetime.utcnow()
    db.session.commit()

    return redirect(url_for('doctor.view_appointments'))


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
    db.session.delete(availability)
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

    # Get all completed appointments for this patient with the current doctor
    appointments = Appointment.query.filter(
        Appointment.patient_id == patient_id,
        Appointment.doctor_id == current_user.id,
        Appointment.status == 'Completed'
    ).order_by(Appointment.date.desc()).all()

    return render_template('doctor_patient_history.html', patient=patient, appointments=appointments)
