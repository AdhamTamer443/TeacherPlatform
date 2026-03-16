from flask import Blueprint, render_template, redirect, url_for, flash
from ..db import get_db, get_youtube_embed
from ..auth_utils import get_current_user

main_bp = Blueprint('main', __name__)


@main_bp.route('/')
def index():
    conn = get_db()
    grades = conn.execute("SELECT * FROM grades ORDER BY order_index").fetchall()
    term_counts = {}
    for g in grades:
        term_counts[g['id']] = conn.execute(
            "SELECT COUNT(*) as c FROM terms WHERE grade_id=?", (g['id'],)
        ).fetchone()['c']
    conn.close()
    return render_template('index.html', grades=grades, term_counts=term_counts)


@main_bp.route('/grades')
def grades():
    conn = get_db()
    grades = conn.execute("SELECT * FROM grades ORDER BY order_index").fetchall()
    term_counts = {}
    for g in grades:
        term_counts[g['id']] = conn.execute(
            "SELECT COUNT(*) as c FROM terms WHERE grade_id=?", (g['id'],)
        ).fetchone()['c']
    conn.close()
    return render_template('grades.html', grades=grades, term_counts=term_counts)


@main_bp.route('/grade/<int:grade_id>')
def grade_detail(grade_id):
    conn = get_db()
    grade = conn.execute("SELECT * FROM grades WHERE id=?", (grade_id,)).fetchone()
    if not grade:
        conn.close()
        return redirect(url_for('main.grades'))

    terms = conn.execute(
        "SELECT * FROM terms WHERE grade_id=? ORDER BY order_index", (grade_id,)
    ).fetchall()

    term_stats = {}
    for t in terms:
        unit_count = conn.execute(
            "SELECT COUNT(*) as c FROM units WHERE term_id=?", (t['id'],)
        ).fetchone()['c']
        lesson_count = conn.execute(
            "SELECT COUNT(*) as c FROM lessons l JOIN units u ON u.id=l.unit_id WHERE u.term_id=?",
            (t['id'],)
        ).fetchone()['c']
        term_stats[t['id']] = {'units': unit_count, 'lessons': lesson_count}

    user = get_current_user()
    term_access = {}
    if user.is_authenticated:
        for t in terms:
            term_access[t['id']] = user.has_access('term', t['id'])

    conn.close()
    return render_template('terms.html', grade=grade, terms=terms,
                           term_stats=term_stats, term_access=term_access)


@main_bp.route('/grade/<int:grade_id>/term/<int:term_id>')
def term_detail(grade_id, term_id):
    conn = get_db()
    grade = conn.execute("SELECT * FROM grades WHERE id=?", (grade_id,)).fetchone()
    term = conn.execute(
        "SELECT * FROM terms WHERE id=? AND grade_id=?", (term_id, grade_id)
    ).fetchone()
    if not grade or not term:
        conn.close()
        return redirect(url_for('main.grades'))

    units = conn.execute(
        "SELECT * FROM units WHERE term_id=? ORDER BY order_index", (term_id,)
    ).fetchall()

    unit_lesson_counts = {}
    for u in units:
        unit_lesson_counts[u['id']] = conn.execute(
            "SELECT COUNT(*) as c FROM lessons WHERE unit_id=?", (u['id'],)
        ).fetchone()['c']

    user = get_current_user()
    term_access = None
    unit_access = {}
    if user.is_authenticated:
        term_access = user.has_access('term', term_id)
        for u in units:
            unit_access[u['id']] = user.has_access('unit', u['id'])

    conn.close()
    return render_template('term_detail.html',
                           grade=grade, term=term, units=units,
                           unit_lesson_counts=unit_lesson_counts,
                           term_access=term_access, unit_access=unit_access)


@main_bp.route('/unit/<int:unit_id>')
def unit_detail(unit_id):
    conn = get_db()
    unit = conn.execute("""
        SELECT u.*, g.title as grade_title,
               t.id as term_id, t.title as term_title
        FROM units u
        JOIN grades g ON g.id=u.grade_id
        LEFT JOIN terms t ON t.id=u.term_id
        WHERE u.id=?
    """, (unit_id,)).fetchone()
    if not unit:
        conn.close()
        return redirect(url_for('main.grades'))

    lessons = conn.execute(
        "SELECT * FROM lessons WHERE unit_id=? ORDER BY order_index", (unit_id,)
    ).fetchall()

    user = get_current_user()
    access_tier = None
    if user.is_authenticated:
        access_tier = user.has_access('unit', unit_id)

    progress_map = {}
    if user.is_authenticated:
        rows = conn.execute(
            "SELECT * FROM progress WHERE user_id=?", (user.id,)
        ).fetchall()
        for r in rows:
            progress_map[r['lesson_id']] = r

    conn.close()
    return render_template('unit_detail.html', unit=unit, lessons=lessons,
                           access_tier=access_tier, progress_map=progress_map)


@main_bp.route('/lesson/<int:lesson_id>')
def lesson(lesson_id):
    user = get_current_user()
    if not user.is_authenticated:
        flash('يجب تسجيل الدخول لمشاهدة الدروس', 'warning')
        return redirect(url_for('auth.login'))

    conn = get_db()
    lesson = conn.execute("""
        SELECT l.*, u.id as unit_id, u.title as unit_title, u.grade_id,
               u.term_id, t.title as term_title
        FROM lessons l
        JOIN units u ON u.id=l.unit_id
        LEFT JOIN terms t ON t.id=u.term_id
        WHERE l.id=?
    """, (lesson_id,)).fetchone()
    if not lesson:
        conn.close()
        return redirect(url_for('main.grades'))

    grade = conn.execute("SELECT * FROM grades WHERE id=?", (lesson['grade_id'],)).fetchone()
    lessons_ordered = conn.execute(
        "SELECT * FROM lessons WHERE unit_id=? ORDER BY order_index", (lesson['unit_id'],)
    ).fetchall()

    lesson_index = next((i for i, l in enumerate(lessons_ordered) if l['id'] == lesson_id), 0)
    access_tier = user.has_access('unit', lesson['unit_id'])

    if not access_tier and not user.is_admin:
        conn.close()
        flash('يجب شراء الوحدة أو الفصل للوصول إلى هذا الدرس', 'warning')
        return redirect(url_for('main.unit_detail', unit_id=lesson['unit_id']))

    progress = conn.execute(
        "SELECT * FROM progress WHERE user_id=? AND lesson_id=?", (user.id, lesson_id)
    ).fetchone()

    next_lesson = lessons_ordered[lesson_index + 1] if lesson_index + 1 < len(lessons_ordered) else None
    prev_lesson = lessons_ordered[lesson_index - 1] if lesson_index > 0 else None
    conn.close()

    embed_url = get_youtube_embed(lesson['video_url'])

    return render_template('lesson.html',
                           lesson=lesson, grade=grade,
                           access_tier=access_tier,
                           progress=progress,
                           next_lesson=next_lesson,
                           prev_lesson=prev_lesson,
                           lessons_ordered=lessons_ordered,
                           lesson_index=lesson_index,
                           embed_url=embed_url)


@main_bp.route('/privacy')
def privacy():
    return render_template('privacy.html')


@main_bp.route('/terms')
def terms_of_use():
    return render_template('terms_of_use.html')


@main_bp.route('/sitemap.xml')
def sitemap():
    from flask import current_app, send_from_directory
    return send_from_directory(current_app.static_folder, 'sitemap.xml', mimetype='application/xml')
