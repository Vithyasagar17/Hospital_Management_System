from datetime import datetime

from app import db
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from sqlalchemy import text


class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(100), unique=True, nullable=False)
    email = db.Column(db.String(255), unique=True, nullable=True)
    email_verified = db.Column(db.Boolean, default=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(50), nullable=False)
    failed_login_count = db.Column(db.Integer, default=0, nullable=False)
    locked_until = db.Column(db.DateTime, nullable=True)
    last_login_at = db.Column(db.DateTime, nullable=True)
    password_changed_at = db.Column(db.DateTime, nullable=True)
    session_version = db.Column(db.Integer, default=1, nullable=False)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)
        self.password_changed_at = datetime.utcnow()

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)


class Specialization(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False)
    description = db.Column(db.String(255))


class Department(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), unique=True, nullable=False)
    code = db.Column(db.String(20), unique=True, nullable=False)
    description = db.Column(db.String(500), nullable=True)
    location = db.Column(db.String(120), nullable=True)
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    head_doctor_id = db.Column(db.Integer, db.ForeignKey('doctor.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=db.func.current_timestamp(), nullable=False)
    updated_at = db.Column(db.DateTime, default=db.func.current_timestamp(), onupdate=db.func.current_timestamp())

    head_doctor = db.relationship('Doctor', foreign_keys=[head_doctor_id], post_update=True)


class Ward(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    department_id = db.Column(db.Integer, db.ForeignKey('department.id'), nullable=False, index=True)
    name = db.Column(db.String(120), nullable=False)
    code = db.Column(db.String(30), unique=True, nullable=False)
    ward_type = db.Column(db.String(30), default='General', nullable=False)
    location = db.Column(db.String(120), nullable=True)
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    created_at = db.Column(db.DateTime, default=db.func.current_timestamp(), nullable=False)
    updated_at = db.Column(db.DateTime, default=db.func.current_timestamp(), onupdate=db.func.current_timestamp())

    department = db.relationship(
        'Department',
        backref=db.backref('wards', lazy=True),
    )

    __table_args__ = (
        db.UniqueConstraint('department_id', 'name', name='uq_ward_department_name'),
    )


class Bed(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    ward_id = db.Column(db.Integer, db.ForeignKey('ward.id'), nullable=False, index=True)
    bed_number = db.Column(db.String(30), nullable=False)
    status = db.Column(db.String(20), default='Available', nullable=False, index=True)
    notes = db.Column(db.String(255), nullable=True)
    created_at = db.Column(db.DateTime, default=db.func.current_timestamp(), nullable=False)
    updated_at = db.Column(db.DateTime, default=db.func.current_timestamp(), onupdate=db.func.current_timestamp())

    ward = db.relationship(
        'Ward',
        backref=db.backref('beds', lazy=True),
    )

    __table_args__ = (
        db.UniqueConstraint('ward_id', 'bed_number', name='uq_bed_ward_number'),
    )


class Doctor(db.Model):
    id = db.Column(db.Integer, db.ForeignKey('user.id'), primary_key=True)
    name = db.Column(db.String(100))
    specialization_id = db.Column(db.Integer, db.ForeignKey('specialization.id'))
    department_id = db.Column(db.Integer, db.ForeignKey('department.id'), nullable=True, index=True)
    specialization = db.relationship('Specialization', backref='doctors')
    department = db.relationship(
        'Department',
        foreign_keys=[department_id],
        backref=db.backref('doctors', lazy=True),
    )
    is_blacklisted = db.Column(db.Boolean, default=False)


class Patient(db.Model):
    id = db.Column(db.Integer, db.ForeignKey('user.id'), primary_key=True)
    name = db.Column(db.String(100))
    contact = db.Column(db.String(15))
    address = db.Column(db.String(255))
    age = db.Column(db.Integer)
    gender = db.Column(db.String(20))
    height = db.Column(db.Float)
    weight = db.Column(db.Float)
    is_blacklisted = db.Column(db.Boolean, default=False)


class Appointment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    patient_id = db.Column(db.Integer, db.ForeignKey('patient.id'))
    doctor_id = db.Column(db.Integer, db.ForeignKey('doctor.id'))
    date = db.Column(db.DateTime, nullable=False)
    time = db.Column(db.String(8), nullable=False)
    reason = db.Column(db.Text, nullable=False)
    status = db.Column(db.String(50), default='Pending')
    notes = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=db.func.current_timestamp())
    updated_at = db.Column(db.DateTime, default=db.func.current_timestamp(), onupdate=db.func.current_timestamp())
    reschedule_count = db.Column(db.Integer, default=0, nullable=False)
    last_rescheduled_at = db.Column(db.DateTime, nullable=True)
    no_show_at = db.Column(db.DateTime, nullable=True)

    patient = db.relationship('Patient', backref=db.backref('appointments', lazy=True))
    doctor = db.relationship('Doctor', backref=db.backref('appointments', lazy=True))

    @property
    def active_prescription(self):
        return next((p for p in self.prescriptions if not getattr(p, 'is_deleted', False)), None)


class Admission(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    patient_id = db.Column(db.Integer, db.ForeignKey('patient.id'), nullable=False, index=True)
    doctor_id = db.Column(db.Integer, db.ForeignKey('doctor.id'), nullable=False, index=True)
    department_id = db.Column(db.Integer, db.ForeignKey('department.id'), nullable=False, index=True)
    ward_id = db.Column(db.Integer, db.ForeignKey('ward.id'), nullable=False, index=True)
    bed_id = db.Column(db.Integer, db.ForeignKey('bed.id'), nullable=False, index=True)
    appointment_id = db.Column(db.Integer, db.ForeignKey('appointment.id'), nullable=True, index=True)
    admitted_at = db.Column(db.DateTime, default=db.func.current_timestamp(), nullable=False, index=True)
    reason = db.Column(db.Text, nullable=False)
    diagnosis = db.Column(db.Text, nullable=True)
    status = db.Column(db.String(20), default='Active', nullable=False, index=True)
    discharged_at = db.Column(db.DateTime, nullable=True)
    discharge_summary = db.Column(db.Text, nullable=True)
    created_by_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    discharged_by_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=db.func.current_timestamp(), nullable=False)
    updated_at = db.Column(db.DateTime, default=db.func.current_timestamp(), onupdate=db.func.current_timestamp())

    patient = db.relationship('Patient', backref=db.backref('admissions', lazy=True), foreign_keys=[patient_id])
    doctor = db.relationship('Doctor', backref=db.backref('admissions', lazy=True), foreign_keys=[doctor_id])
    department = db.relationship('Department', backref=db.backref('admissions', lazy=True), foreign_keys=[department_id])
    ward = db.relationship('Ward', backref=db.backref('admissions', lazy=True), foreign_keys=[ward_id])
    bed = db.relationship('Bed', backref=db.backref('admissions', lazy=True), foreign_keys=[bed_id])
    appointment = db.relationship('Appointment', backref=db.backref('admissions', lazy=True), foreign_keys=[appointment_id])
    created_by = db.relationship('User', foreign_keys=[created_by_id])
    discharged_by = db.relationship('User', foreign_keys=[discharged_by_id])

    __table_args__ = (
        db.Index(
            'ix_admission_active_patient_unique',
            'patient_id',
            unique=True,
            sqlite_where=text("status = 'Active'"),
            postgresql_where=text("status = 'Active'"),
        ),
        db.Index(
            'ix_admission_active_bed_unique',
            'bed_id',
            unique=True,
            sqlite_where=text("status = 'Active'"),
            postgresql_where=text("status = 'Active'"),
        ),
    )


class BedTransfer(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    admission_id = db.Column(db.Integer, db.ForeignKey('admission.id'), nullable=False, index=True)
    from_ward_id = db.Column(db.Integer, db.ForeignKey('ward.id'), nullable=False)
    from_bed_id = db.Column(db.Integer, db.ForeignKey('bed.id'), nullable=False)
    to_ward_id = db.Column(db.Integer, db.ForeignKey('ward.id'), nullable=False)
    to_bed_id = db.Column(db.Integer, db.ForeignKey('bed.id'), nullable=False)
    reason = db.Column(db.String(500), nullable=True)
    transferred_at = db.Column(db.DateTime, default=db.func.current_timestamp(), nullable=False, index=True)
    transferred_by_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)

    admission = db.relationship('Admission', backref=db.backref('transfers', lazy=True, cascade='all, delete-orphan'))
    from_ward = db.relationship('Ward', foreign_keys=[from_ward_id])
    from_bed = db.relationship('Bed', foreign_keys=[from_bed_id])
    to_ward = db.relationship('Ward', foreign_keys=[to_ward_id])
    to_bed = db.relationship('Bed', foreign_keys=[to_bed_id])
    transferred_by = db.relationship('User', foreign_keys=[transferred_by_id])


class Prescription(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    appointment_id = db.Column(db.Integer, db.ForeignKey('appointment.id'), nullable=False)
    diagnosis = db.Column(db.Text, nullable=False)
    advice = db.Column(db.Text, nullable=True)
    follow_up_date = db.Column(db.Date, nullable=True)
    is_deleted = db.Column(db.Boolean, default=False, nullable=False)
    deleted_at = db.Column(db.DateTime, nullable=True)
    deleted_by = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=db.func.current_timestamp())
    updated_at = db.Column(db.DateTime, default=db.func.current_timestamp(), onupdate=db.func.current_timestamp())

    appointment = db.relationship('Appointment', backref=db.backref('prescriptions', lazy=True))
    items = db.relationship('PrescriptionItem', backref='prescription', lazy=True, cascade='all, delete-orphan')


class PrescriptionItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    prescription_id = db.Column(db.Integer, db.ForeignKey('prescription.id'), nullable=False)
    medicine = db.Column(db.String(200), nullable=False)
    dosage = db.Column(db.String(100), nullable=True)
    frequency = db.Column(db.String(100), nullable=True)
    duration = db.Column(db.String(100), nullable=True)
    quantity = db.Column(db.Integer, nullable=True)
    instructions = db.Column(db.String(255), nullable=True)


class DoctorAvailability(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    doctor_id = db.Column(db.Integer, db.ForeignKey('doctor.id'), nullable=False)
    date = db.Column(db.Date, nullable=False)
    start_time = db.Column(db.String(5), nullable=False)
    end_time = db.Column(db.String(5), nullable=False)
    is_available = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=db.func.current_timestamp())
    updated_at = db.Column(db.DateTime, default=db.func.current_timestamp(), onupdate=db.func.current_timestamp())
    doctor = db.relationship('Doctor', backref=db.backref('availability', lazy=True))


class Notification(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False, index=True)
    title = db.Column(db.String(160), nullable=False)
    message = db.Column(db.String(500), nullable=False)
    category = db.Column(db.String(40), default='info', nullable=False)
    target_url = db.Column(db.String(300), nullable=True)
    is_read = db.Column(db.Boolean, default=False, nullable=False)
    created_at = db.Column(db.DateTime, default=db.func.current_timestamp(), nullable=False)
    user = db.relationship('User', backref=db.backref('notifications', lazy=True, cascade='all, delete-orphan'))


class AppointmentReminder(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    appointment_id = db.Column(db.Integer, db.ForeignKey('appointment.id'), nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False, index=True)
    reminder_type = db.Column(db.String(20), nullable=False)
    # Snapshot of the schedule this reminder belongs to. This is essential
    # for rescheduling: a new schedule may legitimately receive the same
    # reminder type again without deleting the old delivery history.
    scheduled_for = db.Column(db.DateTime, nullable=False)
    sent_at = db.Column(db.DateTime, nullable=False)
    email_attempted_at = db.Column(db.DateTime, nullable=True)
    email_sent = db.Column(db.Boolean, default=False, nullable=False)

    appointment = db.relationship('Appointment', backref=db.backref('reminders', lazy=True, cascade='all, delete-orphan'))
    user = db.relationship('User', backref=db.backref('appointment_reminders', lazy=True, cascade='all, delete-orphan'))

    __table_args__ = (
        db.UniqueConstraint(
            'appointment_id', 'user_id', 'reminder_type', 'scheduled_for',
            name='uq_appointment_reminder_delivery',
        ),
    )


class WaitlistEntry(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    patient_id = db.Column(db.Integer, db.ForeignKey('patient.id'), nullable=False, index=True)
    doctor_id = db.Column(db.Integer, db.ForeignKey('doctor.id'), nullable=False, index=True)
    target_date = db.Column(db.Date, nullable=False, index=True)
    reason = db.Column(db.Text, nullable=False)
    status = db.Column(db.String(20), default='Waiting', nullable=False, index=True)
    offered_slot = db.Column(db.DateTime, nullable=True)
    offered_at = db.Column(db.DateTime, nullable=True)
    offer_expires_at = db.Column(db.DateTime, nullable=True, index=True)
    booked_appointment_id = db.Column(db.Integer, db.ForeignKey('appointment.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=db.func.current_timestamp(), nullable=False)
    updated_at = db.Column(db.DateTime, default=db.func.current_timestamp(), onupdate=db.func.current_timestamp())

    patient = db.relationship('Patient', foreign_keys=[patient_id], backref=db.backref('waitlist_entries', lazy=True))
    doctor = db.relationship('Doctor', foreign_keys=[doctor_id], backref=db.backref('waitlist_entries', lazy=True))
    booked_appointment = db.relationship('Appointment', foreign_keys=[booked_appointment_id])

    __table_args__ = (
        db.Index(
            'ix_waitlist_active_unique',
            'patient_id', 'doctor_id', 'target_date',
            unique=True,
            sqlite_where=text("status IN ('Waiting', 'Offered')"),
        ),
    )


class AuditLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True, index=True)
    actor_username = db.Column(db.String(100), nullable=False)
    actor_role = db.Column(db.String(50), nullable=False)
    action = db.Column(db.String(80), nullable=False, index=True)
    entity_type = db.Column(db.String(80), nullable=True)
    entity_id = db.Column(db.Integer, nullable=True)
    description = db.Column(db.String(500), nullable=False)
    created_at = db.Column(db.DateTime, default=db.func.current_timestamp(), nullable=False)
    user = db.relationship('User', backref=db.backref('audit_logs', lazy=True))


class LoginAttempt(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(100), nullable=False, index=True)
    ip_fingerprint = db.Column(db.String(32), nullable=False, index=True)
    success = db.Column(db.Boolean, default=False, nullable=False)
    attempted_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False, index=True)
