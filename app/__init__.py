from datetime import timedelta, timezone
import os
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from flask import (
    Flask,
    abort,
    flash,
    redirect,
    request,
    session,
    url_for,
    render_template,
)
from flask_login import LoginManager, current_user, logout_user
from flask_migrate import Migrate
from flask_sqlalchemy import SQLAlchemy


db = SQLAlchemy()
login_manager = LoginManager()
migrate = Migrate()


def create_app(test_config=None):
    app = Flask(__name__, instance_relative_config=True)

    app.config.from_mapping(
        SECRET_KEY=os.environ.get(
            "HMS_SECRET_KEY",
            "dev-only-change-me-before-deploying"
        ),

        SQLALCHEMY_DATABASE_URI=(
            "sqlite:///" + os.path.join(app.instance_path, "hms.db")
        ),

        SQLALCHEMY_TRACK_MODIFICATIONS=False,

        # Session security
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=(
            os.environ.get("HMS_COOKIE_SECURE", "0") == "1"
        ),
        PERMANENT_SESSION_LIFETIME=timedelta(
            minutes=int(
                os.environ.get("HMS_SESSION_MINUTES", "30")
            )
        ),

        REMEMBER_COOKIE_HTTPONLY=True,
        REMEMBER_COOKIE_SAMESITE="Lax",
        REMEMBER_COOKIE_SECURE=(
            os.environ.get("HMS_COOKIE_SECURE", "0") == "1"
        ),

        TRUST_PROXY_HEADERS=(
            os.environ.get("HMS_TRUST_PROXY", "0") == "1"
        ),

        # Login security
        LOGIN_RATE_WINDOW_MINUTES=15,
        LOGIN_MAX_FAILURES_PER_USER=5,
        LOGIN_MAX_FAILURES_PER_IP=20,
        LOGIN_LOCK_MINUTES=15,

        # Email
        MAIL_MODE=os.environ.get("HMS_MAIL_MODE", "console"),
        SMTP_SERVER=os.environ.get("HMS_SMTP_SERVER"),
        SMTP_PORT=int(
            os.environ.get("HMS_SMTP_PORT", "587")
        ),
        SMTP_USERNAME=os.environ.get("HMS_SMTP_USERNAME"),
        SMTP_PASSWORD=os.environ.get("HMS_SMTP_PASSWORD"),
        SMTP_FROM=os.environ.get("HMS_SMTP_FROM"),
        SMTP_USE_TLS=(
            os.environ.get("HMS_SMTP_USE_TLS", "1") == "1"
        ),
        SMTP_USE_SSL=(
            os.environ.get("HMS_SMTP_USE_SSL", "0") == "1"
        ),

        # Display timezone
        DISPLAY_TIMEZONE="Asia/Kolkata",
    )

    if test_config:
        app.config.update(test_config)

    # ---------------------------------------------------------
    # TIMEZONE CONFIGURATION
    # ---------------------------------------------------------

    try:
        display_timezone = ZoneInfo(
            app.config["DISPLAY_TIMEZONE"]
        )
    except ZoneInfoNotFoundError:
        # Fallback to IST if Windows tzdata is unavailable
        display_timezone = timezone(
            timedelta(hours=5, minutes=30)
        )

    @app.template_filter("local_datetime")
    def local_datetime(
        value,
        fmt="%d %b %Y · %I:%M %p"
    ):
        """
        Convert system timestamps stored in UTC to IST.

        SQLite returns timestamps without timezone information,
        so naive datetimes are interpreted as UTC first.
        """

        if value is None:
            return ""

        if value.tzinfo is None:
            value = value.replace(
                tzinfo=timezone.utc
            )

        local_value = value.astimezone(
            display_timezone
        )

        return local_value.strftime(fmt)

    # ---------------------------------------------------------
    # INITIALIZE APP
    # ---------------------------------------------------------

    os.makedirs(
        app.instance_path,
        exist_ok=True
    )

    db.init_app(app)
    migrate.init_app(app, db)

    login_manager.init_app(app)
    login_manager.login_view = "auth.login"
    login_manager.login_message_category = "info"

    # ---------------------------------------------------------
    # BLUEPRINTS
    # ---------------------------------------------------------

    from app import models

    from app.routes import (
        auth_bp,
        admin_bp,
        doctor_bp,
        patient_bp,
    )

    app.register_blueprint(auth_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(doctor_bp)
    app.register_blueprint(patient_bp)

    # ---------------------------------------------------------
    # DATABASE SCHEMA UPGRADE
    # ---------------------------------------------------------

    with app.app_context():
        from app.schema_upgrade import ensure_phase5_schema
        ensure_phase5_schema()

    # ---------------------------------------------------------
    # CSRF SECURITY
    # ---------------------------------------------------------

    from app.security import (
        generate_csrf_token,
        validate_csrf_token,
    )

    @app.before_request
    def phase4_request_security():

        if (
            request.method
            in {"POST", "PUT", "PATCH", "DELETE"}
            and not app.config.get(
                "TESTING_CSRF_DISABLED",
                False
            )
        ):
            token = (
                request.form.get("_csrf_token")
                or request.headers.get(
                    "X-CSRF-Token"
                )
            )

            if not validate_csrf_token(token):
                abort(
                    400,
                    description=(
                        "Security token missing or invalid. "
                        "Refresh the page and try again."
                    ),
                )

        if current_user.is_authenticated:

            # Password changes invalidate old sessions
            stored_version = session.get(
                "session_version"
            )

            if (
                stored_version is not None
                and stored_version
                != current_user.session_version
            ):
                logout_user()
                session.clear()

                flash(
                    "Your session expired because "
                    "account security changed. "
                    "Please sign in again.",
                    "info",
                )

                return redirect(
                    url_for("auth.login")
                )

            session.permanent = True

            # ---------------------------------------------
            # Enforce blacklisting server-side
            # ---------------------------------------------

            disabled = False

            if current_user.role == "Doctor":

                from app.models import Doctor

                profile = db.session.get(
                    Doctor,
                    current_user.id
                )

                disabled = bool(
                    profile
                    and profile.is_blacklisted
                )

            elif current_user.role == "Patient":

                from app.models import Patient

                profile = db.session.get(
                    Patient,
                    current_user.id
                )

                disabled = bool(
                    profile
                    and profile.is_blacklisted
                )

            if disabled:

                logout_user()
                session.clear()

                flash(
                    "This account is currently disabled. "
                    "Contact an administrator.",
                    "danger",
                )

                return redirect(
                    url_for("auth.login")
                )

    # ---------------------------------------------------------
    # SECURITY HEADERS
    # ---------------------------------------------------------

    @app.after_request
    def phase4_security_headers(response):

        response.headers.setdefault(
            "X-Content-Type-Options",
            "nosniff"
        )

        response.headers.setdefault(
            "X-Frame-Options",
            "DENY"
        )

        response.headers.setdefault(
            "Referrer-Policy",
            "strict-origin-when-cross-origin"
        )

        response.headers.setdefault(
            "Permissions-Policy",
            "camera=(), microphone=(), geolocation=()"
        )

        response.headers.setdefault(
            "Content-Security-Policy",

            "default-src 'self'; "
            "img-src 'self' data:; "

            "style-src 'self' 'unsafe-inline' "
            "https://cdn.jsdelivr.net "
            "https://fonts.googleapis.com; "

            "font-src 'self' "
            "https://cdn.jsdelivr.net "
            "https://fonts.gstatic.com; "

            "script-src 'self' 'unsafe-inline' "
            "https://cdn.jsdelivr.net; "

            "connect-src 'self'; "
            "frame-ancestors 'none'; "
            "base-uri 'self'; "
            "form-action 'self'"
        )

        if current_user.is_authenticated:
            response.headers.setdefault(
                "Cache-Control",
                "no-store, private"
            )

        return response

    # ---------------------------------------------------------
    # NAVBAR DATA
    # ---------------------------------------------------------

    @app.context_processor
    def inject_phase4_navigation():

        from app.models import Notification

        if not getattr(
            current_user,
            "is_authenticated",
            False
        ):
            return {
                "nav_notifications": [],
                "unread_notification_count": 0,
                "csrf_token": generate_csrf_token,
            }

        base = Notification.query.filter_by(
            user_id=current_user.id
        )

        return {
            "nav_notifications": (
                base
                .order_by(
                    Notification.created_at.desc()
                )
                .limit(5)
                .all()
            ),

            "unread_notification_count": (
                base
                .filter_by(is_read=False)
                .count()
            ),

            "csrf_token": generate_csrf_token,
        }

    # ---------------------------------------------------------
    # ERROR PAGES
    # ---------------------------------------------------------

    def _error_page(
        code,
        title,
        message
    ):
        return render_template(
            "error.html",
            error_code=code,
            error_title=title,
            error_message=message,
        ), code

    @app.errorhandler(400)
    def bad_request(error):

        return _error_page(
            400,
            "We could not process that request.",
            getattr(
                error,
                "description",
                "Please check the submitted information "
                "and try again.",
            ),
        )

    @app.errorhandler(403)
    def forbidden(error):

        return _error_page(
            403,
            "Access denied.",
            "Your account does not have permission "
            "to open this resource.",
        )

    @app.errorhandler(404)
    def not_found(error):

        return _error_page(
            404,
            "Page not found.",
            "The page or record may have moved, "
            "been removed, or never existed.",
        )

    @app.errorhandler(500)
    def server_error(error):

        db.session.rollback()

        return _error_page(
            500,
            "Something went wrong.",
            "The request could not be completed. "
            "Please try again.",
        )

    return app


@login_manager.user_loader
def load_user(user_id):

    from app.models import User

    return db.session.get(
        User,
        int(user_id)
    )