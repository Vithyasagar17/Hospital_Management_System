"""Phase 3 activity helpers: notifications and audit logging.

Helpers add records to the current SQLAlchemy transaction but intentionally do
not commit. The calling route commits the business change and its side effects
atomically.
"""
from flask_login import current_user
from app import db
from app.models import AuditLog, Notification, User


def log_activity(action, description, entity_type=None, entity_id=None, actor=None):
    actor = actor or (current_user if getattr(current_user, 'is_authenticated', False) else None)
    username = getattr(actor, 'username', None) or 'system'
    role = getattr(actor, 'role', None) or 'System'
    user_id = getattr(actor, 'id', None)
    entry = AuditLog(
        user_id=user_id,
        actor_username=username,
        actor_role=role,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        description=description,
    )
    db.session.add(entry)
    return entry


def notify_user(user_id, title, message, category='info', target_url=None):
    if not user_id:
        return None
    note = Notification(
        user_id=user_id,
        title=title,
        message=message,
        category=category,
        target_url=target_url,
    )
    db.session.add(note)
    return note


def notify_role(role, title, message, category='info', target_url=None):
    for user in User.query.filter_by(role=role).all():
        notify_user(user.id, title, message, category=category, target_url=target_url)
