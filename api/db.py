import os
from datetime import datetime, timezone

DATABASE_URL = os.environ.get("POSTGRES_URL", os.environ.get("DATABASE_URL", ""))

use_pg = False
try:
    if DATABASE_URL, "postgres" in DATABASE_URL:        
        import psycopg2
        import psycopg2.extras
        use_pg = True
except ImportError:
    pass

class AppRecord:
    def __init__(self, id=None, app_name="", action="open", timestamp=None, created_at=None):
        self.id = id
        self.app_name = app_name
        self.action = action
        self.timestamp = timestamp or datetime.now(timezone.utc)
        self.created_at = created_at or datetime.now(timezone.utc)

    def to_dict(self):
        return {'id': self.id, 'app_name': self.app_name, 'action': self.action, 'timestamp': self.timestamp.isoformat(), 'created_at': self.created_at.isoformat()}

def get_db_conn():
    if use_pg and DATABASE_URL:
        return psycopg2.connect(DATABASE_URL)
    return None

def init_db():
    if not use_pg:
        return
    try:
        conn = get_db_conn()
        cur = conn.cursor()
        cur.execute("""CREATE TABLE IF NOT EXISTS app_records (
            id SERIAL PRIMARY KEY,
            app_name VARCHAR(200) NOT NULL,
            action VARCHAR(20) NOT NULL DEFAULT 'open',
            timestamp TIMESTAMPTZT NOT NULL DEFAULT NOW(),
            created_at TIMESTAMPTZT NOT NULL DEFAULT NOW()
        );""")
        conn.commit()
        cur.close()
        conn.close()
    except Exception as e:
        print(f"DB init error: {e}")

def query_records(where="", params=None, order="timestamp DESC", limit=100):
    if not use_pg:
        return []
    try:
        conn = get_db_conn()
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        sql = "SELECT * FROM app_records"
        if where:
            sql += " WHERE {}".format(where)
        sql += " ORDER BY {}".format(order)
        if limit:
            sql += " LIMIT {}".format(limit)
        cur.execute(sql, params or ())
        rows = cur.fetchall()
        cur.close()
        conn.close()
        return [AppRecord(id=r['id'], app_name=r['app_name'], action=r['action'], timestamp=r['timestamp'], created_at=r['created_at']) for r in rows]
    except Exception as e:
        print(f"Query error: {e}")
        return []

def insert_record(app_name, action, timestamp):
    if not use_pg:
        return None
    try:
        conn = get_db_conn()
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute(
            "INSERT INTO app_records (app_name, action, timestamp) VALUES (%s, %s, %s) RETURNING *",
            (app_name, action, timestamp)
        )
        conn.commit()
        row = cur.fetchone()
        cur.close()
        conn.close()
        return AppRecord(id=row['id'], app_name=row['app_name'], action=row['action'], timestamp=row['timestamp'], created_at=row['created_at'])
    except Exception as e:
        print(f"Insert error: {e}")
        return None

def count_records(where="", params=None):
    if not use_pg:
        return 0
    try:
        conn = get_db_conn()
        cur = conn.cursor()
        sql = "SELECT COUNT(*) FROM app_records"
        if where:
            sql += " WHERE {}".format(where)
        cur.execute(sql, params or ())
        count = cur.fetchone()[0]
        cur.close()
        conn.close()
        return count
    except:
        return 0
