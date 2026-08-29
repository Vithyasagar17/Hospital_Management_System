from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from flask_migrate import Migrate
import os

db = SQLAlchemy()
login_manager = LoginManager()
migrate = Migrate()

def create_app():
    app = Flask(__name__, instance_relative_config=True)

    app.config['SECRET_KEY'] = 'supersecretkey'
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(app.instance_path, 'hms.db')
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

    try:
        os.makedirs(app.instance_path, exist_ok=True)
    except OSError:
        pass

    db.init_app(app)
    migrate.init_app(app, db)
    login_manager.init_app(app)

    login_manager.login_view = 'auth.login'
    login_manager.login_message_category = 'info'

    from app import models

    from app.routes import auth_bp, admin_bp, doctor_bp, patient_bp
    app.register_blueprint(auth_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(doctor_bp)
    app.register_blueprint(patient_bp)

    # Keep older bundled SQLite databases compatible with additive Phase 2 fields.
    with app.app_context():
        from app.schema_upgrade import ensure_phase3_schema
        ensure_phase3_schema()


    @app.context_processor
    def inject_phase3_navigation():
        from flask_login import current_user
        from app.models import Notification
        if not getattr(current_user, 'is_authenticated', False):
            return {'nav_notifications': [], 'unread_notification_count': 0}
        base = Notification.query.filter_by(user_id=current_user.id)
        return {
            'nav_notifications': base.order_by(Notification.created_at.desc()).limit(5).all(),
            'unread_notification_count': base.filter_by(is_read=False).count(),
        }

    return app

@login_manager.user_loader
def load_user(user_id):
    from app.models import User
    return User.query.get(int(user_id))
