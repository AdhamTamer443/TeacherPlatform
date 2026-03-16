import os
from flask import Flask, session
from .db import init_db, seed_admin


def create_app():
    app = Flask(__name__)
    secret = os.environ.get('SECRET_KEY')
    if not secret:
        raise RuntimeError('SECRET_KEY environment variable is not set. Set it before running the app.')
    app.secret_key = secret

    from flask_wtf.csrf import CSRFProtect
    csrf = CSRFProtect(app)
    app.config['WTF_CSRF_HEADERS'] = ['X-CSRFToken']

    from datetime import timedelta
    app.permanent_session_lifetime = timedelta(days=365)
    app.config['SESSION_REFRESH_EACH_REQUEST'] = True
    app.config['UPLOAD_FOLDER'] = os.path.join(app.root_path, 'static', 'uploads')
    app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024
    app.config['INSTAPAY_NUMBER'] = '01000000000'
    app.config['SITE_NAME'] = 'خادم الفصحى'

    os.makedirs(os.path.join(app.config['UPLOAD_FOLDER'], 'screenshots'), exist_ok=True)
    os.makedirs(os.path.join(app.config['UPLOAD_FOLDER'], 'pdfs'), exist_ok=True)
    os.makedirs(os.path.join(app.config['UPLOAD_FOLDER'], 'images'), exist_ok=True)

    init_db()
    seed_admin()

    from .routes.main import main_bp
    from .routes.auth import auth_bp
    from .routes.student import student_bp
    from .routes.admin import admin_bp
    from .routes.payment import payment_bp

    app.register_blueprint(main_bp)
    app.register_blueprint(auth_bp, url_prefix='/auth')
    app.register_blueprint(student_bp, url_prefix='/student')
    app.register_blueprint(admin_bp, url_prefix='/admin')
    app.register_blueprint(payment_bp, url_prefix='/payment')

    # Inject current_user into all templates
    @app.context_processor
    def inject_user():
        from .auth_utils import get_current_user
        from datetime import datetime
        return dict(
            current_user=get_current_user(),
            experience_years=datetime.now().year - 2000
        )

    return app
