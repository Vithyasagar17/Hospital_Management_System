"""Add composite indexes for production query paths.

Revision ID: 20260910_0002
Revises: 20260910_0001
Create Date: 2026-09-10
"""
from alembic import op

revision = '20260910_0002'
down_revision = '20260910_0001'
branch_labels = None
depends_on = None

INDEXES = (
    ('ix_appointment_doctor_date_status', 'appointment', ['doctor_id', 'date', 'status']),
    ('ix_appointment_patient_date_status', 'appointment', ['patient_id', 'date', 'status']),
    ('ix_admission_department_status_admitted', 'admission', ['department_id', 'status', 'admitted_at']),
    ('ix_lab_order_patient_status_ordered', 'lab_order', ['patient_id', 'status', 'ordered_at']),
    ('ix_lab_order_doctor_status_ordered', 'lab_order', ['doctor_id', 'status', 'ordered_at']),
    ('ix_invoice_patient_status_created', 'invoice', ['patient_id', 'status', 'created_at']),
    ('ix_doctor_availability_doctor_date_available', 'doctor_availability', ['doctor_id', 'date', 'is_available']),
    ('ix_appointment_reminder_schedule_type', 'appointment_reminder', ['scheduled_for', 'reminder_type']),
    ('ix_waitlist_doctor_date_status_created', 'waitlist_entry', ['doctor_id', 'target_date', 'status', 'created_at']),
    ('ix_audit_log_created_action', 'audit_log', ['created_at', 'action']),
)


def upgrade():
    for name, table, columns in INDEXES:
        op.create_index(name, table, columns, unique=False)


def downgrade():
    for name, table, _columns in reversed(INDEXES):
        op.drop_index(name, table_name=table)
