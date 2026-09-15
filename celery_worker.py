"""Celery entrypoint used by worker and Beat containers."""
from app import create_app
from app.background import make_celery
from app.observability import configure_logging

flask_app = create_app()
configure_logging(flask_app)
celery_app = make_celery(flask_app)
