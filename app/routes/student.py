from flask import Blueprint, render_template, jsonify, request, session, redirect, url_for, flash
from ..db import get_db
from ..auth_utils import login_required, get_current_user

student_bp = Blueprint('student', __name__)


@student_bp.route('/dashboard')
@login_required
def dashboard():
    user = get_current_user()
    conn = get_db()

    purchases = conn.execute(
        """SELECT * FROM purchases WHERE user_id=? AND status='approved'
           AND (expires_at IS NULL OR expires_at > datetime('now'))
           ORDER BY created_at DESC""",
        (user.id,)
    ).fetchall()

    purchased_terms = []
    purchased_units = []

    for p in purchases:
        if p['item_type'] == 'term':
            term = conn.execute("""
                SELECT t.*, g.title as grade_title
                FROM terms t JOIN grades g ON g.id=t.grade_id
                WHERE t.id=?
            """, (p['item_id'],)).fetchone()
            if term:
                ucount = conn.execute(
                    "SELECT COUNT(*) as c FROM units WHERE term_id=?", (term['id'],)
                ).fetchone()['c']
                pending_upgrade = conn.execute(
                    """SELECT id FROM payment_requests
                       WHERE user_id=? AND item_type='term' AND item_id=?
                       AND status='pending' AND is_upgrade=1""",
                    (user.id, term['id'])
                ).fetchone()
                purchased_terms.append({
                    'term': term, 'tier': p['tier'], 'unit_count': ucount,
                    'pending_upgrade': bool(pending_upgrade), 'expires_at': p['expires_at']
                })
        elif p['item_type'] == 'unit':
            unit = conn.execute("""
                SELECT u.*, g.title as grade_title, t.id as term_id, t.title as term_title
                FROM units u
                JOIN grades g ON g.id=u.grade_id
                LEFT JOIN terms t ON t.id=u.term_id
                WHERE u.id=?
            """, (p['item_id'],)).fetchone()
            if unit:
                lcount = conn.execute(
                    "SELECT COUNT(*) as c FROM lessons WHERE unit_id=?", (unit['id'],)
                ).fetchone()['c']
                pending_upgrade = conn.execute(
                    """SELECT id FROM payment_requests
                       WHERE user_id=? AND item_type='unit' AND item_id=?
                       AND status='pending' AND is_upgrade=1""",
                    (user.id, unit['id'])
                ).fetchone()
                purchased_units.append({
                    'unit': unit, 'tier': p['tier'], 'lesson_count': lcount,
                    'pending_upgrade': bool(pending_upgrade), 'expires_at': p['expires_at']
                })

    last_progress = conn.execute(
        "SELECT * FROM progress WHERE user_id=? ORDER BY last_watched DESC LIMIT 1", (user.id,)
    ).fetchone()

    last_lesson = None
    if last_progress:
        last_lesson = conn.execute(
            "SELECT l.*, u.title as unit_title FROM lessons l JOIN units u ON u.id=l.unit_id WHERE l.id=?",
            (last_progress['lesson_id'],)
        ).fetchone()

    pending_count = conn.execute(
        "SELECT COUNT(*) as c FROM payment_requests WHERE user_id=? AND status='pending'", (user.id,)
    ).fetchone()['c']

    rejected_requests = conn.execute(
        """SELECT pr.*, 
               CASE pr.item_type 
                 WHEN 'unit' THEN (SELECT title FROM units WHERE id=pr.item_id)
                 WHEN 'term' THEN (SELECT title FROM terms WHERE id=pr.item_id)
               END as item_title
           FROM payment_requests pr
           WHERE pr.user_id=? AND pr.status='rejected' AND pr.seen=0
           ORDER BY pr.reviewed_at DESC""",
        (user.id,)
    ).fetchall()

    conn.close()
    return render_template('dashboard.html',
                           purchased_terms=purchased_terms,
                           purchased_units=purchased_units,
                           last_lesson=last_lesson,
                           last_progress=last_progress,
                           pending_requests=pending_count,
                           rejected_requests=rejected_requests)


@student_bp.route('/progress/update', methods=['POST'])
@login_required
def update_progress():
    user = get_current_user()

    data = request.get_json(silent=True)
    if not data:
        return jsonify({'error': 'invalid request'}), 400

    lesson_id = data.get('lesson_id')
    try:
        watch_percent = float(data.get('watch_percent', 0))
    except (TypeError, ValueError):
        return jsonify({'error': 'invalid watch_percent'}), 400

    if not lesson_id:
        return jsonify({'error': 'missing lesson_id'}), 400

    conn = get_db()

    # Verify lesson exists and student has access to its unit
    lesson = conn.execute(
        "SELECT unit_id FROM lessons WHERE id=?", (lesson_id,)
    ).fetchone()
    if not lesson:
        conn.close()
        return jsonify({'error': 'lesson not found'}), 404

    access = user.has_access('unit', lesson['unit_id'])
    if not access and not user.is_admin:
        conn.close()
        return jsonify({'error': 'access denied'}), 403

    completed = (watch_percent >= 90)

    existing = conn.execute(
        "SELECT * FROM progress WHERE user_id=? AND lesson_id=?", (user.id, lesson_id)
    ).fetchone()

    if existing:
        new_percent = max(existing['watch_percent'], watch_percent)
        new_completed = existing['completed'] or completed
        conn.execute("""UPDATE progress SET watch_percent=?, completed=?, last_watched=datetime('now')
                        WHERE user_id=? AND lesson_id=?""",
                     (new_percent, int(new_completed), user.id, lesson_id))
    else:
        conn.execute("""INSERT INTO progress (user_id, lesson_id, watch_percent, completed)
                        VALUES (?,?,?,?)""", (user.id, lesson_id, watch_percent, int(completed)))

    conn.commit()
    conn.close()
    return jsonify({'completed': completed, 'watch_percent': watch_percent})



@student_bp.route('/delete-account', methods=['POST'])
@login_required
def delete_account():
    user = get_current_user()
    password = request.form.get('password', '')

    conn = get_db()
    row = conn.execute("SELECT password_hash FROM users WHERE id=?", (user.id,)).fetchone()

    from werkzeug.security import check_password_hash
    if not row or not check_password_hash(row['password_hash'], password):
        conn.close()
        flash('كلمة المرور غير صحيحة', 'danger')
        return redirect(url_for('student.dashboard'))

    conn.execute("DELETE FROM progress WHERE user_id=?", (user.id,))
    conn.execute("DELETE FROM purchases WHERE user_id=?", (user.id,))
    conn.execute("DELETE FROM payment_requests WHERE user_id=?", (user.id,))
    conn.execute("DELETE FROM users WHERE id=?", (user.id,))
    conn.commit()
    conn.close()
    session.clear()
    flash('تم حذف حسابك وجميع بياناتك بنجاح', 'success')
    return redirect(url_for('main.index'))





@student_bp.route('/dismiss-rejection/<int:rid>', methods=['POST'])
@login_required
def dismiss_rejection(rid):
    user = get_current_user()
    conn = get_db()
    conn.execute(
        "UPDATE payment_requests SET seen=1 WHERE id=? AND user_id=?", (rid, user.id)
    )
    conn.commit()
    conn.close()
    return ('', 204)
