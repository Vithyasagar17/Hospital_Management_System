import os
from datetime import datetime, timedelta
from app import create_app, db
from app.models import User, Specialization, Doctor, Patient, DoctorAvailability, Appointment, Prescription, PrescriptionItem

app = create_app()

with app.app_context():
    os.makedirs(app.instance_path, exist_ok=True)

    db_path = os.path.join(app.instance_path, 'hms.db')

    if os.path.exists(db_path):
        os.remove(db_path)

    db.create_all()

    from sqlalchemy import text

    try:
        existing_appt_cols = {row[1] for row in db.session.execute(text("PRAGMA table_info('appointment')")).fetchall()}
    except Exception:
        existing_appt_cols = set()

    appt_extras = {
        'notes': 'TEXT',
        'created_at': 'DATETIME',
        'updated_at': 'DATETIME'
    }

    for col, sqltype in appt_extras.items():
        if col not in existing_appt_cols:
            try:
                db.session.execute(text(f"ALTER TABLE appointment ADD COLUMN {col} {sqltype}"))
            except Exception as e:
                _ = e
    db.session.commit()

    try:
        existing_cols = {row[1] for row in db.session.execute(text("PRAGMA table_info('patient')")).fetchall()}
    except Exception:
        existing_cols = set()

    extras = {
        'age': 'INTEGER',
        'gender': 'VARCHAR(20)',
        'height': 'REAL',
        'weight': 'REAL',
        'is_blacklisted': 'BOOLEAN',
    }

    for col, sqltype in extras.items():
        if col not in existing_cols:
            try:
                db.session.execute(text(f"ALTER TABLE patient ADD COLUMN {col} {sqltype}"))
            except Exception as e:
                _ = e
    db.session.commit()

    try:
        existing_doctor_cols = {row[1] for row in db.session.execute(text("PRAGMA table_info('doctor')")).fetchall()}
    except Exception:
        existing_doctor_cols = set()

    doctor_extras = {
        'is_blacklisted': 'BOOLEAN',
    }

    for col, sqltype in doctor_extras.items():
        if col not in existing_doctor_cols:
            try:
                db.session.execute(text(f"ALTER TABLE doctor ADD COLUMN {col} {sqltype}"))
            except Exception as e:
                _ = e
    db.session.commit()

    if not User.query.filter_by(username='admin').first():
        admin = User(username='admin', role='Admin')
        admin.set_password('supersecretadmin')
        db.session.add(admin)

    # Create specializations
    specializations_list = [
        ('General Medicine', 'Primary Care and General Health'),
        ('Cardiology', 'Heart and Cardiovascular Health'),
        ('Neurology', 'Brain and Nervous System'),
        ('Orthopedics', 'Bones and Joints'),
        ('Pediatrics', 'Children Health'),
        ('Dermatology', 'Skin Health'),
    ]

    for spec_name, spec_desc in specializations_list:
        if not Specialization.query.filter_by(name=spec_name).first():
            specialization = Specialization(name=spec_name, description=spec_desc)
            db.session.add(specialization)

    db.session.commit()

    if not User.query.filter_by(username='dr_sample').first():
        doctor_user = User(username='dr_sample', role='Doctor')
        doctor_user.set_password('doctorpass')
        db.session.add(doctor_user)
        db.session.commit()

        gen_med = Specialization.query.filter_by(name='General Medicine').first()
        doctor = Doctor(id=doctor_user.id, name='Alice Smith', specialization_id=gen_med.id if gen_med else None)
        db.session.add(doctor)
        db.session.commit()

    # Seed demo booking windows for the sample doctor so the live-slot workflow
    # is immediately usable after recreating the database.
    sample_doctor_user = User.query.filter_by(username='dr_sample').first()
    if sample_doctor_user:
        start_day = datetime.now().date()
        for offset in range(7):
            day = start_day + timedelta(days=offset)
            if day.weekday() == 6:  # Sunday
                continue
            for start_time, end_time in [('09:00', '12:00'), ('14:00', '17:00')]:
                db.session.add(DoctorAvailability(
                    doctor_id=sample_doctor_user.id,
                    date=day,
                    start_time=start_time,
                    end_time=end_time,
                    is_available=True
                ))
        db.session.commit()

    if not User.query.filter_by(username='patient_sample').first():
        patient_user = User(username='patient_sample', role='Patient')
        patient_user.set_password('patientpass')
        db.session.add(patient_user)
        db.session.commit()

        patient = Patient(id=patient_user.id, name='Kumar', age=35, height=175, weight=75, contact='9876543210', address='123 Main St')
        db.session.add(patient)
        db.session.commit()

    # Phase 2 demo record: a completed visit with a structured prescription.
    sample_doctor_user = User.query.filter_by(username='dr_sample').first()
    sample_patient_user = User.query.filter_by(username='patient_sample').first()
    if sample_doctor_user and sample_patient_user and not Appointment.query.first():
        visit_time = datetime.now().replace(hour=10, minute=0, second=0, microsecond=0) - timedelta(days=7)
        visit = Appointment(
            patient_id=sample_patient_user.id,
            doctor_id=sample_doctor_user.id,
            date=visit_time,
            time='10:00',
            reason='Fever, fatigue and mild body ache for two days',
            status='Completed',
            notes='Vitals stable. Hydration advised; return if fever persists beyond 3 days.'
        )
        db.session.add(visit)
        db.session.commit()

        rx = Prescription(
            appointment_id=visit.id,
            diagnosis='Acute viral fever',
            advice='Rest, maintain oral fluids, light diet, and monitor temperature twice daily.',
            follow_up_date=(visit_time + timedelta(days=5)).date()
        )
        db.session.add(rx)
        db.session.commit()
        db.session.add(PrescriptionItem(
            prescription_id=rx.id,
            medicine='Paracetamol', dosage='500 mg', frequency='1 tablet every 8 hours if fever',
            duration='3 days', quantity=9, instructions='Take after food; do not exceed advised dose.'
        ))
        db.session.commit()

    print("Database created successfully!")
