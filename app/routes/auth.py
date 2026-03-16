import re
from flask import Blueprint, render_template, redirect, url_for, flash, request, session
from werkzeug.security import generate_password_hash, check_password_hash
from ..db import get_db
from ..auth_utils import get_current_user

auth_bp = Blueprint('auth', __name__)


def validate_password(p):
    if not p:
        return ['كلمة المرور مطلوبة']
    if len(p) < 8:
        return ['كلمة المرور يجب أن تكون 8 أحرف على الأقل']
    return []
    



def validate_phone(phone):
    return bool(re.match(r'^(\+20|0020|0)?1[0125]\d{8}$', phone.replace(' ', '')))


@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if session.get('user_id'):
        return redirect(url_for('main.index'))

    if request.method == 'POST':
        identifier = request.form.get('identifier', '').strip()
        password = request.form.get('password', '')
        conn = get_db()
        user = conn.execute(
            "SELECT * FROM users WHERE email=? OR phone=?", (identifier, identifier)
        ).fetchone()
        conn.close()

        if user and check_password_hash(user['password_hash'], password):
            if not user['is_active']:
                flash('حسابك موقوف، تواصل مع الدعم', 'danger')
                return redirect(url_for('auth.login'))
            session.permanent = bool(request.form.get('remember'))
            session['user_id'] = user['id']
            session['is_admin'] = bool(user['is_admin'])
            flash(f'أهلاً بك، {user["name"]}!', 'success')
            if user['is_admin']:
                return redirect(url_for('admin.dashboard'))
            return redirect(url_for('student.dashboard'))
        flash('البريد الإلكتروني أو كلمة المرور غير صحيحة', 'danger')

    return render_template('login.html')


@auth_bp.route('/signup', methods=['GET', 'POST'])
def signup():
    if session.get('user_id'):
        return redirect(url_for('main.index'))

    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        phone = request.form.get('phone', '').strip()
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')
        password2 = request.form.get('password2', '')

        errors = []
        if len(name) < 3: errors.append('الاسم يجب أن يكون 3 أحرف على الأقل')
        if not validate_phone(phone): errors.append('رقم الهاتف غير صحيح (رقم مصري مطلوب)')
        if not re.match(r'^[^@]+@[^@]+\.[^@]+$', email) and email != "": errors.append('البريد الإلكتروني غير صحيح')
        errors.extend(validate_password(password))
        if password != password2: errors.append('كلمتا المرور غير متطابقتين')

        conn = get_db()
        if conn.execute("SELECT id FROM users WHERE phone=?", (phone,)).fetchone():
            errors.append('رقم الهاتف مسجل بالفعل')
        if email != '':
            if conn.execute("SELECT id FROM users WHERE email=?", (email,)).fetchone():
                errors.append('البريد الإلكتروني مسجل بالفعل')

        if errors:
            conn.close()
            for e in errors: flash(e, 'danger')
            return render_template('signup.html', form_data=request.form)

        conn.execute(
    "INSERT INTO users (name,phone,email,password_hash) VALUES (?,?,?,?)",
    (name, phone, email if email else None, generate_password_hash(password))
)
        conn.commit()
        user = conn.execute("SELECT * FROM users WHERE phone=?", (phone,)).fetchone()
        conn.close()

        session.permanent = True
        session['user_id'] = user['id']
        session['is_admin'] = False
        flash('تم إنشاء حسابك بنجاح! 🎉', 'success')
        return redirect(url_for('student.dashboard'))

    return render_template('signup.html', form_data={})


@auth_bp.route('/logout')
def logout():
    session.clear()
    flash('تم تسجيل الخروج بنجاح', 'success')
    return redirect(url_for('main.index'))
