from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required
from app import db
from app.models import Doctor, Patient, Appointment, Specialization, User
from app.routes.auth_decorator import role_required

admin_bp = Blueprint('admin', __name__, url_prefix='/admin')

@admin_bp.route('/dashboard')
@login_required
@role_required('Admin')
def admin_dashboard():
    total_doctors = Doctor.query.filter_by(is_blacklisted=False).count()
    total_patients = Patient.query.filter_by(is_blacklisted=False).count()
    total_appointments = Appointment.query.count()
    return render_template('admin_dashboard.html',total_doctors=total_doctors,total_patients=total_patients,total_appointments=total_appointments)


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
    if status == 'blacklisted':
        doctors = Doctor.query.filter_by(is_blacklisted=True).order_by(Doctor.name).all()
    else:
        doctors = Doctor.query.filter_by(is_blacklisted=False).order_by(Doctor.name).all()
    return render_template('admin_doctors.html', doctors=doctors, status=status)


@admin_bp.route('/doctor/add', methods=['GET', 'POST'])
@login_required
@role_required('Admin')
def add_doctor():
    specializations = Specialization.query.all()
    
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '').strip()
        name = request.form.get('name', '').strip()
        specialization_id = request.form.get('specialization_id')
        
        if not username or not password or not name:
            flash('Username, password, and name are required.', 'warning')
            return redirect(url_for('admin.add_doctor'))
        
        if User.query.filter_by(username=username).first():
            flash('Username already exists.', 'warning')
            return redirect(url_for('admin.add_doctor'))
        
        try:
            spec_id = int(specialization_id) if specialization_id else None
        except ValueError:
            spec_id = None
        
        # Create user
        user = User(username=username, role='Doctor')
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        
        # Create doctor profile
        doctor = Doctor(id=user.id, name=name, specialization_id=spec_id)
        db.session.add(doctor)
        db.session.commit()
        
        flash(f'Doctor {name} added successfully with username: {username}', 'success')
        return redirect(url_for('admin.admin_doctors'))
    
    return render_template('admin_add_doctor.html', specializations=specializations)


@admin_bp.route('/patients')
@login_required
@role_required('Admin')
def admin_patients():
    status = request.args.get('status', 'active')
    if status == 'blacklisted':
        patients = Patient.query.filter_by(is_blacklisted=True).order_by(Patient.name).all()
    else:
        patients = Patient.query.filter_by(is_blacklisted=False).order_by(Patient.name).all()
    return render_template('admin_patients.html', patients=patients, status=status)


@admin_bp.route('/appointments')
@login_required
@role_required('Admin')
def admin_appointments():
    appointments = Appointment.query.order_by(Appointment.date.desc()).all()
    return render_template('admin_appointments.html', appointments=appointments)


@admin_bp.route('/search')
@login_required
@role_required('Admin')
def search():
    query = request.args.get('q', '').strip()
    search_type = request.args.get('type', 'all')
    
    results = {'doctors': [], 'patients': []}
    
    if query:
        if search_type in ['all', 'doctor']:
            # Search by doctor name or specialization
            results['doctors'] = Doctor.query.filter(
                (Doctor.name.ilike(f'%{query}%')) |
                (Doctor.specialization.has(Specialization.name.ilike(f'%{query}%')))
            ).filter_by(is_blacklisted=False).all()
        
        if search_type in ['all', 'patient']:
            # Search by patient name, ID, or contact
            results['patients'] = Patient.query.filter(
                (Patient.name.ilike(f'%{query}%')) |
                (Patient.contact.ilike(f'%{query}%')) |
                (Patient.id == int(query) if query.isdigit() else False)
            ).filter_by(is_blacklisted=False).all()
    
    return render_template('admin_search.html', results=results, query=query, search_type=search_type)


@admin_bp.route('/doctor/<int:doctor_id>/edit', methods=['GET', 'POST'])
@login_required
@role_required('Admin')
def edit_doctor(doctor_id):
    doctor = Doctor.query.get_or_404(doctor_id)
    specializations = Specialization.query.all()
    
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
        flash(f'Patient {name} updated successfully.', 'success')
        return redirect(url_for('admin.admin_patients'))
    
    return render_template('admin_edit_patient.html', patient=patient)


@admin_bp.route('/doctor/<int:doctor_id>/blacklist', methods=['POST'])
@login_required
@role_required('Admin')
def blacklist_doctor(doctor_id):
    doctor = Doctor.query.get_or_404(doctor_id)
    doctor.is_blacklisted = True
    db.session.commit()
    flash(f'Doctor {doctor.name} has been blacklisted.', 'success')
    return redirect(url_for('admin.admin_doctors'))


@admin_bp.route('/patient/<int:patient_id>/blacklist', methods=['POST'])
@login_required
@role_required('Admin')
def blacklist_patient(patient_id):
    patient = Patient.query.get_or_404(patient_id)
    patient.is_blacklisted = True
    db.session.commit()
    flash(f'Patient {patient.name} has been blacklisted.', 'success')
    return redirect(url_for('admin.admin_patients'))


@admin_bp.route('/doctor/<int:doctor_id>/unblacklist', methods=['POST'])
@login_required
@role_required('Admin')
def unblacklist_doctor(doctor_id):
    doctor = Doctor.query.get_or_404(doctor_id)
    doctor.is_blacklisted = False
    db.session.commit()
    flash(f'Doctor {doctor.name} has been unblacklisted.', 'success')
    return redirect(url_for('admin.admin_doctors'))


@admin_bp.route('/patient/<int:patient_id>/unblacklist', methods=['POST'])
@login_required
@role_required('Admin')
def unblacklist_patient(patient_id):
    patient = Patient.query.get_or_404(patient_id)
    patient.is_blacklisted = False
    db.session.commit()
    flash(f'Patient {patient.name} has been unblacklisted.', 'success')
    return redirect(url_for('admin.admin_patients'))
