"""Celery entrypoint used by worker and Beat containers."""
from app import create_app
from app.background import make_celery

flask_app = create_app()
celery_app = make_celery(flask_app)
