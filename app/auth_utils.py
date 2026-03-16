from flask import session
from .db import get_db


class UserProxy:
    """Simple user object stored in session."""
    def __init__(self, row):
        if row:
            self.id = row['id']
            self.name = row['name']
            self.phone = row['phone']
            self.email = row['email']
            self.is_admin = bool(row['is_admin'])
            self.is_active = bool(row['is_active'])
            self.is_authenticated = True
        else:
            self.is_authenticated = False
            self.is_admin = False
            self.id = None
            self.name = ''

    def has_access(self, item_type, item_id):
        """Return highest tier string or None.
        For 'unit': checks direct unit purchase OR parent term purchase.
        For 'term': checks term purchase directly.
        """
        if not self.is_authenticated:
            return None
        conn = get_db()

        if item_type == 'unit':
            # 1. Check direct unit purchase
            row = conn.execute("""
                SELECT tier FROM purchases
                WHERE user_id=? AND item_type='unit' AND item_id=? AND status='approved'
                AND (expires_at IS NULL OR expires_at > datetime('now'))
                ORDER BY CASE tier WHEN 'gold' THEN 1 WHEN 'silver' THEN 2 ELSE 3 END
                LIMIT 1
            """, (self.id, item_id)).fetchone()
            if row:
                conn.close()
                return row['tier']

            # 2. Check if a term purchase covers this unit
            term_row = conn.execute("""
                SELECT p.tier FROM purchases p
                JOIN units u ON u.term_id = p.item_id
                WHERE p.user_id=? AND p.item_type='term' AND u.id=? AND p.status='approved'
                AND (p.expires_at IS NULL OR p.expires_at > datetime('now'))
                ORDER BY CASE p.tier WHEN 'gold' THEN 1 WHEN 'silver' THEN 2 ELSE 3 END
                LIMIT 1
            """, (self.id, item_id)).fetchone()
            conn.close()
            return term_row['tier'] if term_row else None

        else:
            # Direct lookup (term or any future type)
            row = conn.execute("""
                SELECT tier FROM purchases
                WHERE user_id=? AND item_type=? AND item_id=? AND status='approved'
                AND (expires_at IS NULL OR expires_at > datetime('now'))
                ORDER BY CASE tier WHEN 'gold' THEN 1 WHEN 'silver' THEN 2 ELSE 3 END
                LIMIT 1
            """, (self.id, item_type, item_id)).fetchone()
            conn.close()
            return row['tier'] if row else None


_anon = None


def get_current_user():
    global _anon
    uid = session.get('user_id')
    if uid:
        conn = get_db()
        row = conn.execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone()
        conn.close()
        if row and row['is_active']:
            return UserProxy(row)
        session.clear()
    if _anon is None:
        _anon = UserProxy(None)
    return _anon


def login_required(f):
    from functools import wraps
    from flask import redirect, url_for, flash
    @wraps(f)
    def decorated(*args, **kwargs):
        user = get_current_user()
        if not user.is_authenticated:
            flash('يجب تسجيل الدخول للوصول إلى هذه الصفحة', 'warning')
            return redirect(url_for('auth.login'))
        return f(*args, **kwargs)
    return decorated

def admin_required(f):
    from functools import wraps
    from flask import redirect, url_for, flash
    @wraps(f)
    def decorated(*args, **kwargs):
        user = get_current_user()
        if not user.is_authenticated or not user.is_admin:
            flash('غير مصرح لك بالوصول', 'danger')
            return redirect(url_for('auth.login'))
        return f(*args, **kwargs)
    return decorated
