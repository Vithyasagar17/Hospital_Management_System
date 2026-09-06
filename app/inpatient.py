"""Ward and bed infrastructure helpers for Phase 6B.1."""
from collections import Counter

from app.models import Bed, Ward


WARD_TYPES = ('General', 'ICU', 'Private', 'Emergency', 'Other')
BED_STATUSES = ('Available', 'Reserved', 'Occupied', 'Maintenance')
ADMIN_SETTABLE_BED_STATUSES = ('Available', 'Reserved', 'Maintenance')


def ward_snapshot(ward_id):
    """Return bed-capacity and availability metrics for one ward."""
    ward = Ward.query.get(ward_id)
    if not ward:
        return None

    beds = Bed.query.filter_by(ward_id=ward.id).order_by(Bed.bed_number).all()
    counts = Counter(bed.status for bed in beds)
    capacity = len(beds)
    occupied = counts.get('Occupied', 0)
    reserved = counts.get('Reserved', 0)
    available = counts.get('Available', 0)
    maintenance = counts.get('Maintenance', 0)
    usable = max(capacity - maintenance, 0)
    occupancy_rate = round((occupied / usable) * 100, 1) if usable else 0.0

    return {
        'ward': ward,
        'capacity': capacity,
        'available': available,
        'reserved': reserved,
        'occupied': occupied,
        'maintenance': maintenance,
        'usable': usable,
        'occupancy_rate': occupancy_rate,
    }


def hospital_bed_snapshot():
    """Return hospital-wide bed metrics used by the Admin dashboard."""
    wards = Ward.query.all()
    beds = Bed.query.all()
    counts = Counter(bed.status for bed in beds)
    maintenance = counts.get('Maintenance', 0)
    occupied = counts.get('Occupied', 0)
    usable = max(len(beds) - maintenance, 0)

    return {
        'total_wards': len(wards),
        'active_wards': sum(1 for ward in wards if ward.is_active),
        'total_beds': len(beds),
        'available': counts.get('Available', 0),
        'reserved': counts.get('Reserved', 0),
        'occupied': occupied,
        'maintenance': maintenance,
        'occupancy_rate': round((occupied / usable) * 100, 1) if usable else 0.0,
    }


def department_bed_snapshot(department_id):
    """Aggregate ward and bed capacity for a department."""
    wards = Ward.query.filter_by(department_id=department_id).order_by(Ward.name).all()
    snapshots = [ward_snapshot(ward.id) for ward in wards]
    return {
        'wards': snapshots,
        'ward_count': len(wards),
        'active_wards': sum(1 for ward in wards if ward.is_active),
        'total_beds': sum(row['capacity'] for row in snapshots),
        'available_beds': sum(row['available'] for row in snapshots),
        'reserved_beds': sum(row['reserved'] for row in snapshots),
        'occupied_beds': sum(row['occupied'] for row in snapshots),
        'maintenance_beds': sum(row['maintenance'] for row in snapshots),
    }
