import os
from datetime import datetime
from flask import Blueprint, render_template, request, redirect, url_for, flash, current_app
from werkzeug.utils import secure_filename
from ..db import get_db
from ..auth_utils import admin_required, get_current_user

admin_bp = Blueprint('admin', __name__)


ALLOWED_IMAGE_EXTS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}
ALLOWED_PDF_EXTS = {'pdf'}

def save_file(file, subfolder, prefix=''):
    if file and file.filename:
        ext = file.filename.rsplit('.', 1)[-1].lower() if '.' in file.filename else ''
        allowed = ALLOWED_PDF_EXTS if subfolder == 'pdfs' else ALLOWED_IMAGE_EXTS
        if ext not in allowed:
            return None
        safe = secure_filename(f"{prefix}_{file.filename}")
        folder = os.path.join(current_app.config['UPLOAD_FOLDER'], subfolder)
        os.makedirs(folder, exist_ok=True)
        file.save(os.path.join(folder, safe))
        return f"{subfolder}/{safe}"
    return None


# ── Dashboard ──────────────────────────────────

@admin_bp.route('/')
@admin_required
def dashboard():
    conn = get_db()
    stats = {
        'students': conn.execute("SELECT COUNT(*) as c FROM users WHERE is_admin=0").fetchone()['c'],
        'grades':   conn.execute("SELECT COUNT(*) as c FROM grades").fetchone()['c'],
        'terms':    conn.execute("SELECT COUNT(*) as c FROM terms").fetchone()['c'],
        'units':    conn.execute("SELECT COUNT(*) as c FROM units").fetchone()['c'],
        'lessons':  conn.execute("SELECT COUNT(*) as c FROM lessons").fetchone()['c'],
        'pending':  conn.execute("SELECT COUNT(*) as c FROM payment_requests WHERE status='pending'").fetchone()['c'],
    }
    recent = conn.execute("""SELECT pr.*, u.name as user_name, u.phone,
       CASE pr.item_type
         WHEN 'unit' THEN (SELECT title FROM units WHERE id=pr.item_id)
         WHEN 'term' THEN (SELECT title FROM terms WHERE id=pr.item_id)
       END as item_title,
       CASE pr.item_type
         WHEN 'unit' THEN (SELECT grade_id FROM units WHERE id=pr.item_id)
         WHEN 'term' THEN (SELECT grade_id FROM terms WHERE id=pr.item_id)
       END as item_grade_id
       FROM payment_requests pr JOIN users u ON u.id=pr.user_id
       ORDER BY pr.created_at DESC LIMIT 8""").fetchall()
    conn.close()
    return render_template('admin/dashboard.html', stats=stats, recent_requests=recent)


# ── Grades ──────────────────────────────────────

@admin_bp.route('/grades')
@admin_required
def grades():
    conn = get_db()
    grades = conn.execute("SELECT * FROM grades ORDER BY order_index").fetchall()
    counts = {}
    for g in grades:
        counts[g['id']] = conn.execute(
            "SELECT COUNT(*) as c FROM terms WHERE grade_id=?", (g['id'],)
        ).fetchone()['c']
    conn.close()
    return render_template('admin/grades.html', grades=grades, term_counts=counts)


@admin_bp.route('/grades/create', methods=['GET', 'POST'])
@admin_required
def grade_create():
    if request.method == 'POST':
        img = save_file(request.files.get('image'), 'images', 'grade')
        conn = get_db()
        conn.execute("INSERT INTO grades (title,description,image,order_index) VALUES (?,?,?,?)",
                     (request.form['title'], request.form.get('description', ''),
                      img, int(request.form.get('order_index', 0))))
        conn.commit(); conn.close()
        flash('تم إنشاء الصف', 'success')
        return redirect(url_for('admin.grades'))
    return render_template('admin/grade_form.html', grade=None, action='create')


@admin_bp.route('/grades/<int:gid>/edit', methods=['GET', 'POST'])
@admin_required
def grade_edit(gid):
    conn = get_db()
    grade = conn.execute("SELECT * FROM grades WHERE id=?", (gid,)).fetchone()
    if request.method == 'POST':
        img = save_file(request.files.get('image'), 'images', 'grade')
        conn.execute("UPDATE grades SET title=?,description=?,order_index=?{}WHERE id=?".format(
            ',image=? ' if img else ' '),
            (request.form['title'], request.form.get('description', ''),
             int(request.form.get('order_index', 0)), *([img] if img else []), gid))
        conn.commit(); conn.close()
        flash('تم تحديث الصف', 'success')
        return redirect(url_for('admin.grades'))
    conn.close()
    return render_template('admin/grade_form.html', grade=grade, action='edit')


@admin_bp.route('/grades/<int:gid>/delete', methods=['POST'])
@admin_required
def grade_delete(gid):
    conn = get_db()
    conn.execute("DELETE FROM grades WHERE id=?", (gid,))
    conn.commit(); conn.close()
    flash('تم حذف الصف', 'success')
    return redirect(url_for('admin.grades'))


# ── Terms ───────────────────────────────────────

@admin_bp.route('/grades/<int:gid>/terms')
@admin_required
def terms(gid):
    conn = get_db()
    grade = conn.execute("SELECT * FROM grades WHERE id=?", (gid,)).fetchone()
    if not grade:
        conn.close()
        return redirect(url_for('admin.grades'))
    terms = conn.execute(
        "SELECT * FROM terms WHERE grade_id=? ORDER BY order_index", (gid,)
    ).fetchall()
    unit_counts = {}
    for t in terms:
        unit_counts[t['id']] = conn.execute(
            "SELECT COUNT(*) as c FROM units WHERE term_id=?", (t['id'],)
        ).fetchone()['c']
    conn.close()
    return render_template('admin/terms.html', grade=grade, terms=terms, unit_counts=unit_counts)


@admin_bp.route('/grades/<int:gid>/terms/create', methods=['GET', 'POST'])
@admin_required
def term_create(gid):
    conn = get_db()
    grade = conn.execute("SELECT * FROM grades WHERE id=?", (gid,)).fetchone()
    if not grade:
        conn.close()
        return redirect(url_for('admin.grades'))
    if request.method == 'POST':
        conn.execute("""INSERT INTO terms
            (grade_id, title, description, order_index, bronze_price, silver_price, gold_price)
            VALUES (?,?,?,?,?,?,?)""",
            (gid,
             request.form['title'],
             request.form.get('description', ''),
             int(request.form.get('order_index', 0)),
             float(request.form.get('bronze_price', 0)),
             float(request.form.get('silver_price', 0)),
             float(request.form.get('gold_price', 0))))
        conn.commit(); conn.close()
        flash('تم إنشاء الفصل الدراسي', 'success')
        return redirect(url_for('admin.terms', gid=gid))
    conn.close()
    return render_template('admin/term_form.html', grade=grade, term=None, action='create')


@admin_bp.route('/grades/<int:gid>/terms/<int:tid>/edit', methods=['GET', 'POST'])
@admin_required
def term_edit(gid, tid):
    conn = get_db()
    grade = conn.execute("SELECT * FROM grades WHERE id=?", (gid,)).fetchone()
    term = conn.execute("SELECT * FROM terms WHERE id=? AND grade_id=?", (tid, gid)).fetchone()
    if not grade or not term:
        conn.close()
        return redirect(url_for('admin.grades'))
    if request.method == 'POST':
        conn.execute("""UPDATE terms SET title=?, description=?, order_index=?,
                        bronze_price=?, silver_price=?, gold_price=? WHERE id=?""",
                     (request.form['title'],
                      request.form.get('description', ''),
                      int(request.form.get('order_index', 0)),
                      float(request.form.get('bronze_price', 0)),
                      float(request.form.get('silver_price', 0)),
                      float(request.form.get('gold_price', 0)),
                      tid))
        conn.commit(); conn.close()
        flash('تم تحديث الفصل الدراسي', 'success')
        return redirect(url_for('admin.terms', gid=gid))
    conn.close()
    return render_template('admin/term_form.html', grade=grade, term=term, action='edit')


@admin_bp.route('/grades/<int:gid>/terms/<int:tid>/delete', methods=['POST'])
@admin_required
def term_delete(gid, tid):
    conn = get_db()
    conn.execute("DELETE FROM terms WHERE id=? AND grade_id=?", (tid, gid))
    conn.commit(); conn.close()
    flash('تم حذف الفصل الدراسي', 'success')
    return redirect(url_for('admin.terms', gid=gid))


# ── Units ───────────────────────────────────────

@admin_bp.route('/units')
@admin_required
def units():
    conn = get_db()
    grade_filter = request.args.get('grade')
    term_filter = request.args.get('term')

    q = """SELECT u.*, g.title as grade_title, t.title as term_title
           FROM units u
           JOIN grades g ON g.id=u.grade_id
           LEFT JOIN terms t ON t.id=u.term_id"""
    params = []
    if term_filter:
        q += " WHERE u.term_id=?"
        params.append(term_filter)
    elif grade_filter:
        q += " WHERE u.grade_id=?"
        params.append(grade_filter)
    q += " ORDER BY g.order_index, t.order_index, u.order_index"

    units = conn.execute(q, params).fetchall()
    grades = conn.execute("SELECT * FROM grades ORDER BY order_index").fetchall()
    all_terms = conn.execute(
        "SELECT t.*, g.title as grade_title FROM terms t JOIN grades g ON g.id=t.grade_id ORDER BY g.order_index, t.order_index"
    ).fetchall()
    lesson_counts = {}
    for u in units:
        lesson_counts[u['id']] = conn.execute(
            "SELECT COUNT(*) as c FROM lessons WHERE unit_id=?", (u['id'],)
        ).fetchone()['c']
    conn.close()
    return render_template('admin/units.html', units=units, grades=grades,
                           all_terms=all_terms, lesson_counts=lesson_counts)


@admin_bp.route('/units/create', methods=['GET', 'POST'])
@admin_required
def unit_create():
    conn = get_db()
    grades = conn.execute("SELECT * FROM grades ORDER BY order_index").fetchall()
    all_terms = conn.execute(
        "SELECT * FROM terms ORDER BY grade_id, order_index"
    ).fetchall()
    if request.method == 'POST':
        thumb = save_file(request.files.get('thumbnail'), 'images', 'unit')
        term_id = request.form.get('term_id') or None
        grade_id = int(request.form['grade_id'])
        conn.execute("""INSERT INTO units
            (grade_id, term_id, title, description, thumbnail, order_index,
             bronze_price, silver_price, gold_price)
            VALUES (?,?,?,?,?,?,?,?,?)""",
            (grade_id, term_id, request.form['title'],
             request.form.get('description', ''), thumb,
             int(request.form.get('order_index', 0)),
             float(request.form.get('bronze_price', 0)),
             float(request.form.get('silver_price', 0)),
             float(request.form.get('gold_price', 0))))
        conn.commit(); conn.close()
        flash('تم إنشاء الوحدة', 'success')
        return redirect(url_for('admin.units'))
    conn.close()
    return render_template('admin/unit_form.html', unit=None, grades=grades,
                           all_terms=all_terms, action='create')


@admin_bp.route('/units/<int:uid>/edit', methods=['GET', 'POST'])
@admin_required
def unit_edit(uid):
    conn = get_db()
    unit = conn.execute("SELECT * FROM units WHERE id=?", (uid,)).fetchone()
    grades = conn.execute("SELECT * FROM grades ORDER BY order_index").fetchall()
    all_terms = conn.execute(
        "SELECT * FROM terms ORDER BY grade_id, order_index"
    ).fetchall()
    if request.method == 'POST':
        thumb = save_file(request.files.get('thumbnail'), 'images', 'unit')
        term_id = request.form.get('term_id') or None
        grade_id = int(request.form['grade_id'])
        if thumb:
            conn.execute("""UPDATE units SET grade_id=?, term_id=?, title=?, description=?,
                            thumbnail=?, order_index=?,
                            bronze_price=?, silver_price=?, gold_price=? WHERE id=?""",
                         (grade_id, term_id, request.form['title'],
                          request.form.get('description', ''), thumb,
                          int(request.form.get('order_index', 0)),
                          float(request.form.get('bronze_price', 0)),
                          float(request.form.get('silver_price', 0)),
                          float(request.form.get('gold_price', 0)), uid))
        else:
            conn.execute("""UPDATE units SET grade_id=?, term_id=?, title=?, description=?,
                            order_index=?,
                            bronze_price=?, silver_price=?, gold_price=? WHERE id=?""",
                         (grade_id, term_id, request.form['title'],
                          request.form.get('description', ''),
                          int(request.form.get('order_index', 0)),
                          float(request.form.get('bronze_price', 0)),
                          float(request.form.get('silver_price', 0)),
                          float(request.form.get('gold_price', 0)), uid))
        conn.commit(); conn.close()
        flash('تم تحديث الوحدة', 'success')
        return redirect(url_for('admin.units'))
    conn.close()
    return render_template('admin/unit_form.html', unit=unit, grades=grades,
                           all_terms=all_terms, action='edit')


@admin_bp.route('/units/<int:uid>/delete', methods=['POST'])
@admin_required
def unit_delete(uid):
    conn = get_db()
    conn.execute("DELETE FROM units WHERE id=?", (uid,))
    conn.commit(); conn.close()
    flash('تم حذف الوحدة', 'success')
    return redirect(url_for('admin.units'))


# ── Lessons ─────────────────────────────────────

@admin_bp.route('/units/<int:uid>/lessons')
@admin_required
def lessons(uid):
    conn = get_db()
    unit = conn.execute("""
        SELECT u.*, g.title as grade_title, t.title as term_title
        FROM units u
        JOIN grades g ON g.id=u.grade_id
        LEFT JOIN terms t ON t.id=u.term_id
        WHERE u.id=?
    """, (uid,)).fetchone()
    lessons = conn.execute(
        "SELECT * FROM lessons WHERE unit_id=? ORDER BY order_index", (uid,)
    ).fetchall()
    conn.close()
    return render_template('admin/lessons.html', unit=unit, lessons=lessons)


@admin_bp.route('/units/<int:uid>/lessons/create', methods=['GET', 'POST'])
@admin_required
def lesson_create(uid):
    conn = get_db()
    unit = conn.execute("SELECT * FROM units WHERE id=?", (uid,)).fetchone()
    if request.method == 'POST':
        ep = save_file(request.files.get('exercise_easy_pdf'), 'pdfs', 'easy')
        hp = save_file(request.files.get('exercise_hard_pdf'), 'pdfs', 'hard')
        bp = save_file(request.files.get('brief_pdf'), 'pdfs', 'brief')
        conn.execute("""INSERT INTO lessons
                        (unit_id,title,description,video_url,exercise_easy_pdf,
                         exercise_hard_pdf,brief_pdf,order_index,duration_minutes)
                        VALUES (?,?,?,?,?,?,?,?,?)""",
                     (uid, request.form['title'], request.form.get('description', ''),
                      request.form.get('video_url', ''), ep, hp, bp,
                      int(request.form.get('order_index', 0)),
                      int(request.form.get('duration_minutes', 0))))
        conn.commit(); conn.close()
        flash('تم إنشاء الدرس', 'success')
        return redirect(url_for('admin.lessons', uid=uid))
    conn.close()
    return render_template('admin/lesson_form.html', unit=unit, lesson=None, action='create')


@admin_bp.route('/lessons/<int:lid>/edit', methods=['GET', 'POST'])
@admin_required
def lesson_edit(lid):
    conn = get_db()
    lesson = conn.execute("SELECT * FROM lessons WHERE id=?", (lid,)).fetchone()
    unit = conn.execute("SELECT * FROM units WHERE id=?", (lesson['unit_id'],)).fetchone()
    if request.method == 'POST':
        ep = save_file(request.files.get('exercise_easy_pdf'), 'pdfs', 'easy')
        hp = save_file(request.files.get('exercise_hard_pdf'), 'pdfs', 'hard')
        bp = save_file(request.files.get('brief_pdf'), 'pdfs', 'brief')
        conn.execute("""UPDATE lessons SET title=?,description=?,video_url=?,order_index=?,duration_minutes=?
                        {} {} {} WHERE id=?""".format(
            ',exercise_easy_pdf=?' if ep else '',
            ',exercise_hard_pdf=?' if hp else '',
            ',brief_pdf=?' if bp else ''),
            (request.form['title'], request.form.get('description', ''),
             request.form.get('video_url', ''),
             int(request.form.get('order_index', 0)),
             int(request.form.get('duration_minutes', 0)),
             *([ep] if ep else []), *([hp] if hp else []), *([bp] if bp else []), lid))
        conn.commit(); conn.close()
        flash('تم تحديث الدرس', 'success')
        return redirect(url_for('admin.lessons', uid=lesson['unit_id']))
    conn.close()
    return render_template('admin/lesson_form.html', unit=unit, lesson=lesson, action='edit')


@admin_bp.route('/lessons/<int:lid>/delete', methods=['POST'])
@admin_required
def lesson_delete(lid):
    conn = get_db()
    lesson = conn.execute("SELECT unit_id FROM lessons WHERE id=?", (lid,)).fetchone()
    uid = lesson['unit_id']
    conn.execute("DELETE FROM lessons WHERE id=?", (lid,))
    conn.commit(); conn.close()
    flash('تم حذف الدرس', 'success')
    return redirect(url_for('admin.lessons', uid=uid))


# ── Payments ────────────────────────────────────

@admin_bp.route('/payments')
@admin_required
def payments():
    status = request.args.get('status', 'pending')
    conn = get_db()
    q = """SELECT pr.*, u.name as user_name, u.phone,
       CASE pr.item_type
         WHEN 'unit' THEN (SELECT title FROM units WHERE id=pr.item_id)
         WHEN 'term' THEN (SELECT title FROM terms WHERE id=pr.item_id)
       END as item_title,
       CASE pr.item_type
         WHEN 'unit' THEN (SELECT grade_id FROM units WHERE id=pr.item_id)
         WHEN 'term' THEN (SELECT grade_id FROM terms WHERE id=pr.item_id)
       END as item_grade_id
       FROM payment_requests pr JOIN users u ON u.id=pr.user_id"""
    if status != 'all':
        q += " WHERE pr.status=?"
        params = [status]
    else:
        params = []
    q += " ORDER BY pr.created_at DESC"
    requests_list = conn.execute(q, params).fetchall()
    conn.close()
    return render_template('admin/payments.html', requests=requests_list, status=status)


@admin_bp.route('/payments/<int:rid>/approve', methods=['POST'])
@admin_required
def payment_approve(rid):
    conn = get_db()
    pr = conn.execute("SELECT * FROM payment_requests WHERE id=?", (rid,)).fetchone()
    conn.execute(
        "UPDATE payment_requests SET status='approved', reviewed_at=datetime('now') WHERE id=?", (rid,)
    )
    final_tier = pr['target_tier'] if pr['is_upgrade'] and pr['target_tier'] else pr['tier']
    if pr['is_upgrade']:
        conn.execute(
        "UPDATE purchases SET tier=? WHERE user_id=? AND item_type=? AND item_id=? AND status='approved'",
        (final_tier, pr['user_id'], pr['item_type'], pr['item_id'])
    )
    else:
        conn.execute(
            "INSERT INTO purchases (user_id,item_type,item_id,tier,status,expires_at) VALUES (?,?,?,?,'approved',datetime('now', '+1 year'))",
            (pr['user_id'], pr['item_type'], pr['item_id'], final_tier)
        )
    conn.commit(); conn.close()
    flash('تم قبول الدفع ✅ وتفعيل الوصول للطالب', 'success')
    return redirect(url_for('admin.payments'))


@admin_bp.route('/payments/<int:rid>/reject', methods=['POST'])
@admin_required
def payment_reject(rid):
    note = request.form.get('note', '')
    conn = get_db()
    conn.execute(
        "UPDATE payment_requests SET status='rejected', admin_note=?, reviewed_at=datetime('now') WHERE id=?",
        (note, rid)
    )
    conn.commit(); conn.close()
    flash('تم رفض الدفع', 'warning')
    return redirect(url_for('admin.payments'))


# ── Students ────────────────────────────────────

@admin_bp.route('/students')
@admin_required
def students():
    conn = get_db()
    students = conn.execute("""SELECT * FROM users
                           WHERE is_admin=0 ORDER BY created_at DESC""").fetchall()
    conn.close()
    return render_template('admin/students.html', students=students)


@admin_bp.route('/students/<int:uid>/toggle', methods=['POST'])
@admin_required
def student_toggle(uid):
    conn = get_db()
    user = conn.execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone()
    new_status = 0 if user['is_active'] else 1
    conn.execute("UPDATE users SET is_active=? WHERE id=?", (new_status, uid))
    conn.commit(); conn.close()
    flash(f'تم {"تفعيل" if new_status else "إيقاف"} الطالب', 'success')
    return redirect(url_for('admin.students'))
