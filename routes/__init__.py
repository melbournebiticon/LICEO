import os
from flask import send_from_directory

# Import your blueprints
from routes.auth import auth_bp  # type: ignore
from routes.super_admin import super_admin_bp  # type: ignore
from routes.branch_admin import branch_admin_bp  # type: ignore
from routes.registrar import registrar_bp  # type: ignore
from routes.student import student_bp  # type: ignore
from routes.public import public_bp  # type: ignore
from routes.cashier import cashier_bp  # type: ignore
from routes.parent import parent_bp  # type: ignore
from routes.student_portal import student_portal_bp  # type: ignore
from routes.librarian import librarian_bp  # type: ignore
from routes.teacher import teacher_bp  # type: ignore


def _register_bp_once(app, bp, **kwargs):
    """
    Register blueprint only if not yet registered.
    Prevents: ValueError: The name 'xxx' is already registered...
    """
    if bp.name in app.blueprints:
        return
    app.register_blueprint(bp, **kwargs)


def init_routes(app):
    # Folder where uploaded files are stored
    upload_folder = os.path.join(os.getcwd(), "uploads")
    os.makedirs(upload_folder, exist_ok=True)

    # Optional: store on app config
    app.config["UPLOAD_FOLDER"] = upload_folder

    # Register blueprints (safe)
    _register_bp_once(app, auth_bp)
    _register_bp_once(app, super_admin_bp)
    _register_bp_once(app, branch_admin_bp)
    _register_bp_once(app, registrar_bp)
    _register_bp_once(app, student_bp)
    _register_bp_once(app, public_bp)
    _register_bp_once(app, cashier_bp)
    _register_bp_once(app, parent_bp)
    _register_bp_once(app, student_portal_bp)
    _register_bp_once(app, librarian_bp)
    _register_bp_once(app, teacher_bp)

    # Serve uploaded files (avoid duplicate route on reload)
    if "uploaded_file" not in app.view_functions:
        @app.route("/uploads/<path:filename>")
        def uploaded_file(filename):
            return send_from_directory(app.config["UPLOAD_FOLDER"], filename)