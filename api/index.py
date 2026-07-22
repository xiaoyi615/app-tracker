# App Tracker - Vercel Serverless API
# Set env vars: POSTGRES_URL, DEEPSEEK_API_KEY

from http.server import BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
from datetime import datetime, timezone, timedelta
import json
import os

# Database setup
DATABASE_URL = os.environ.get("POSTGRES_URL", os.environ.get("DATABASE_URL", ""))
use_pg = False
if DATABASE_URL and "postgres" in DATABASE_URL:
    try:
        import psycopg2
        import psycopg2.extras
        use_pg = True
    except ImportError:
        pass

class AppRecord:
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)
    def to_dict(self):
        d = dict(self.__dict__)
        if 'timestamp' in d and hasattr(d['timestamp'], 'isoformat'):
            d['timestamp'] = d['timestamp'].isoformat()
        if 'created_at' in d and hasattr(d['created_at'], 'isoformat'):
            d['created_at'] = d['created_at'].isoformat()
        return d

def _pg():
    if not use_pg: return None
    return psycopg2.connect(DATABASE_URL)

def init_db():
    if not use_pg: return
    try:
        c = _pg(); cur = c.cursor()
        cur.execute("CREATE TABLE IF NOT EXISTS app_records (id SERIAL PRIMARY KEY, app_name VARCHAR(200) NOT NULL, action VARCHAR(20) NOT NULL DEFAULT 'open', timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(), created_at TIMESTAMPTZ NOT NULL DEFAULT NOW())")
        c.commit(); cur.close(); c.close()
    except Exception as e: print(f"DB init: {e}")

def q(where="", params=None, order="timestamp DESC", limit=100):
    if not use_pg: return []
    try:
        c = _pg(); cur = c.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        sql = "SELECT * FROM app_records"
        if where: sql += f" WHERE {where}"
        sql += f" ORDER BY {order} LIMIT {limit}"
        cur.execute(sql, params or ())
        rows = [AppRecord(**r) for r in cur.fetchall()]
        cur.close(); c.close(); return rows
    except: return []

def do_insert(app_name, action, ts):
    if not use_pg: return None
    try:
        c = _pg(); cur = c.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute("INSERT INTO app_records (app_name,action,timestamp) VALUES (%s,%s,%s) RETURNING *", (app_name, action, ts))
        c.commit(); r = AppRecord(**cur.fetchone())
        cur.close(); c.close(); return r
    except: return None

def count_records():
    if not use_pg: return 0
    try:
        c = _pg(); cur = c.cursor()
        cur.execute("SELECT COUNT(*) FROM app_records"); n = cur.fetchone()[0]
        cur.close(); c.close(); return n
    except: return 0

DEEPSEEK_API_KEY = os.environ.get("DEEPSEEK_API_KEY", "")

def ask_deepseek(messages, max_tokens=1024):
    if not DEEPSEEK_API_KEY: return None, "DeepSeek key not set"
    try:
        import requests
        r = requests.post("https://api.deepseek.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {DEEPSEEK_API_KEY}", "Content-Type": "application/json"},
            json={"model": "deepseek-chat", "messages": messages, "max_tokens": max_tokens, "temperature": 0.3, "stream": False},
            timeout=30)
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"], None
    except Exception as e: return None, str(e)

def analyze(records, question):
    if not records: return "还没有使用记录哦～"
    now = datetime.now(timezone.utc) + timedelta(hours=8)
    txt = "\n".join([f"{r.to_dict()['timestamp']} - {r.to_dict()['app_name']} ({'打开' if r.to_dict()['action']=='open' else '关闭'})" for r in records])
    sp = f"你是一个手机使用记录分析助手。当前时间：{now.strftime('%Y-%m-%d %H:%M')}\n\n以下是用户手机 App 使用记录：\n\n{txt}\n\n回答用户问题，简洁、友好、基于数据。如果涉及'昨晚'，指前一天18:00到当天06:00。精确计算时间。"
    reply, err = ask_deepseek([{"role": "system", "content": sp}, {"role": "user", "content": question}])
    if err:
        app_counts = {}
        for r in records:
            d = r.to_dict()
            if d['action'] == 'open': app_counts[d['app_name']] = app_counts.get(d['app_name'], 0) + 1
        return f"📊 共找到 {len(records)} 条记录，涉及 {len(app_counts)} 个App：\n" + "\n".join([f"  • {n}：打开 {c} 次" for n, c in sorted(app_counts.items(), key=lambda x: -x[1])])
    return reply

init_db()

def make_json(data, status=200):
    return (status, {"Content-Type": "application/json"}, json.dumps(data, ensure_ascii=False))

class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        p = urlparse(self.path).path
        qs = parse_qs(urlparse(self.path).query)
        if p == "/api/health":
            self._respond(200, {"success": True, "status": "running", "total_records": count_records(), "version": "1.0.0", "db_type": "postgresql" if use_pg else "none"})
        elif p == "/api/records/today":
            t = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
            self._respond(200, {"success": True, "records": [r.to_dict() for r in q("timestamp >= %s", (t,), "timestamp DESC", 200)]})
        elif p == "/api/records/today/stats":
            t = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
            recs = q("timestamp >= %s", (t,), "timestamp ASC", 500)
            opens = {}
            for r in recs:
                d = r.to_dict()
                if d['action'] == 'open': opens[d['app_name']] = opens.get(d['app_name'], 0) + 1
            top = sorted(opens.items(), key=lambda x: -x[1])[:10]
            self._respond(200, {"success": True, "date": datetime.now(timezone.utc).strftime("%Y-%m-%d"), "total_records": len(recs), "total_opens": sum(opens.values()), "top_apps": [{"name": n, "count": c} for n, c in top]})
        elif p == "/api/records/range":
            conds, vals = [], []
            st = qs.get("start", [None])[0]
            en = qs.get("end", [None])[0]
            an = qs.get("app_name", [None])[0]
            lm = int(qs.get("limit", [100])[0])
            if st: conds.append("timestamp >= %s"); vals.append(st)
            if en: conds.append("timestamp <= %s"); vals.append(en)
            if an: conds.append("app_name ILIKE %s"); vals.append(f"%{an}%")
            wh = " AND ".join(conds) if conds else ""
            self._respond(200, {"success": True, "records": [r.to_dict() for r in q(wh, tuple(vals) if vals else None, "timestamp DESC", lm)]})
        else:
            self._respond(404, {"success": False, "error": "Not found"})

    def do_POST(self):
        p = urlparse(self.path).path
        body = {}
        try:
            cl = int(self.headers.get("Content-Length", 0))
            if cl > 0:
                body = json.loads(self.rfile.read(cl).decode())
        except: pass
        
        if p == "/api/record":
            app_name = body.get("app_name", "").strip()
            action = body.get("action", "open").strip()
            if not app_name: return self._respond(400, {"success": False, "error": "app_name required"})
            if action not in ["open", "close"]: action = "open"
            r = do_insert(app_name, action, datetime.now(timezone.utc))
            self._respond(201, {"success": True, "record": r.to_dict() if r else {"app_name": app_name, "action": action}})
        elif p == "/api/record/batch":
            created = []
            for item in body.get("records", []):
                an = item.get("app_name", "").strip()
                if not an: continue
                r = do_insert(an, item.get("action", "open"), datetime.now(timezone.utc))
                if r: created.append(r.to_dict())
            self._respond(201, {"success": True, "count": len(created), "records": created})
        elif p == "/api/ask":
            qq = body.get("question", "").strip()
            if not qq: return self._respond(400, {"success": False, "error": "question required"})
            st = datetime.now(timezone.utc) - timedelta(days=7)
            recs = q("timestamp >= %s", (st,), "timestamp ASC", 1000)
            self._respond(200, {"success": True, "question": qq, "answer": analyze(recs, qq), "record_count": len(recs)})
        else:
            self._respond(404, {"success": False, "error": "Not found"})

    def _respond(self, status, data):
        s, h, b = status, {"Content-Type": "application/json"}, json.dumps(data, ensure_ascii=False)
        self.send_response(s)
        for k, v in h.items(): self.send_header(k, v)
        self.end_headers()
        self.wfile.write(b.encode())
    
    # Silent: do not log to stderr
    def log_message(self, format, *args):
        pass