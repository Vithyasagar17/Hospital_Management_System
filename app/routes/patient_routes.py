from flask import Blueprint, render_template, request, redirect, url_for, flash, abort
from flask_login import login_required, current_user
from app.routes.auth_decorator import role_required
from app.models import Patient, Doctor, Appointment, Specialization, DoctorAvailability, Prescription
from app import db
from sqlalchemy import or_
from app.activity import log_activity, notify_user
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

        log_activity('patient_profile_updated', f'Updated patient profile for {patient.name}.', 'Patient', patient.id)
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
            db.session.flush()
            patient_name = patient.name if patient and patient.name else current_user.username
            doctor_name = doctor.name if doctor and doctor.name else 'Doctor'
            log_activity('appointment_booked', f'Booked appointment #{appointment.id} with Dr. {doctor_name}.', 'Appointment', appointment.id)
            notify_user(doctor_id, 'New appointment request', f'{patient_name} requested {date.strftime("%d %b %Y at %I:%M %p")}.', 'info', f'/doctor/appointment/{appointment.id}')
            db.session.commit()
            flash('Appointment request sent to the doctor.', 'success')
            return redirect(url_for('patient.view_appointments'))

        except (ValueError, TypeError):
            flash('Invalid booking details.', 'error')
            return redirect(url_for('patient.book_appointment'))

    slot_map = {}
    for doctor in doctors:
        slot_map[str(doctor.id)] = available_slots_for_doctor(doctor.id, days=15)
    selected_doctor_id = request.args.get('doctor_id', type=int)

    return render_template(
        'book_appointment.html', doctors=doctors, patient=patient,
        now=datetime.now(), slot_map=slot_map, selected_doctor_id=selected_doctor_id
    )

@patient_bp.route('/appointments')
@login_required
@role_required('Patient')
def view_appointments():
    status = request.args.get('status', 'all')
    q = request.args.get('q', '').strip()
    date_from_raw = request.args.get('date_from', '')
    date_to_raw = request.args.get('date_to', '')
    query = Appointment.query.join(Doctor, Appointment.doctor_id == Doctor.id).filter(Appointment.patient_id == current_user.id)
    if status in {'Pending', 'Confirmed', 'Completed', 'Cancelled'}:
        query = query.filter(Appointment.status == status)
    if q:
        query = query.filter(or_(Doctor.name.ilike(f'%{q}%'), Appointment.reason.ilike(f'%{q}%')))
    try:
        if date_from_raw:
            query = query.filter(Appointment.date >= datetime.strptime(date_from_raw, '%Y-%m-%d'))
        if date_to_raw:
            query = query.filter(Appointment.date < datetime.strptime(date_to_raw, '%Y-%m-%d') + timedelta(days=1))
    except ValueError:
        flash('One of the date filters was invalid and has been ignored.', 'warning')
    appointments = query.order_by(Appointment.date.desc()).all()
    return render_template('view_appointments.html', appointments=appointments, status=status, now=datetime.now(), q=q, date_from=date_from_raw, date_to=date_to_raw)


@patient_bp.route('/appointment/<int:appointment_id>')
@login_required
@role_required('Patient')
def appointment_detail(appointment_id):
    appointment = Appointment.query.get_or_404(appointment_id)
    if appointment.patient_id != current_user.id:
        abort(403)
    prescription = appointment.active_prescription
    return render_template(
        'appointment_detail.html', appointment=appointment, prescription=prescription,
        viewer_role='Patient', now=datetime.now()
    )


@patient_bp.route('/prescription/<int:prescription_id>')
@login_required
@role_required('Patient')
def prescription_detail(prescription_id):
    prescription = Prescription.query.filter_by(id=prescription_id, is_deleted=False).first_or_404()
    if prescription.appointment.patient_id != current_user.id:
        abort(403)
    return render_template('patient_prescription_detail.html', prescription=prescription)


@patient_bp.route('/search-doctors')
@login_required
@role_required('Patient')
def search_doctors():
    q = request.args.get('q', '').strip()
    specialization_id = request.args.get('specialization_id', type=int)
    available_on_raw = request.args.get('available_on', '').strip()

    query = Doctor.query.filter(Doctor.is_blacklisted.is_(False))
    if q:
        query = query.filter(or_(Doctor.name.ilike(f'%{q}%'), Doctor.specialization.has(Specialization.name.ilike(f'%{q}%'))))
    if specialization_id:
        query = query.filter(Doctor.specialization_id == specialization_id)

    doctors = query.order_by(Doctor.name).all()
    available_slots = {}
    available_on = None
    if available_on_raw:
        try:
            available_on = datetime.strptime(available_on_raw, '%Y-%m-%d').date()
        except ValueError:
            flash('Invalid availability date.', 'warning')

    if available_on:
        filtered = []
        for doctor in doctors:
            slot_map = available_slots_for_doctor(doctor.id, days=15)
            day_slots = slot_map.get(available_on.isoformat(), [])
            if day_slots:
                filtered.append(doctor)
                available_slots[str(doctor.id)] = day_slots
        doctors = filtered

    specializations = Specialization.query.order_by(Specialization.name).all()
    return render_template('patient_search_doctors.html', doctors=doctors, query=q,
                           specialization_id=specialization_id, specializations=specializations,
                           available_on=available_on_raw, available_slots=available_slots)


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
    patient_name = appointment.patient.name if appointment.patient and appointment.patient.name else current_user.username
    log_activity('appointment_cancelled', f'Cancelled appointment #{appointment.id}.', 'Appointment', appointment.id)
    notify_user(appointment.doctor_id, 'Appointment cancelled', f'{patient_name} cancelled the appointment on {appointment.date.strftime("%d %b %Y at %I:%M %p")}.', 'warning', f'/doctor/appointment/{appointment.id}')
    db.session.commit()

    flash('Appointment cancelled successfully.', 'success')
    return redirect(url_for('patient.view_appointments'))
