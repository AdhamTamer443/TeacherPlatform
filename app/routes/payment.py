import os
from flask import Blueprint, render_template, request, redirect, url_for, flash, current_app
from werkzeug.utils import secure_filename
from ..db import get_db
from ..auth_utils import login_required, get_current_user

payment_bp = Blueprint('payment', __name__)


@payment_bp.route('/checkout/<item_type>/<int:item_id>', methods=['GET', 'POST'])
@login_required
def checkout(item_type, item_id):
    user = get_current_user()
    conn = get_db()

    if item_type == 'unit':
        item = conn.execute("SELECT * FROM units WHERE id=?", (item_id,)).fetchone()
        item_label = 'وحدة دراسية'
    elif item_type == 'term':
        item = conn.execute("SELECT * FROM terms WHERE id=?", (item_id,)).fetchone()
        item_label = 'فصل دراسي كامل'
    else:
        conn.close()
        return redirect(url_for('main.index'))

    if not item:
        conn.close()
        flash('العنصر غير موجود', 'danger')
        return redirect(url_for('main.index'))

    from ..db import tier_rank

    is_upgrade = request.args.get('upgrade') == '1'
    target_tier = request.args.get('target_tier')

    # ── Upgrade path ──────────────────────────────
    if is_upgrade:
        current_tier = user.has_access(item_type, item_id)
        if not current_tier:
            conn.close()
            flash('يجب شراء المحتوى أولاً قبل الترقية', 'danger')
            return redirect(url_for('student.dashboard'))
        if current_tier == 'gold':
            conn.close()
            flash('أنت بالفعل على أعلى باقة', 'info')
            return redirect(url_for('student.dashboard'))
        if target_tier not in ('silver', 'gold') or tier_rank(target_tier) <= tier_rank(current_tier):
            conn.close()
            flash('باقة الترقية غير صحيحة', 'danger')
            return redirect(url_for('student.dashboard'))

        price = max(item[f'{target_tier}_price'] - item[f'{current_tier}_price'], 0)
        tier = target_tier

        term_unit_count = None
        if item_type == 'term':
            term_unit_count = conn.execute(
                "SELECT COUNT(*) as c FROM units WHERE term_id=?", (item_id,)
            ).fetchone()['c']

        if request.method == 'POST':
            pending = conn.execute(
                """SELECT id FROM payment_requests
                   WHERE user_id=? AND item_type=? AND item_id=?
                   AND status='pending' AND is_upgrade=1""",
                (user.id, item_type, item_id)
            ).fetchone()
            if pending:
                conn.close()
                flash('طلب الترقية قيد المراجعة بالفعل', 'warning')
                return redirect(url_for('student.dashboard'))

            file = request.files.get('screenshot')
            screenshot_name = None
            if file and file.filename:
                ext = file.filename.rsplit('.', 1)[-1].lower()
                if ext in ('png', 'jpg', 'jpeg', 'gif'):
                    safe = secure_filename(f"upg_{user.id}_{item_type}_{item_id}_{tier}.{ext}")
                    save_path = os.path.join(current_app.config['UPLOAD_FOLDER'], 'screenshots', safe)
                    os.makedirs(os.path.dirname(save_path), exist_ok=True)
                    file.save(save_path)
                    screenshot_name = safe
                else:
                    conn.close()
                    flash('نوع الملف غير مدعوم', 'danger')
                    return redirect(request.url)
            else:
                conn.close()
                flash('يجب رفع صورة إيصال الدفع', 'danger')
                return redirect(request.url)

            conn.execute("""INSERT INTO payment_requests
                            (user_id, item_type, item_id, tier, target_tier, amount,
                             screenshot_path, status, is_upgrade)
                            VALUES (?,?,?,?,?,?,?,'pending',1)""",
                         (user.id, item_type, item_id, current_tier, target_tier, price, screenshot_name))
            conn.commit(); conn.close()
            flash('تم إرسال طلب الترقية! سيتم مراجعته خلال 24 ساعة ✅', 'success')
            return redirect(url_for('student.dashboard'))

        conn.close()
        return render_template('checkout.html',
                               item=item, item_type=item_type, item_label=item_label,
                               tier=tier, price=price,
                               is_upgrade=True, current_tier=current_tier,
                               term_unit_count=term_unit_count,
                               instapay=current_app.config['INSTAPAY_NUMBER'])

    # ── Normal purchase path ───────────────────────
    existing = conn.execute(
        "SELECT id FROM purchases WHERE user_id=? AND item_type=? AND item_id=? AND status='approved'",
        (user.id, item_type, item_id)
    ).fetchone()
    if existing:
        conn.close()
        flash('لقد اشتريت هذا المحتوى بالفعل', 'info')
        return redirect(url_for('student.dashboard'))

    tier = request.args.get('tier', 'bronze')
    if tier not in ('bronze', 'silver', 'gold'):
        tier = 'bronze'

    price = item[f'{tier}_price']

    term_unit_count = None
    if item_type == 'term':
        row = conn.execute("SELECT COUNT(*) as c FROM units WHERE term_id=?", (item_id,)).fetchone()
        term_unit_count = row['c']

    if request.method == 'POST':
        tier_post = request.form.get('tier', tier)
        if tier_post not in ('bronze', 'silver', 'gold'):
            tier_post = 'bronze'
        price_post = item[f'{tier_post}_price']

        pending = conn.execute(
            "SELECT id FROM payment_requests WHERE user_id=? AND item_type=? AND item_id=? AND status='pending' AND is_upgrade=0",
            (user.id, item_type, item_id)
        ).fetchone()
        if pending:
            conn.close()
            flash('طلب الدفع قيد المراجعة بالفعل', 'warning')
            return redirect(url_for('student.dashboard'))

        file = request.files.get('screenshot')
        screenshot_name = None
        if file and file.filename:
            ext = file.filename.rsplit('.', 1)[-1].lower()
            if ext in ('png', 'jpg', 'jpeg', 'gif'):
                safe = secure_filename(f"pay_{user.id}_{item_type}_{item_id}_{tier_post}.{ext}")
                save_path = os.path.join(current_app.config['UPLOAD_FOLDER'], 'screenshots', safe)
                os.makedirs(os.path.dirname(save_path), exist_ok=True)
                file.save(save_path)
                screenshot_name = safe
            else:
                conn.close()
                flash('نوع الملف غير مدعوم', 'danger')
                return redirect(request.url)
        else:
            conn.close()
            flash('يجب رفع صورة إيصال الدفع', 'danger')
            return redirect(request.url)

        conn.execute("""INSERT INTO payment_requests
                        (user_id, item_type, item_id, tier, amount, screenshot_path, status)
                        VALUES (?,?,?,?,?,?,'pending')""",
                     (user.id, item_type, item_id, tier_post, price_post, screenshot_name))
        conn.commit()
        conn.close()
        flash('تم إرسال طلب الدفع! سيتم مراجعته خلال 24 ساعة ✅', 'success')
        return redirect(url_for('student.dashboard'))

    conn.close()
    return render_template('checkout.html',
                           item=item, item_type=item_type, item_label=item_label,
                           tier=tier, price=price,
                           is_upgrade=False, current_tier=None,
                           term_unit_count=term_unit_count,
                           instapay=current_app.config['INSTAPAY_NUMBER'])
