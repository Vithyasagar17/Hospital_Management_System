from flask import Blueprint, render_template, request, redirect, url_for, flash, abort
from flask_login import login_required, current_user
from app.routes.auth_decorator import role_required
from app.models import Patient, Doctor, Appointment, Specialization, DoctorAvailability, Prescription
from app import db
from datetime import datetime, timedelta
from app.scheduling import available_slots_for_doctor, is_valid_booking_slot

patient_bp = Blueprint('patient', __name__, url_prefix='/patient')


@patient_bp.route('/dashboard')
@login_required
@role_required('Patient')
def patient_dashboard():
    patient = Patient.query.filter_by(id=current_user.id).first()
    patient_name = patient.name if patient and patient.name else current_user.username
    base_query = Appointment.query.filter_by(patient_id=current_user.id)

    upcoming = base_query.filter(
        Appointment.date >= datetime.now(),
        Appointment.status.in_(['Pending', 'Confirmed'])
    ).order_by(Appointment.date.asc()).limit(4).all()
    pending_count = base_query.filter_by(status='Pending').count()
    confirmed_count = base_query.filter_by(status='Confirmed').count()
    completed_count = base_query.filter_by(status='Completed').count()

    status_counts = {
        status: base_query.filter_by(status=status).count()
        for status in ['Pending', 'Confirmed', 'Completed', 'Cancelled']
    }
    return render_template(
        'patient_dashboard.html', patient_name=patient_name, upcoming=upcoming,
        pending_count=pending_count, confirmed_count=confirmed_count,
        completed_count=completed_count, status_counts=status_counts
    )


@patient_bp.route('/profile', methods=['GET', 'POST'])
@login_required
@role_required('Patient')
def patient_profile():
    patient = Patient.query.filter_by(id=current_user.id).first()
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        contact = request.form.get('contact', '').strip()
        address = request.form.get('address', '').strip()
        age = request.form.get('age')
        gender = request.form.get('gender')
        height = request.form.get('height')
        weight = request.form.get('weight')

        if not name:
            flash('Full name is required.', 'warning')
            return redirect(url_for('patient.patient_profile'))

        if not patient:
            patient = Patient(id=current_user.id)
            db.session.add(patient)

        patient.name = name
        patient.contact = contact or None
        patient.address = address or None
        try:
            patient.age = int(age) if age else None
        except ValueError:
            patient.age = None
        patient.gender = gender or None
        try:
            patient.height = float(height) if height else None
        except ValueError:
            patient.height = None
        try:
            patient.weight = float(weight) if weight else None
        except ValueError:
            patient.weight = None

        db.session.commit()
        return redirect(url_for('patient.patient_dashboard'))

    return render_template('patient_profile.html', patient=patient)


@patient_bp.route('/medical-history')
@login_required
@role_required('Patient')
def medical_history():
    appointments = Appointment.query.filter_by(patient_id=current_user.id)\
        .order_by(Appointment.date.desc())\
        .all()
    return render_template('medical_history.html', appointments=appointments)

@patient_bp.route('/book_appointment', methods=['GET', 'POST'])
@login_required
@role_required('Patient')
def book_appointment():
    patient = Patient.query.filter_by(id=current_user.id).first()
    doctors = Doctor.query.filter_by(is_blacklisted=False).all()

    if request.method == 'POST':
        doctor_id = request.form.get('doctor_id')
        date_str = request.form.get('date')
        time_str = request.form.get('time')
        reason = request.form.get('reason', '').strip()

        if not all([doctor_id, date_str, time_str, reason]):
            flash('Please choose a doctor, date, time slot, and reason.', 'error')
            return redirect(url_for('patient.book_appointment'))

        try:
            doctor_id = int(doctor_id)
            date = datetime.strptime(f"{date_str} {time_str}", '%Y-%m-%d %H:%M')

            doctor = Doctor.query.filter_by(id=doctor_id, is_blacklisted=False).first()
            if not doctor:
                flash('That doctor is not currently available for booking.', 'error')
                return redirect(url_for('patient.book_appointment'))

            if date <= datetime.now():
                flash('Cannot book appointments in the past.', 'error')
                return redirect(url_for('patient.book_appointment'))

            if not is_valid_booking_slot(doctor_id, date):
                flash('That slot is no longer available. Please choose another time.', 'warning')
                return redirect(url_for('patient.book_appointment'))

            existing_appointment = Appointment.query.filter(
                Appointment.doctor_id == doctor_id,
                Appointment.date == date,
                Appointment.status != 'Cancelled'
            ).first()
            if existing_appointment:
                flash('That time slot was just booked. Please choose another one.', 'warning')
                return redirect(url_for('patient.book_appointment'))

            appointment = Appointment(
                patient_id=patient.id,
                doctor_id=doctor_id,
                date=date,
                time=time_str,
                reason=reason,
                status='Pending'
            )
            db.session.add(appointment)
            db.session.commit()
            flash('Appointment request sent to the doctor.', 'success')
            return redirect(url_for('patient.view_appointments'))

        except (ValueError, TypeError):
            flash('Invalid booking details.', 'error')
            return redirect(url_for('patient.book_appointment'))

    slot_map = {}
    for doctor in doctors:
        slot_map[str(doctor.id)] = available_slots_for_doctor(doctor.id, days=15)

    return render_template(
        'book_appointment.html', doctors=doctors, patient=patient,
        now=datetime.now(), slot_map=slot_map
    )

@patient_bp.route('/appointments')
@login_required
@role_required('Patient')
def view_appointments():
    status = request.args.get('status', 'all')
    query = Appointment.query.filter_by(patient_id=current_user.id)
    if status in {'Pending', 'Confirmed', 'Completed', 'Cancelled'}:
        query = query.filter_by(status=status)
    appointments = query.order_by(Appointment.date.desc()).all()
    return render_template('view_appointments.html', appointments=appointments, status=status, now=datetime.now())


@patient_bp.route('/appointment/<int:appointment_id>')
@login_required
@role_required('Patient')
def appointment_detail(appointment_id):
    appointment = Appointment.query.get_or_404(appointment_id)
    if appointment.patient_id != current_user.id:
        abort(403)
    prescription = appointment.prescriptions[0] if appointment.prescriptions else None
    return render_template(
        'appointment_detail.html', appointment=appointment, prescription=prescription,
        viewer_role='Patient', now=datetime.now()
    )


@patient_bp.route('/prescription/<int:prescription_id>')
@login_required
@role_required('Patient')
def prescription_detail(prescription_id):
    prescription = Prescription.query.get_or_404(prescription_id)
    if prescription.appointment.patient_id != current_user.id:
        abort(403)
    return render_template('patient_prescription_detail.html', prescription=prescription)


@patient_bp.route('/search-doctors')
@login_required
@role_required('Patient')
def search_doctors():
    query = request.args.get('q', '').strip()
    search_type = request.args.get('type', 'all')

    results = {'doctors': [], 'specializations': []}

    if query:
        if search_type in ['all', 'doctor']:
            # Search by doctor name
            results['doctors'] = Doctor.query.filter(
                Doctor.name.ilike(f'%{query}%'),
                Doctor.is_blacklisted == False
            ).all()

        if search_type in ['all', 'specialization']:
            # Search by specialization
            results['specializations'] = Specialization.query.filter(
                Specialization.name.ilike(f'%{query}%')
            ).all()

    return render_template('patient_search_doctors.html', results=results, query=query, search_type=search_type)


@patient_bp.route('/doctor/<int:doctor_id>/profile')
@login_required
@role_required('Patient')
def view_doctor_profile(doctor_id):
    doctor = Doctor.query.filter_by(id=doctor_id, is_blacklisted=False).first()
    if not doctor:
        abort(404)

    return render_template('patient_view_doctor_profile.html', doctor=doctor)


@patient_bp.route('/appointment/<int:appointment_id>/cancel', methods=['POST'])
@login_required
@role_required('Patient')
def cancel_appointment(appointment_id):
    appointment = Appointment.query.get_or_404(appointment_id)

    if appointment.patient_id != current_user.id:
        abort(403)

    if appointment.status not in ['Pending', 'Confirmed']:
        flash('Only pending or confirmed appointments can be cancelled.', 'warning')
        return redirect(url_for('patient.view_appointments'))

    if appointment.date and appointment.date <= datetime.now():
        flash('Past appointments can no longer be cancelled.', 'warning')
        return redirect(url_for('patient.view_appointments'))

    appointment.status = 'Cancelled'
    appointment.updated_at = datetime.utcnow()
    db.session.commit()

    flash('Appointment cancelled successfully.', 'success')
    return redirect(url_for('patient.view_appointments'))
