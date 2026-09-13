"""Phase 6 schema baseline for Alembic-managed databases.

Revision ID: 20260910_0001
Revises:
Create Date: 2026-09-10
"""
from alembic import op
import sqlalchemy as sa

revision = '20260910_0001'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('user',
        sa.Column('id', sa.Integer(), primary_key=True, nullable=False),
        sa.Column('username', sa.String(100), nullable=False, unique=True),
        sa.Column('email', sa.String(255), nullable=True, unique=True),
        sa.Column('email_verified', sa.Boolean(), nullable=False),
        sa.Column('password_hash', sa.String(255), nullable=False),
        sa.Column('role', sa.String(50), nullable=False),
        sa.Column('failed_login_count', sa.Integer(), nullable=False),
        sa.Column('locked_until', sa.DateTime(), nullable=True),
        sa.Column('last_login_at', sa.DateTime(), nullable=True),
        sa.Column('password_changed_at', sa.DateTime(), nullable=True),
        sa.Column('session_version', sa.Integer(), nullable=False),
    )

    op.create_table('specialization',
        sa.Column('id', sa.Integer(), primary_key=True, nullable=False),
        sa.Column('name', sa.String(100), nullable=False, unique=True),
        sa.Column('description', sa.String(255)),
    )

    op.create_table('department',
        sa.Column('id', sa.Integer(), primary_key=True, nullable=False),
        sa.Column('name', sa.String(120), nullable=False, unique=True),
        sa.Column('code', sa.String(20), nullable=False, unique=True),
        sa.Column('description', sa.String(500), nullable=True),
        sa.Column('location', sa.String(120), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False),
        sa.Column('head_doctor_id', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime()),
    )

    op.create_table('doctor',
        sa.Column('id', sa.Integer(), sa.ForeignKey('user.id'), primary_key=True, nullable=False),
        sa.Column('name', sa.String(100)),
        sa.Column('specialization_id', sa.Integer(), sa.ForeignKey('specialization.id')),
        sa.Column('department_id', sa.Integer(), sa.ForeignKey('department.id'), nullable=True),
        sa.Column('is_blacklisted', sa.Boolean()),
        sa.Column('consultation_fee', sa.Numeric(10, 2), nullable=True),
    )

    op.create_table('patient',
        sa.Column('id', sa.Integer(), sa.ForeignKey('user.id'), primary_key=True, nullable=False),
        sa.Column('name', sa.String(100)),
        sa.Column('contact', sa.String(15)),
        sa.Column('address', sa.String(255)),
        sa.Column('age', sa.Integer()),
        sa.Column('gender', sa.String(20)),
        sa.Column('height', sa.Float()),
        sa.Column('weight', sa.Float()),
        sa.Column('is_blacklisted', sa.Boolean()),
    )

    op.create_table('ward',
        sa.Column('id', sa.Integer(), primary_key=True, nullable=False),
        sa.Column('department_id', sa.Integer(), sa.ForeignKey('department.id'), nullable=False),
        sa.Column('name', sa.String(120), nullable=False),
        sa.Column('code', sa.String(30), nullable=False, unique=True),
        sa.Column('ward_type', sa.String(30), nullable=False),
        sa.Column('location', sa.String(120), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False),
        sa.Column('daily_rate', sa.Numeric(10, 2), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime()),
        sa.UniqueConstraint('department_id', 'name', name='uq_ward_department_name'),
    )

    op.create_table('bed',
        sa.Column('id', sa.Integer(), primary_key=True, nullable=False),
        sa.Column('ward_id', sa.Integer(), sa.ForeignKey('ward.id'), nullable=False),
        sa.Column('bed_number', sa.String(30), nullable=False),
        sa.Column('status', sa.String(20), nullable=False),
        sa.Column('notes', sa.String(255), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime()),
        sa.UniqueConstraint('ward_id', 'bed_number', name='uq_bed_ward_number'),
    )

    op.create_table('appointment',
        sa.Column('id', sa.Integer(), primary_key=True, nullable=False),
        sa.Column('patient_id', sa.Integer(), sa.ForeignKey('patient.id')),
        sa.Column('doctor_id', sa.Integer(), sa.ForeignKey('doctor.id')),
        sa.Column('date', sa.DateTime(), nullable=False),
        sa.Column('time', sa.String(8), nullable=False),
        sa.Column('reason', sa.Text(), nullable=False),
        sa.Column('status', sa.String(50)),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime()),
        sa.Column('updated_at', sa.DateTime()),
        sa.Column('reschedule_count', sa.Integer(), nullable=False),
        sa.Column('last_rescheduled_at', sa.DateTime(), nullable=True),
        sa.Column('no_show_at', sa.DateTime(), nullable=True),
    )

    op.create_table('admission',
        sa.Column('id', sa.Integer(), primary_key=True, nullable=False),
        sa.Column('patient_id', sa.Integer(), sa.ForeignKey('patient.id'), nullable=False),
        sa.Column('doctor_id', sa.Integer(), sa.ForeignKey('doctor.id'), nullable=False),
        sa.Column('department_id', sa.Integer(), sa.ForeignKey('department.id'), nullable=False),
        sa.Column('ward_id', sa.Integer(), sa.ForeignKey('ward.id'), nullable=False),
        sa.Column('bed_id', sa.Integer(), sa.ForeignKey('bed.id'), nullable=False),
        sa.Column('appointment_id', sa.Integer(), sa.ForeignKey('appointment.id'), nullable=True),
        sa.Column('admitted_at', sa.DateTime(), nullable=False),
        sa.Column('reason', sa.Text(), nullable=False),
        sa.Column('diagnosis', sa.Text(), nullable=True),
        sa.Column('status', sa.String(20), nullable=False),
        sa.Column('discharged_at', sa.DateTime(), nullable=True),
        sa.Column('discharge_summary', sa.Text(), nullable=True),
        sa.Column('room_rate_snapshot', sa.Numeric(10, 2), nullable=True),
        sa.Column('created_by_id', sa.Integer(), sa.ForeignKey('user.id'), nullable=True),
        sa.Column('discharged_by_id', sa.Integer(), sa.ForeignKey('user.id'), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime()),
    )

    op.create_table('bed_transfer',
        sa.Column('id', sa.Integer(), primary_key=True, nullable=False),
        sa.Column('admission_id', sa.Integer(), sa.ForeignKey('admission.id'), nullable=False),
        sa.Column('from_ward_id', sa.Integer(), sa.ForeignKey('ward.id'), nullable=False),
        sa.Column('from_bed_id', sa.Integer(), sa.ForeignKey('bed.id'), nullable=False),
        sa.Column('to_ward_id', sa.Integer(), sa.ForeignKey('ward.id'), nullable=False),
        sa.Column('to_bed_id', sa.Integer(), sa.ForeignKey('bed.id'), nullable=False),
        sa.Column('reason', sa.String(500), nullable=True),
        sa.Column('transferred_at', sa.DateTime(), nullable=False),
        sa.Column('transferred_by_id', sa.Integer(), sa.ForeignKey('user.id'), nullable=True),
        sa.Column('from_daily_rate_snapshot', sa.Numeric(10, 2), nullable=True),
        sa.Column('to_daily_rate_snapshot', sa.Numeric(10, 2), nullable=True),
    )

    op.create_table('lab_test',
        sa.Column('id', sa.Integer(), primary_key=True, nullable=False),
        sa.Column('code', sa.String(30), nullable=False, unique=True),
        sa.Column('name', sa.String(160), nullable=False, unique=True),
        sa.Column('category', sa.String(80), nullable=True),
        sa.Column('specimen_type', sa.String(80), nullable=True),
        sa.Column('default_unit', sa.String(40), nullable=True),
        sa.Column('reference_range', sa.String(120), nullable=True),
        sa.Column('base_price', sa.Numeric(10, 2), nullable=True),
        sa.Column('turnaround_hours', sa.Integer(), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime()),
    )

    op.create_table('lab_order',
        sa.Column('id', sa.Integer(), primary_key=True, nullable=False),
        sa.Column('patient_id', sa.Integer(), sa.ForeignKey('patient.id'), nullable=False),
        sa.Column('doctor_id', sa.Integer(), sa.ForeignKey('doctor.id'), nullable=False),
        sa.Column('appointment_id', sa.Integer(), sa.ForeignKey('appointment.id'), nullable=True),
        sa.Column('admission_id', sa.Integer(), sa.ForeignKey('admission.id'), nullable=True),
        sa.Column('priority', sa.String(20), nullable=False),
        sa.Column('status', sa.String(30), nullable=False),
        sa.Column('clinical_notes', sa.Text(), nullable=True),
        sa.Column('specimen_id', sa.String(80), nullable=True, unique=True),
        sa.Column('sample_notes', sa.String(500), nullable=True),
        sa.Column('ordered_at', sa.DateTime(), nullable=False),
        sa.Column('sample_collected_at', sa.DateTime(), nullable=True),
        sa.Column('processing_started_at', sa.DateTime(), nullable=True),
        sa.Column('completed_at', sa.DateTime(), nullable=True),
        sa.Column('cancelled_at', sa.DateTime(), nullable=True),
        sa.Column('cancelled_reason', sa.String(500), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime()),
    )

    op.create_table('lab_order_item',
        sa.Column('id', sa.Integer(), primary_key=True, nullable=False),
        sa.Column('lab_order_id', sa.Integer(), sa.ForeignKey('lab_order.id'), nullable=False),
        sa.Column('lab_test_id', sa.Integer(), sa.ForeignKey('lab_test.id'), nullable=False),
        sa.Column('test_code_snapshot', sa.String(30), nullable=False),
        sa.Column('test_name_snapshot', sa.String(160), nullable=False),
        sa.Column('unit_snapshot', sa.String(40), nullable=True),
        sa.Column('reference_range_snapshot', sa.String(120), nullable=True),
        sa.Column('price_snapshot', sa.Numeric(10, 2), nullable=True),
        sa.Column('result_value', sa.Text(), nullable=True),
        sa.Column('interpretation', sa.String(30), nullable=True),
        sa.Column('result_notes', sa.String(500), nullable=True),
        sa.Column('resulted_at', sa.DateTime(), nullable=True),
        sa.UniqueConstraint('lab_order_id', 'lab_test_id', name='uq_lab_order_test'),
    )

    op.create_table('billing_service',
        sa.Column('id', sa.Integer(), primary_key=True, nullable=False),
        sa.Column('code', sa.String(30), nullable=False, unique=True),
        sa.Column('name', sa.String(160), nullable=False, unique=True),
        sa.Column('category', sa.String(80), nullable=True),
        sa.Column('unit_price', sa.Numeric(10, 2), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime()),
    )

    op.create_table('invoice',
        sa.Column('id', sa.Integer(), primary_key=True, nullable=False),
        sa.Column('invoice_number', sa.String(40), nullable=True, unique=True),
        sa.Column('patient_id', sa.Integer(), sa.ForeignKey('patient.id'), nullable=False),
        sa.Column('appointment_id', sa.Integer(), sa.ForeignKey('appointment.id'), nullable=True),
        sa.Column('admission_id', sa.Integer(), sa.ForeignKey('admission.id'), nullable=True),
        sa.Column('status', sa.String(30), nullable=False),
        sa.Column('subtotal', sa.Numeric(12, 2), nullable=False),
        sa.Column('discount', sa.Numeric(12, 2), nullable=False),
        sa.Column('total', sa.Numeric(12, 2), nullable=False),
        sa.Column('amount_paid', sa.Numeric(12, 2), nullable=False),
        sa.Column('balance_due', sa.Numeric(12, 2), nullable=False),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('issued_at', sa.DateTime(), nullable=True),
        sa.Column('due_at', sa.DateTime(), nullable=True),
        sa.Column('paid_at', sa.DateTime(), nullable=True),
        sa.Column('voided_at', sa.DateTime(), nullable=True),
        sa.Column('void_reason', sa.String(500), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime()),
    )

    op.create_table('invoice_item',
        sa.Column('id', sa.Integer(), primary_key=True, nullable=False),
        sa.Column('invoice_id', sa.Integer(), sa.ForeignKey('invoice.id'), nullable=False),
        sa.Column('description', sa.String(500), nullable=False),
        sa.Column('quantity', sa.Numeric(10, 2), nullable=False),
        sa.Column('unit_price', sa.Numeric(12, 2), nullable=False),
        sa.Column('amount', sa.Numeric(12, 2), nullable=False),
        sa.Column('source_type', sa.String(40), nullable=True),
        sa.Column('source_id', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
    )

    op.create_table('payment',
        sa.Column('id', sa.Integer(), primary_key=True, nullable=False),
        sa.Column('invoice_id', sa.Integer(), sa.ForeignKey('invoice.id'), nullable=False),
        sa.Column('amount', sa.Numeric(12, 2), nullable=False),
        sa.Column('method', sa.String(30), nullable=False),
        sa.Column('reference', sa.String(120), nullable=True),
        sa.Column('received_at', sa.DateTime(), nullable=False),
        sa.Column('received_by_id', sa.Integer(), sa.ForeignKey('user.id'), nullable=True),
    )

    op.create_table('prescription',
        sa.Column('id', sa.Integer(), primary_key=True, nullable=False),
        sa.Column('appointment_id', sa.Integer(), sa.ForeignKey('appointment.id'), nullable=False),
        sa.Column('diagnosis', sa.Text(), nullable=False),
        sa.Column('advice', sa.Text(), nullable=True),
        sa.Column('follow_up_date', sa.Date(), nullable=True),
        sa.Column('is_deleted', sa.Boolean(), nullable=False),
        sa.Column('deleted_at', sa.DateTime(), nullable=True),
        sa.Column('deleted_by', sa.Integer(), sa.ForeignKey('user.id'), nullable=True),
        sa.Column('created_at', sa.DateTime()),
        sa.Column('updated_at', sa.DateTime()),
    )

    op.create_table('prescription_item',
        sa.Column('id', sa.Integer(), primary_key=True, nullable=False),
        sa.Column('prescription_id', sa.Integer(), sa.ForeignKey('prescription.id'), nullable=False),
        sa.Column('medicine', sa.String(200), nullable=False),
        sa.Column('dosage', sa.String(100), nullable=True),
        sa.Column('frequency', sa.String(100), nullable=True),
        sa.Column('duration', sa.String(100), nullable=True),
        sa.Column('quantity', sa.Integer(), nullable=True),
        sa.Column('instructions', sa.String(255), nullable=True),
    )

    op.create_table('doctor_availability',
        sa.Column('id', sa.Integer(), primary_key=True, nullable=False),
        sa.Column('doctor_id', sa.Integer(), sa.ForeignKey('doctor.id'), nullable=False),
        sa.Column('date', sa.Date(), nullable=False),
        sa.Column('start_time', sa.String(5), nullable=False),
        sa.Column('end_time', sa.String(5), nullable=False),
        sa.Column('is_available', sa.Boolean()),
        sa.Column('created_at', sa.DateTime()),
        sa.Column('updated_at', sa.DateTime()),
    )

    op.create_table('notification',
        sa.Column('id', sa.Integer(), primary_key=True, nullable=False),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('user.id'), nullable=False),
        sa.Column('title', sa.String(160), nullable=False),
        sa.Column('message', sa.String(500), nullable=False),
        sa.Column('category', sa.String(40), nullable=False),
        sa.Column('target_url', sa.String(300), nullable=True),
        sa.Column('is_read', sa.Boolean(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
    )

    op.create_table('appointment_reminder',
        sa.Column('id', sa.Integer(), primary_key=True, nullable=False),
        sa.Column('appointment_id', sa.Integer(), sa.ForeignKey('appointment.id'), nullable=False),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('user.id'), nullable=False),
        sa.Column('reminder_type', sa.String(20), nullable=False),
        sa.Column('scheduled_for', sa.DateTime(), nullable=False),
        sa.Column('sent_at', sa.DateTime(), nullable=False),
        sa.Column('email_attempted_at', sa.DateTime(), nullable=True),
        sa.Column('email_sent', sa.Boolean(), nullable=False),
        sa.UniqueConstraint('appointment_id', 'user_id', 'reminder_type', 'scheduled_for', name='uq_appointment_reminder_delivery'),
    )

    op.create_table('waitlist_entry',
        sa.Column('id', sa.Integer(), primary_key=True, nullable=False),
        sa.Column('patient_id', sa.Integer(), sa.ForeignKey('patient.id'), nullable=False),
        sa.Column('doctor_id', sa.Integer(), sa.ForeignKey('doctor.id'), nullable=False),
        sa.Column('target_date', sa.Date(), nullable=False),
        sa.Column('reason', sa.Text(), nullable=False),
        sa.Column('status', sa.String(20), nullable=False),
        sa.Column('offered_slot', sa.DateTime(), nullable=True),
        sa.Column('offered_at', sa.DateTime(), nullable=True),
        sa.Column('offer_expires_at', sa.DateTime(), nullable=True),
        sa.Column('booked_appointment_id', sa.Integer(), sa.ForeignKey('appointment.id'), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime()),
    )

    op.create_table('audit_log',
        sa.Column('id', sa.Integer(), primary_key=True, nullable=False),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('user.id'), nullable=True),
        sa.Column('actor_username', sa.String(100), nullable=False),
        sa.Column('actor_role', sa.String(50), nullable=False),
        sa.Column('action', sa.String(80), nullable=False),
        sa.Column('entity_type', sa.String(80), nullable=True),
        sa.Column('entity_id', sa.Integer(), nullable=True),
        sa.Column('description', sa.String(500), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
    )

    op.create_table('login_attempt',
        sa.Column('id', sa.Integer(), primary_key=True, nullable=False),
        sa.Column('username', sa.String(100), nullable=False),
        sa.Column('ip_fingerprint', sa.String(32), nullable=False),
        sa.Column('success', sa.Boolean(), nullable=False),
        sa.Column('attempted_at', sa.DateTime(), nullable=False),
    )

    # Resolve the Department↔Doctor circular foreign key after both tables exist.
    with op.batch_alter_table('department') as batch_op:
        batch_op.create_foreign_key('fk_department_head_doctor_id_doctor', 'doctor', ['head_doctor_id'], ['id'])

    op.create_index('ix_admission_active_patient_unique', 'admission', ['patient_id'], unique=True, sqlite_where=sa.text("status = 'Active'"), postgresql_where=sa.text("status = 'Active'"))
    op.create_index('ix_admission_active_bed_unique', 'admission', ['bed_id'], unique=True, sqlite_where=sa.text("status = 'Active'"), postgresql_where=sa.text("status = 'Active'"))
    op.create_index('ix_waitlist_active_unique', 'waitlist_entry', ['patient_id', 'doctor_id', 'target_date'], unique=True, sqlite_where=sa.text("status IN ('Waiting', 'Offered')"), postgresql_where=sa.text("status IN ('Waiting', 'Offered')"))
    op.create_index('ix_doctor_department_id', 'doctor', ['department_id'], unique=False)
    op.create_index('ix_ward_department_id', 'ward', ['department_id'], unique=False)
    op.create_index('ix_bed_ward_id', 'bed', ['ward_id'], unique=False)
    op.create_index('ix_bed_status', 'bed', ['status'], unique=False)
    op.create_index('ix_admission_patient_id', 'admission', ['patient_id'], unique=False)
    op.create_index('ix_admission_doctor_id', 'admission', ['doctor_id'], unique=False)
    op.create_index('ix_admission_department_id', 'admission', ['department_id'], unique=False)
    op.create_index('ix_admission_ward_id', 'admission', ['ward_id'], unique=False)
    op.create_index('ix_admission_bed_id', 'admission', ['bed_id'], unique=False)
    op.create_index('ix_admission_appointment_id', 'admission', ['appointment_id'], unique=False)
    op.create_index('ix_admission_admitted_at', 'admission', ['admitted_at'], unique=False)
    op.create_index('ix_admission_status', 'admission', ['status'], unique=False)
    op.create_index('ix_bed_transfer_admission_id', 'bed_transfer', ['admission_id'], unique=False)
    op.create_index('ix_bed_transfer_transferred_at', 'bed_transfer', ['transferred_at'], unique=False)
    op.create_index('ix_lab_test_code', 'lab_test', ['code'], unique=False)
    op.create_index('ix_lab_test_category', 'lab_test', ['category'], unique=False)
    op.create_index('ix_lab_test_is_active', 'lab_test', ['is_active'], unique=False)
    op.create_index('ix_lab_order_patient_id', 'lab_order', ['patient_id'], unique=False)
    op.create_index('ix_lab_order_doctor_id', 'lab_order', ['doctor_id'], unique=False)
    op.create_index('ix_lab_order_appointment_id', 'lab_order', ['appointment_id'], unique=False)
    op.create_index('ix_lab_order_admission_id', 'lab_order', ['admission_id'], unique=False)
    op.create_index('ix_lab_order_priority', 'lab_order', ['priority'], unique=False)
    op.create_index('ix_lab_order_status', 'lab_order', ['status'], unique=False)
    op.create_index('ix_lab_order_specimen_id', 'lab_order', ['specimen_id'], unique=False)
    op.create_index('ix_lab_order_ordered_at', 'lab_order', ['ordered_at'], unique=False)
    op.create_index('ix_lab_order_item_lab_order_id', 'lab_order_item', ['lab_order_id'], unique=False)
    op.create_index('ix_lab_order_item_lab_test_id', 'lab_order_item', ['lab_test_id'], unique=False)
    op.create_index('ix_billing_service_code', 'billing_service', ['code'], unique=False)
    op.create_index('ix_billing_service_category', 'billing_service', ['category'], unique=False)
    op.create_index('ix_billing_service_is_active', 'billing_service', ['is_active'], unique=False)
    op.create_index('ix_invoice_invoice_number', 'invoice', ['invoice_number'], unique=False)
    op.create_index('ix_invoice_patient_id', 'invoice', ['patient_id'], unique=False)
    op.create_index('ix_invoice_appointment_id', 'invoice', ['appointment_id'], unique=False)
    op.create_index('ix_invoice_admission_id', 'invoice', ['admission_id'], unique=False)
    op.create_index('ix_invoice_status', 'invoice', ['status'], unique=False)
    op.create_index('ix_invoice_issued_at', 'invoice', ['issued_at'], unique=False)
    op.create_index('ix_invoice_item_invoice_id', 'invoice_item', ['invoice_id'], unique=False)
    op.create_index('ix_invoice_item_source_type', 'invoice_item', ['source_type'], unique=False)
    op.create_index('ix_invoice_item_source_id', 'invoice_item', ['source_id'], unique=False)
    op.create_index('ix_payment_invoice_id', 'payment', ['invoice_id'], unique=False)
    op.create_index('ix_payment_received_at', 'payment', ['received_at'], unique=False)
    op.create_index('ix_notification_user_id', 'notification', ['user_id'], unique=False)
    op.create_index('ix_appointment_reminder_appointment_id', 'appointment_reminder', ['appointment_id'], unique=False)
    op.create_index('ix_appointment_reminder_user_id', 'appointment_reminder', ['user_id'], unique=False)
    op.create_index('ix_waitlist_entry_patient_id', 'waitlist_entry', ['patient_id'], unique=False)
    op.create_index('ix_waitlist_entry_doctor_id', 'waitlist_entry', ['doctor_id'], unique=False)
    op.create_index('ix_waitlist_entry_target_date', 'waitlist_entry', ['target_date'], unique=False)
    op.create_index('ix_waitlist_entry_status', 'waitlist_entry', ['status'], unique=False)
    op.create_index('ix_waitlist_entry_offer_expires_at', 'waitlist_entry', ['offer_expires_at'], unique=False)
    op.create_index('ix_audit_log_user_id', 'audit_log', ['user_id'], unique=False)
    op.create_index('ix_audit_log_action', 'audit_log', ['action'], unique=False)
    op.create_index('ix_login_attempt_username', 'login_attempt', ['username'], unique=False)
    op.create_index('ix_login_attempt_ip_fingerprint', 'login_attempt', ['ip_fingerprint'], unique=False)
    op.create_index('ix_login_attempt_attempted_at', 'login_attempt', ['attempted_at'], unique=False)


def downgrade():
    with op.batch_alter_table('department') as batch_op:
        batch_op.drop_constraint('fk_department_head_doctor_id_doctor', type_='foreignkey')
    op.drop_table('login_attempt')
    op.drop_table('audit_log')
    op.drop_table('waitlist_entry')
    op.drop_table('appointment_reminder')
    op.drop_table('notification')
    op.drop_table('doctor_availability')
    op.drop_table('prescription_item')
    op.drop_table('prescription')
    op.drop_table('payment')
    op.drop_table('invoice_item')
    op.drop_table('invoice')
    op.drop_table('billing_service')
    op.drop_table('lab_order_item')
    op.drop_table('lab_order')
    op.drop_table('lab_test')
    op.drop_table('bed_transfer')
    op.drop_table('admission')
    op.drop_table('appointment')
    op.drop_table('bed')
    op.drop_table('ward')
    op.drop_table('patient')
    op.drop_table('doctor')
    op.drop_table('department')
    op.drop_table('specialization')
    op.drop_table('user')
