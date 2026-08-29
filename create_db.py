import os
from app import create_app, db
from app.models import User, Specialization, Doctor, Patient, DoctorAvailability

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

    if not User.query.filter_by(username='patient_sample').first():
        patient_user = User(username='patient_sample', role='Patient')
        patient_user.set_password('patientpass')
        db.session.add(patient_user)
        db.session.commit()

        patient = Patient(id=patient_user.id, name='Kumar', age=35, height=175, weight=75, contact='9876543210', address='123 Main St')
        db.session.add(patient)
        db.session.commit()

    print("Database created successfully!")
