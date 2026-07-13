"""
migrate.py — Jute Sliver Analyzer database migration
=====================================================
Migrates data from any old app.db into the current schema.

Usage:
    python migrate.py --old <path/to/old/app.db> --new <path/to/new/app.db>

    If --new is omitted, defaults to ./app.db (next to this script).
    The new DB is created fresh if it doesn't exist yet.

What it migrates:
    • users        — name + created_at (skips duplicates by name)
    • batches      — all columns, adding machine_type=NULL if missing
    • samples      — all columns, adding machine_type=NULL if missing;
                     image_path is kept as-is (point images folder at same place)
    • width_samples — all columns
    • machines     — custom (non-default) machine types

What it does NOT touch:
    • Default machine types (re-seeded by the app on startup)
    • Any data already in the new DB (no overwrites, INSERT OR IGNORE on conflicts)

Run this BEFORE starting the new app for the first time, or with the app stopped.
"""

import argparse, sqlite3, os, sys
from pathlib import Path

DEFAULT_MACHINE_TYPES = {'Drawhead(sliver)', 'Draw-1', 'Draw-2', 'Draw-3', 'Spinning'}

def cols(conn, table):
    return {r[1] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()}

def table_exists(conn, table):
    return conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)
    ).fetchone() is not None

def migrate(old_path, new_path):
    if not os.path.exists(old_path):
        sys.exit(f"ERROR: old DB not found: {old_path}")

    print(f"  Old DB : {old_path}")
    print(f"  New DB : {new_path}")
    print()

    old = sqlite3.connect(old_path)
    old.row_factory = sqlite3.Row

    # ── initialise new DB schema directly ────────────────────────────────────
    new = sqlite3.connect(new_path)
    new.row_factory = sqlite3.Row
    new.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS batches (
            id TEXT PRIMARY KEY,
            user_id INTEGER NOT NULL REFERENCES users(id),
            name TEXT NOT NULL,
            notes TEXT,
            machine_type TEXT,
            closed INTEGER NOT NULL DEFAULT 0,
            closed_at TEXT,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS samples (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL REFERENCES users(id),
            batch_id TEXT REFERENCES batches(id) ON DELETE SET NULL,
            original_filename TEXT,
            image_path TEXT NOT NULL,
            width INTEGER, height INTEGER, score INTEGER,
            mean_angle_deg REAL, resultant_length_r REAL,
            circular_variance REAL, angular_stddev_deg REAL,
            edge_pixel_count INTEGER, histogram_json TEXT,
            notes TEXT, machine_type TEXT,
            analyzed INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        );
        CREATE INDEX IF NOT EXISTS idx_samples_user    ON samples(user_id);
        CREATE INDEX IF NOT EXISTS idx_samples_created ON samples(created_at);
        CREATE INDEX IF NOT EXISTS idx_samples_batch   ON samples(batch_id);
        CREATE INDEX IF NOT EXISTS idx_samples_machine ON samples(machine_type);
        CREATE TABLE IF NOT EXISTS machines (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            is_default INTEGER NOT NULL DEFAULT 0,
            sort_order INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS width_samples (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL REFERENCES users(id),
            set_label TEXT NOT NULL DEFAULT 'A',
            original_filename TEXT, image_path TEXT NOT NULL,
            image_width INTEGER, image_height INTEGER, rows_measured INTEGER,
            mean_width_px REAL, median_width_px REAL,
            min_width_px REAL, max_width_px REAL, sd_width_px REAL,
            row_widths_json TEXT, notes TEXT,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        );
        CREATE INDEX IF NOT EXISTS idx_width_samples_user ON width_samples(user_id);
        CREATE INDEX IF NOT EXISTS idx_width_samples_set  ON width_samples(set_label);
    """)
    # Seed default machine types
    for i, name in enumerate(DEFAULT_MACHINE_TYPES):
        new.execute(
            "INSERT OR IGNORE INTO machines (name, is_default, sort_order) VALUES (?,1,?)",
            (name, i)
        )
    new.commit()
    print("  ✓ New DB schema initialised")

    stats = {}

    # ── 1. USERS ──────────────────────────────────────────────────────────────
    if table_exists(old, 'users'):
        old_users = old.execute("SELECT * FROM users").fetchall()
        inserted = 0
        user_id_map = {}  # old_id → new_id
        new_cols = cols(new, 'users')
        for u in old_users:
            u = dict(u)
            name = u['name']
            existing = new.execute("SELECT id FROM users WHERE name=?", (name,)).fetchone()
            if existing:
                user_id_map[u['id']] = existing['id']
            else:
                cur = new.execute(
                    "INSERT INTO users (name, created_at) VALUES (?, ?)",
                    (name, u.get('created_at'))
                )
                user_id_map[u['id']] = cur.lastrowid
                inserted += 1
        new.commit()
        stats['users'] = (len(old_users), inserted)
        print(f"  ✓ users        : {len(old_users)} found, {inserted} inserted, {len(old_users)-inserted} already existed")
    else:
        print("  – users        : table not in old DB, skipped")
        user_id_map = {}

    def map_user(old_id):
        return user_id_map.get(old_id, old_id)

    # ── 2. MACHINES (custom only) ─────────────────────────────────────────────
    if table_exists(old, 'machines'):
        old_machines = old.execute(
            "SELECT * FROM machines WHERE is_default=0 OR name NOT IN ({})".format(
                ','.join('?' * len(DEFAULT_MACHINE_TYPES))
            ), list(DEFAULT_MACHINE_TYPES)
        ).fetchall()
        inserted = 0
        for m in old_machines:
            m = dict(m)
            try:
                new.execute(
                    "INSERT OR IGNORE INTO machines (name, is_default, sort_order, created_at) VALUES (?,?,?,?)",
                    (m['name'], 0, m.get('sort_order', 99), m.get('created_at'))
                )
                inserted += 1
            except Exception:
                pass
        new.commit()
        print(f"  ✓ machines     : {inserted} custom machine(s) inserted")
    else:
        print("  – machines     : table not in old DB, skipped")

    # ── 3. BATCHES ────────────────────────────────────────────────────────────
    if table_exists(old, 'batches'):
        old_batches = old.execute("SELECT * FROM batches").fetchall()
        old_batch_cols = cols(old, 'batches')
        inserted = 0
        for b in old_batches:
            b = dict(b)
            existing = new.execute("SELECT id FROM batches WHERE id=?", (b['id'],)).fetchone()
            if existing:
                continue
            new.execute(
                """INSERT OR IGNORE INTO batches
                   (id, user_id, name, notes, machine_type, closed, closed_at, created_at)
                   VALUES (?,?,?,?,?,?,?,?)""",
                (
                    b['id'],
                    map_user(b['user_id']),
                    b.get('name', ''),
                    b.get('notes'),
                    b.get('machine_type'),          # NULL in old schema → fine
                    b.get('closed', 0),
                    b.get('closed_at'),
                    b.get('created_at'),
                )
            )
            inserted += 1
        new.commit()
        stats['batches'] = (len(old_batches), inserted)
        print(f"  ✓ batches      : {len(old_batches)} found, {inserted} inserted")
    else:
        print("  – batches      : table not in old DB, skipped")

    # ── 4. SAMPLES ────────────────────────────────────────────────────────────
    if table_exists(old, 'samples'):
        old_samples = old.execute("SELECT * FROM samples").fetchall()
        old_sample_cols = cols(old, 'samples')
        inserted = 0
        skipped = 0
        for s in old_samples:
            s = dict(s)
            existing = new.execute("SELECT id FROM samples WHERE id=?", (s['id'],)).fetchone()
            if existing:
                skipped += 1
                continue
            new.execute(
                """INSERT OR IGNORE INTO samples
                   (id, user_id, batch_id, original_filename, image_path,
                    width, height, score,
                    mean_angle_deg, resultant_length_r, circular_variance,
                    angular_stddev_deg, edge_pixel_count, histogram_json,
                    notes, machine_type, analyzed, created_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    s['id'],
                    map_user(s['user_id']),
                    s.get('batch_id'),
                    s.get('original_filename'),
                    s.get('image_path', ''),
                    s.get('width'),
                    s.get('height'),
                    s.get('score'),
                    s.get('mean_angle_deg'),
                    s.get('resultant_length_r'),
                    s.get('circular_variance'),
                    s.get('angular_stddev_deg'),
                    s.get('edge_pixel_count'),
                    s.get('histogram_json'),
                    s.get('notes'),
                    s.get('machine_type'),           # NULL in old schema → fine
                    s.get('analyzed', 1),
                    s.get('created_at'),
                )
            )
            inserted += 1
        new.commit()
        stats['samples'] = (len(old_samples), inserted)
        print(f"  ✓ samples      : {len(old_samples)} found, {inserted} inserted, {skipped} already existed")
    else:
        print("  – samples      : table not in old DB, skipped")

    # ── 5. WIDTH_SAMPLES ─────────────────────────────────────────────────────
    if table_exists(old, 'width_samples'):
        old_ws = old.execute("SELECT * FROM width_samples").fetchall()
        inserted = 0
        skipped = 0
        for w in old_ws:
            w = dict(w)
            existing = new.execute("SELECT id FROM width_samples WHERE id=?", (w['id'],)).fetchone()
            if existing:
                skipped += 1
                continue
            new.execute(
                """INSERT OR IGNORE INTO width_samples
                   (id, user_id, set_label, original_filename, image_path,
                    image_width, image_height, rows_measured,
                    mean_width_px, median_width_px, min_width_px, max_width_px,
                    sd_width_px, row_widths_json, notes, created_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    w['id'],
                    map_user(w['user_id']),
                    w.get('set_label', 'A'),
                    w.get('original_filename'),
                    w.get('image_path', ''),
                    w.get('image_width'),
                    w.get('image_height'),
                    w.get('rows_measured'),
                    w.get('mean_width_px'),
                    w.get('median_width_px'),
                    w.get('min_width_px'),
                    w.get('max_width_px'),
                    w.get('sd_width_px'),
                    w.get('row_widths_json'),
                    w.get('notes'),
                    w.get('created_at'),
                )
            )
            inserted += 1
        new.commit()
        stats['width_samples'] = (len(old_ws), inserted)
        print(f"  ✓ width_samples: {len(old_ws)} found, {inserted} inserted, {skipped} already existed")
    else:
        print("  – width_samples: table not in old DB, skipped")

    old.close()
    new.close()
    print()
    print("  Migration complete.")
    print()
    print("  NOTE: Images are referenced by path in the DB.")
    print("  Make sure the old 'uploads/' folder is copied next to the new app.db,")
    print("  or the app will show broken images for migrated samples.")


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="Migrate old juteapp DB to new schema")
    parser.add_argument('--old', required=True, help="Path to the OLD app.db")
    parser.add_argument('--new', default='app.db',  help="Path to the NEW app.db (default: ./app.db)")
    args = parser.parse_args()

    print()
    print("=" * 55)
    print("  Jute Sliver Analyzer — DB Migration")
    print("=" * 55)
    migrate(args.old, args.new)
