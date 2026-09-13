"""Gunicorn runtime configuration for the containerized HMS web service."""
import os

bind = f"0.0.0.0:{os.environ.get('PORT', '8000')}"
workers = int(os.environ.get('GUNICORN_WORKERS', '2'))
threads = int(os.environ.get('GUNICORN_THREADS', '4'))
worker_class = 'gthread'
timeout = int(os.environ.get('GUNICORN_TIMEOUT', '60'))
graceful_timeout = 30
keepalive = 5
accesslog = '-'
errorlog = '-'
capture_output = True
forwarded_allow_ips = os.environ.get('GUNICORN_FORWARDED_ALLOW_IPS', '*')
