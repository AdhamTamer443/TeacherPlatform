import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / 'teacher.db'


def get_db():
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    conn = get_db()
    c = conn.cursor()

    # One-time migration: if terms table doesn't exist yet, wipe old content tables
    # and rebuild with the new schema (user confirmed data can be cleared)
    terms_exists = c.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='terms'"
    ).fetchone()

    if not terms_exists:
        c.executescript("""
            PRAGMA foreign_keys = OFF;
            DROP TABLE IF EXISTS progress;
            DROP TABLE IF EXISTS payment_requests;
            DROP TABLE IF EXISTS purchases;
            DROP TABLE IF EXISTS lessons;
            DROP TABLE IF EXISTS units;
            DROP TABLE IF EXISTS grades;
            PRAGMA foreign_keys = ON;
        """)

    c.executescript("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        phone TEXT UNIQUE NOT NULL,
        email TEXT UNIQUE,
        password_hash TEXT NOT NULL,
        is_admin INTEGER DEFAULT 0,
        is_active INTEGER DEFAULT 1,
        created_at TEXT DEFAULT (datetime('now'))
    );

    CREATE TABLE IF NOT EXISTS grades (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT NOT NULL,
        description TEXT,
        image TEXT,
        order_index INTEGER DEFAULT 0
    );

    CREATE TABLE IF NOT EXISTS terms (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        grade_id INTEGER NOT NULL REFERENCES grades(id) ON DELETE CASCADE,
        title TEXT NOT NULL,
        description TEXT,
        order_index INTEGER DEFAULT 0,
        bronze_price REAL DEFAULT 0,
        silver_price REAL DEFAULT 0,
        gold_price REAL DEFAULT 0
    );

    CREATE TABLE IF NOT EXISTS units (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        grade_id INTEGER NOT NULL REFERENCES grades(id) ON DELETE CASCADE,
        term_id INTEGER REFERENCES terms(id) ON DELETE SET NULL,
        title TEXT NOT NULL,
        description TEXT,
        thumbnail TEXT,
        order_index INTEGER DEFAULT 0,
        bronze_price REAL DEFAULT 0,
        silver_price REAL DEFAULT 0,
        gold_price REAL DEFAULT 0
    );

    CREATE TABLE IF NOT EXISTS lessons (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        unit_id INTEGER NOT NULL REFERENCES units(id) ON DELETE CASCADE,
        title TEXT NOT NULL,
        description TEXT,
        video_url TEXT,
        exercise_easy_pdf TEXT,
        exercise_hard_pdf TEXT,
        brief_pdf TEXT,
        order_index INTEGER DEFAULT 0,
        duration_minutes INTEGER DEFAULT 0
    );

    CREATE TABLE IF NOT EXISTS purchases (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL REFERENCES users(id),
        item_type TEXT NOT NULL,
        item_id INTEGER NOT NULL,
        tier TEXT NOT NULL,
        status TEXT DEFAULT 'approved',
        created_at TEXT DEFAULT (datetime('now'))
    );

    CREATE TABLE IF NOT EXISTS payment_requests (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL REFERENCES users(id),
        item_type TEXT NOT NULL,
        item_id INTEGER NOT NULL,
        tier TEXT NOT NULL,
        amount REAL NOT NULL,
        screenshot_path TEXT,
        status TEXT DEFAULT 'pending',
        admin_note TEXT,
        seen INTEGER DEFAULT 0,
        is_upgrade INTEGER DEFAULT 0,
        target_tier TEXT,
        created_at TEXT DEFAULT (datetime('now')),
        reviewed_at TEXT
    );

    CREATE TABLE IF NOT EXISTS progress (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL REFERENCES users(id),
        lesson_id INTEGER NOT NULL REFERENCES lessons(id) ON DELETE CASCADE,
        completed INTEGER DEFAULT 0,
        watch_percent REAL DEFAULT 0,
        last_watched TEXT DEFAULT (datetime('now')),
        UNIQUE(user_id, lesson_id)
    );
    """)
    # Migrations for existing databases
    purchase_cols = [r[1] for r in conn.execute("PRAGMA table_info(purchases)").fetchall()]
    if 'expires_at' not in purchase_cols:
        conn.execute("ALTER TABLE purchases ADD COLUMN expires_at TEXT")
        conn.execute("UPDATE purchases SET expires_at = datetime(created_at, '+1 year') WHERE expires_at IS NULL")

    cols = [r[1] for r in conn.execute("PRAGMA table_info(payment_requests)").fetchall()]
    if 'seen' not in cols:
        conn.execute("ALTER TABLE payment_requests ADD COLUMN seen INTEGER DEFAULT 0")
    if 'is_upgrade' not in cols:
        conn.execute("ALTER TABLE payment_requests ADD COLUMN is_upgrade INTEGER DEFAULT 0")
    if 'target_tier' not in cols:
        conn.execute("ALTER TABLE payment_requests ADD COLUMN target_tier TEXT")

    # 60-day cleanup: delete screenshot files and null the path
    import os as _os
    old_shots = conn.execute("""
        SELECT id, screenshot_path FROM payment_requests
        WHERE screenshot_path IS NOT NULL
        AND reviewed_at IS NOT NULL
        AND reviewed_at < datetime('now', '-60 days')
    """).fetchall()
    for row in old_shots:
        full = Path(__file__).parent / 'static' / 'uploads' / 'screenshots' / row['screenshot_path']
        try:
            if full.exists():
                full.unlink()
        except Exception:
            pass
        conn.execute("UPDATE payment_requests SET screenshot_path=NULL WHERE id=?", (row['id'],))

    conn.commit()
    conn.close()


def seed_admin():
    from werkzeug.security import generate_password_hash
    conn = get_db()
    existing = conn.execute("SELECT id FROM users WHERE is_admin=1").fetchone()
    if not existing:
        conn.execute("""INSERT INTO users (name, phone, email, password_hash, is_admin)
                        VALUES (?,?,?,?,1)""",
                     ('المدير', '01000000000', 'admin@teacher.com',
                      generate_password_hash('Admin@1234')))
        conn.commit()
    conn.close()


# ── Helpers ──────────────────────────────────────

def get_youtube_embed(url):
    if not url:
        return None
    if 'youtu.be/' in url:
        vid = url.split('youtu.be/')[-1].split('?')[0]
    elif 'v=' in url:
        vid = url.split('v=')[-1].split('&')[0]
    elif 'embed/' in url:
        vid = url.split('embed/')[-1].split('?')[0]
    else:
        vid = url
    return f'https://www.youtube.com/embed/{vid}?enablejsapi=1'


def get_user_access(user_id, item_type, item_id):
    """Return highest tier the user has for this item, or None."""
    conn = get_db()
    row = conn.execute("""SELECT tier FROM purchases
                          WHERE user_id=? AND item_type=? AND item_id=? AND status='approved'
                          AND (expires_at IS NULL OR expires_at > datetime('now'))
                          ORDER BY CASE tier WHEN 'gold' THEN 1 WHEN 'silver' THEN 2 ELSE 3 END
                          LIMIT 1""", (user_id, item_type, item_id)).fetchone()
    conn.close()
    return row['tier'] if row else None


def tier_rank(tier):
    return {'bronze': 1, 'silver': 2, 'gold': 3}.get(tier, 0)
