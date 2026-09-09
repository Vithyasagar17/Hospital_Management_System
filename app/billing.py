"""Billing and invoice helpers for Phase 6D.

Invoices snapshot billable prices at generation time. Clinical source records remain
independent from financial records, while source identifiers prevent accidental
double billing of the same consultation, laboratory item, or inpatient stay.
Helpers intentionally avoid committing so routes can persist billing, audit and
notification changes in one transaction.
"""
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from math import ceil

from app import db
from app.models import (
    Admission, Appointment, BillingService, Invoice, InvoiceItem, LabOrder,
    LabOrderItem, Patient, Payment,
)

INVOICE_STATUSES = ('Draft', 'Issued', 'Partially Paid', 'Paid', 'Void')
PAYMENT_METHODS = ('Cash', 'Card', 'UPI', 'Bank Transfer', 'Insurance', 'Other')
MONEY = Decimal('0.01')


def money(value):
    if value is None or value == '':
        return Decimal('0.00')
    try:
        return Decimal(str(value)).quantize(MONEY, rounding=ROUND_HALF_UP)
    except (InvalidOperation, ValueError, TypeError):
        raise ValueError('Enter a valid monetary amount.')


def parse_nonnegative_money(value, label='Amount'):
    amount = money(value)
    if amount < 0:
        raise ValueError(f'{label} cannot be negative.')
    return amount


def _item_amount(quantity, unit_price):
    return (Decimal(str(quantity)) * money(unit_price)).quantize(MONEY, rounding=ROUND_HALF_UP)


def refresh_invoice_totals(invoice):
    subtotal = sum((money(item.amount) for item in invoice.items), Decimal('0.00'))
    discount = min(parse_nonnegative_money(invoice.discount or 0, 'Discount'), subtotal)
    total = (subtotal - discount).quantize(MONEY)
    paid = sum((money(payment.amount) for payment in invoice.payments), Decimal('0.00'))
    balance = max(total - paid, Decimal('0.00')).quantize(MONEY)

    invoice.subtotal = subtotal
    invoice.discount = discount
    invoice.total = total
    invoice.amount_paid = paid
    invoice.balance_due = balance

    if invoice.status not in ('Draft', 'Void'):
        if total > 0 and paid >= total:
            invoice.status = 'Paid'
            invoice.paid_at = invoice.paid_at or datetime.utcnow()
        elif paid > 0:
            invoice.status = 'Partially Paid'
            invoice.paid_at = None
        else:
            invoice.status = 'Issued'
            invoice.paid_at = None
    db.session.flush()
    return invoice


def _source_already_billed(source_type, source_id, exclude_invoice_id=None):
    query = InvoiceItem.query.join(Invoice, InvoiceItem.invoice_id == Invoice.id).filter(
        InvoiceItem.source_type == source_type,
        InvoiceItem.source_id == source_id,
        Invoice.status != 'Void',
    )
    if exclude_invoice_id is not None:
        query = query.filter(Invoice.id != exclude_invoice_id)
    return query.first() is not None


def add_invoice_item(invoice, *, description, quantity=1, unit_price=0,
                     source_type=None, source_id=None):
    if invoice.status != 'Draft':
        raise ValueError('Only draft invoices can be edited.')
    description = (description or '').strip()
    if not description:
        raise ValueError('Invoice item description is required.')
    try:
        quantity = Decimal(str(quantity))
    except (InvalidOperation, ValueError, TypeError):
        raise ValueError('Quantity must be a positive number.')
    if quantity <= 0:
        raise ValueError('Quantity must be greater than zero.')
    unit_price = parse_nonnegative_money(unit_price, 'Unit price')

    if source_type and source_id and source_type in {'Appointment', 'LabOrderItem', 'AdmissionRoom'}:
        if _source_already_billed(source_type, int(source_id), exclude_invoice_id=invoice.id):
            raise ValueError('That clinical charge is already present on another active invoice.')

    item = InvoiceItem(
        invoice=invoice,
        description=description,
        quantity=quantity,
        unit_price=unit_price,
        amount=_item_amount(quantity, unit_price),
        source_type=source_type,
        source_id=source_id,
    )
    db.session.add(item)
    db.session.flush()
    refresh_invoice_totals(invoice)
    return item


def create_invoice(*, patient_id, appointment_id=None, admission_id=None, notes=None):
    patient = db.session.get(Patient, patient_id)
    if not patient:
        raise ValueError('Choose a valid patient.')
    if appointment_id and admission_id:
        raise ValueError('An invoice can originate from either an appointment or an admission, not both.')

    appointment = None
    admission = None
    if appointment_id:
        appointment = db.session.get(Appointment, appointment_id)
        if not appointment or appointment.patient_id != patient.id:
            raise ValueError('The selected appointment does not belong to this patient.')
        if appointment.status != 'Completed':
            raise ValueError('Only completed appointments can generate consultation billing.')
    if admission_id:
        admission = db.session.get(Admission, admission_id)
        if not admission or admission.patient_id != patient.id:
            raise ValueError('The selected admission does not belong to this patient.')
        if admission.status != 'Discharged':
            raise ValueError('Discharge the inpatient stay before generating its final invoice.')

    invoice = Invoice(
        patient_id=patient.id,
        appointment_id=appointment.id if appointment else None,
        admission_id=admission.id if admission else None,
        status='Draft',
        notes=(notes or '').strip() or None,
        subtotal=Decimal('0.00'), discount=Decimal('0.00'), total=Decimal('0.00'),
        amount_paid=Decimal('0.00'), balance_due=Decimal('0.00'),
    )
    db.session.add(invoice)
    db.session.flush()
    invoice.invoice_number = f'INV-{datetime.now().year}-{invoice.id:06d}'

    if appointment:
        _populate_appointment_charges(invoice, appointment)
    if admission:
        _populate_admission_charges(invoice, admission)
    if (appointment or admission) and InvoiceItem.query.filter_by(invoice_id=invoice.id).count() == 0:
        raise ValueError('No unbilled configured charges remain for that clinical source. Use a manual invoice if needed.')
    refresh_invoice_totals(invoice)
    return invoice


def _populate_lab_charges(invoice, orders):
    for order in orders:
        if order.status != 'Completed':
            continue
        for item in order.items:
            if _source_already_billed('LabOrderItem', item.id, exclude_invoice_id=invoice.id):
                continue
            price = item.price_snapshot
            if price is None and item.lab_test:
                price = item.lab_test.base_price
            price = money(price)
            if price <= 0:
                continue
            add_invoice_item(
                invoice,
                description=f'Laboratory · {item.test_name_snapshot}',
                quantity=1,
                unit_price=price,
                source_type='LabOrderItem', source_id=item.id,
            )


def _populate_appointment_charges(invoice, appointment):
    fee = money(appointment.doctor.consultation_fee if appointment.doctor else 0)
    if fee > 0 and not _source_already_billed('Appointment', appointment.id, exclude_invoice_id=invoice.id):
        add_invoice_item(
            invoice,
            description=f'Consultation · Dr. {appointment.doctor.name or "Doctor"}',
            quantity=1, unit_price=fee,
            source_type='Appointment', source_id=appointment.id,
        )
    _populate_lab_charges(invoice, LabOrder.query.filter_by(appointment_id=appointment.id).all())


def _admission_room_charge(admission):
    """Return total inpatient room charge and a human-readable breakdown."""
    end_at = admission.discharged_at or datetime.utcnow()
    transfers = sorted(admission.transfers, key=lambda row: row.transferred_at)
    segments = []
    start_at = admission.admitted_at
    current_ward = transfers[0].from_ward if transfers else admission.ward
    current_rate = admission.room_rate_snapshot
    if current_rate is None and current_ward:
        current_rate = current_ward.daily_rate

    for transfer in transfers:
        rate = transfer.from_daily_rate_snapshot
        if rate is None:
            rate = current_rate if current_rate is not None else (transfer.from_ward.daily_rate if transfer.from_ward else 0)
        segments.append((current_ward or transfer.from_ward, start_at, transfer.transferred_at, money(rate)))
        start_at = transfer.transferred_at
        current_ward = transfer.to_ward
        current_rate = transfer.to_daily_rate_snapshot
        if current_rate is None and current_ward:
            current_rate = current_ward.daily_rate

    if current_ward:
        segments.append((current_ward, start_at, end_at, money(current_rate or current_ward.daily_rate)))

    total = Decimal('0.00')
    breakdown = []
    for ward, segment_start, segment_end, rate in segments:
        seconds = max((segment_end - segment_start).total_seconds(), 0)
        days = max(1, ceil(seconds / 86400))
        charge = (rate * days).quantize(MONEY)
        total += charge
        breakdown.append(f'{ward.name}: {days} day{"s" if days != 1 else ""} × ₹{rate:.2f}')
    return total.quantize(MONEY), '; '.join(breakdown)


def _populate_admission_charges(invoice, admission):
    if not _source_already_billed('AdmissionRoom', admission.id, exclude_invoice_id=invoice.id):
        room_total, breakdown = _admission_room_charge(admission)
        if room_total > 0:
            add_invoice_item(
                invoice,
                description=f'Inpatient room/bed charges · {breakdown}',
                quantity=1, unit_price=room_total,
                source_type='AdmissionRoom', source_id=admission.id,
            )
    _populate_lab_charges(invoice, LabOrder.query.filter_by(admission_id=admission.id).all())


def add_service_to_invoice(invoice, service_id, quantity=1):
    service = db.session.get(BillingService, service_id)
    if not service or not service.is_active:
        raise ValueError('Choose an active billing service.')
    return add_invoice_item(
        invoice,
        description=f'{service.category or "Service"} · {service.name}',
        quantity=quantity,
        unit_price=service.unit_price,
        source_type='BillingService', source_id=service.id,
    )


def save_invoice_draft(invoice, *, discount=0, due_date=None, notes=None):
    if invoice.status != 'Draft':
        raise ValueError('Only draft invoices can be changed.')
    invoice.discount = parse_nonnegative_money(discount, 'Discount')
    invoice.notes = (notes or '').strip() or None
    if due_date:
        try:
            invoice.due_at = datetime.strptime(due_date, '%Y-%m-%d')
        except ValueError:
            raise ValueError('Choose a valid due date.')
    else:
        invoice.due_at = None
    refresh_invoice_totals(invoice)
    return invoice


def issue_invoice(invoice):
    if invoice.status != 'Draft':
        raise ValueError('Only draft invoices can be issued.')
    refresh_invoice_totals(invoice)
    if not invoice.items:
        raise ValueError('Add at least one charge before issuing the invoice.')
    if money(invoice.total) <= 0:
        raise ValueError('Invoice total must be greater than zero before issue.')
    invoice.status = 'Issued'
    invoice.issued_at = datetime.utcnow()
    if not invoice.due_at:
        invoice.due_at = datetime.utcnow() + timedelta(days=14)
    refresh_invoice_totals(invoice)
    return invoice


def record_payment(invoice, *, amount, method, reference=None, received_by_id=None):
    if invoice.status not in ('Issued', 'Partially Paid'):
        raise ValueError('Payments can only be recorded against an issued unpaid invoice.')
    if method not in PAYMENT_METHODS:
        raise ValueError('Choose a valid payment method.')
    amount = parse_nonnegative_money(amount, 'Payment amount')
    if amount <= 0:
        raise ValueError('Payment amount must be greater than zero.')
    refresh_invoice_totals(invoice)
    if amount > money(invoice.balance_due):
        raise ValueError('Payment cannot exceed the outstanding balance.')

    payment = Payment(
        invoice=invoice,
        amount=amount,
        method=method,
        reference=(reference or '').strip() or None,
        received_by_id=received_by_id,
        received_at=datetime.utcnow(),
    )
    db.session.add(payment)
    db.session.flush()
    refresh_invoice_totals(invoice)
    return payment


def void_invoice(invoice, reason=None):
    if invoice.status not in ('Draft', 'Issued'):
        raise ValueError('Only draft or unpaid issued invoices can be voided.')
    if invoice.payments:
        raise ValueError('Invoices with payments cannot be voided.')
    invoice.status = 'Void'
    invoice.voided_at = datetime.utcnow()
    invoice.void_reason = (reason or '').strip() or None
    invoice.balance_due = Decimal('0.00')
    db.session.flush()
    return invoice


def billing_summary(days=30):
    start = datetime.utcnow() - timedelta(days=days)
    active = Invoice.query.filter(Invoice.status.in_(['Issued', 'Partially Paid', 'Paid'])).all()
    outstanding = sum((money(row.balance_due) for row in active), Decimal('0.00'))
    payments = Payment.query.filter(Payment.received_at >= start).all()
    collected = sum((money(row.amount) for row in payments), Decimal('0.00'))
    issued = Invoice.query.filter(Invoice.issued_at >= start, Invoice.status != 'Void').all()
    issued_value = sum((money(row.total) for row in issued), Decimal('0.00'))
    return {
        'outstanding': outstanding.quantize(MONEY),
        'collected': collected.quantize(MONEY),
        'issued_value': issued_value.quantize(MONEY),
        'unpaid_count': Invoice.query.filter(Invoice.status.in_(['Issued', 'Partially Paid'])).count(),
        'paid_count': Invoice.query.filter_by(status='Paid').count(),
        'draft_count': Invoice.query.filter_by(status='Draft').count(),
    }
