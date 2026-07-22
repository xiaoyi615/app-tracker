# App Tracker - Vercel Serverless API
# Set env vars: POSTGRES_URL (Neon PostgreSQL connection string)
#                DEEPSEEK_API_KEY (optional, for AI chat)

from urllib.parse import urlparse, parse_qs
from datetime import datetime, timezone, timedelta
import json
import os

# Database setup
DATABASE_URL = os.environ.get("POSTGRES_URL", os.environ.get("DATABASE_URL", ""))
use_pg = False
try:
    if DATABASE_URL and "postgres" in DATABASE_URL:
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
        return {'id': self.id, 'app_name': self.app_name, 'action': self.action,
                'timestamp': self.timestamp.isoformat(), 'created_at': self.created_at.isoformat()}

def get_db_conn():
    if use_pg and DATABASE_URL:
        return psycopg2.connect(DATABASE_URL)
    return None

def init_db():
    if not use_pg: return
    try:
        conn = get_db_conn()
        cur = conn.cursor()
        cur.execute("""CREATE TABLE IF NOT EXISTS app_records (
            id SERIAL PRIMARY KEY,
            app_name VARCHAR(200) NOT NULL,
            action VARCHAR(20) NOT NULL DEFAULT 'open',
            timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );""")
        conn.commit()
        cur.close()
        conn.close()
    except Exception as e:
        print(f"DB init error: {e}")

def query_records(where="", params=None, order="timestamp DESC", limit=100):
    if not use_pg: return []
    try:
        conn = get_db_conn()
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        sql = "SELECT * FROM app_records"
        if where: sql += f" WHERE {where}"
        sql += f" ORDER BY {order}"
        if limit: sql += f" LIMIT {limit}"
        cur.execute(sql, params or ())
        rows = cur.fetchall()
        cur.close()
        conn.close()
        return [AppRecord(id=r['id'], app_name=r['app_name'], action=r['action'],
                          timestamp=r['timestamp'], created_at=r['created_at']) for r in rows]
    except: return []

def insert_record(app_name, action, timestamp):
    if not use_pg: return None
    try:
        conn = get_db_conn()
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute("INSERT INTO app_records (app_name, action, timestamp) VALUES (%s,%s,%s) RETURNING *",
                    (app_name, action, timestamp))
        conn.commit()
        row = cur.fetchone()
        cur.close(); conn.close()
        return AppRecord(id=row['id'], app_name=row['app_name'], action=row['action'],
                         timestamp=row['timestamp'], created_at=row['created_at'])
    except: return None

def count_records():
    if not use_pg: return 0
    try:
        conn = get_db_conn(); cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM app_records")
        c = cur.fetchone()[0]; cur.close(); conn.close(); return c
    except: return 0

# Utils
DEEPSEEK_API_KEY = os.environ.get("DEEPSEEK_API_KEY", "")
DEEPSEEK_API_URL = "https://api.deepseek.com/v1/chat/completions"

def query_deepseek(messages, max_tokens=1024):
    if not DEEPSEEK_API_KEY: return None, "DeepSeek key not set"
    try:
        import requests
        headers = {"Authorization": f"Bearer {DEEPSEEK_API_KEY}", "Content-Type": "application/json"}
        payload = {"model": "deepseek-chat", "messages": messages, "max_tokens": max_tokens, "temperature": 0.3, "stream": False}
        resp = requests.post(DEEPSEEK_API_URL, headers=headers, json=payload, timeout=30)
        resp.raise_for_status()
        result = resp.json()
        return result["choices"][0]["message"]["content"], None
    except Exception as e: return None, str(e)

def analyze_usage_with_deepseek(records, question):
    if not records: return "还没有使用记录哦～"
    now = datetime.now(timezone.utc) + timedelta(hours=8)
    records_text = "\n".join([f"{r['timestamp']} - {r['app_name']} ({'打开' if r['action']=='open' else '关闭'})" for r in records])
    system_prompt = f"你是一个手机使用记录分析助手。当前时间：{now.strftime('%Y-%m-%d %H:%M')}\n\n以下是用户手机 App 使用记录（按时间排序）：\n\n{records_text}\n\n请回答用户的问题。答案要简洁、友好、基于数据。如果涉及'昨晚'，指前一天18:00到当天06:00。精确计算时间。"
    messages = [{"role": "system", "content": system_prompt}, {"role": "user", "content": question}]
    reply, err = query_deepseek(messages)
    if err:
        app_counts = {}
        for r in records:
            if r['action'] == 'open': app_counts[r['app_name']] = app_counts.get(r['app_name'], 0) + 1
        result = f"📊 共找到 {len(records)} 条记录，涉及 {len(app_counts)} 个App：\n"
        for n, c in sorted(app_counts.items(), key=lambda x: -x[1]):
            result += f"  • {n}：打开 {c} 次\n"
        return result
    return reply

init_db()

def json_resp(data, status=200):
    return (status, {"Content-Type": "application/json"}, json.dumps(data, ensure_ascii=False))

def handler(request, context):
    """Vercel serverless handler"""
    path = urlparse(request["path"]).path
    method = request["method"]
    
    body = {}
    if method == "POST":
        try:
            cl = int(request.get("headers", {}).get("content-length", 0))
            if cl > 0:
                body = json.loads(request["body"])
        except:
            pass
    
    # Health check
    if path == "/api/health":
        return json_resp({"success": True, "status": "running", "total_records": count_records(),
                          "version": "1.0.0", "db_type": "postgresql" if use_pg else "none"})
    
    # Today records
    if path == "/api/records/today":
        today = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
        records = query_records("timestamp >= %s", (today,), "timestamp DESC", 200)
        return json_resp({"success": True, "records": [r.to_dict() for r in records]})
    
    # Today stats
    if path == "/api/records/today/stats":
        today = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
        records = query_records("timestamp >= %s", (today,), "timestamp ASC", 500)
        app_opens = {}
        for r in records:
            if r.action == "open": app_opens[r.app_name] = app_opens.get(r.app_name, 0) + 1
        total = sum(app_opens.values())
        top = sorted(app_opens.items(), key=lambda x: -x[1])[:10]
        now = datetime.now(timezone.utc)
        return json_resp({"success": True, "date": now.strftime("%Y-%m-%d"), "total_records": len(records),
                          "total_opens": total, "top_apps": [{"name": n, "count": c} for n, c in top]})
    
    # Range query
    if path == "/api/records/range":
        params_qs = parse_qs(urlparse(request["path"]).query)
        start = params_qs.get("start", [None])[0]
        end = params_qs.get("end", [None])[0]
        app_name = params_qs.get("app_name", [None])[0]
        limit = int(params_qs.get("limit", [100])[0])
        
        conditions = []
        values = []
        if start:
            from dateutil import parser as date_parser
            try:
                dt = date_parser.parse(start)
                conditions.append("timestamp >= %s"); values.append(dt)
            except: pass
        if end:
            from dateutil import parser as date_parser
            try:
                dt = date_parser.parse(end)
                conditions.append("timestamp <= %s"); values.append(dt)
            except: pass
        if app_name:
            conditions.append("app_name ILIKE %s"); values.append(f"%{app_name}%")
        
        where = " AND ".join(conditions) if conditions else ""
        records = query_records(where, tuple(values) if values else None, "timestamp DESC", limit)
        return json_resp({"success": True, "records": [r.to_dict() for r in records]})
    
    # Record app
    if path == "/api/record" and method == "POST":
        app_name = body.get("app_name", "").strip()
        action = body.get("action", "open").strip()
        if not app_name: return json_resp({"success": False, "error": "app_name required"}, 400)
        if action not in ["open", "close"]: action = "open"
        ts = datetime.now(timezone.utc)
        record = insert_record(app_name, action, ts)
        return json_resp({"success": True, "record": record.to_dict() if record else {"app_name": app_name, "action": action}}, 201)
    
    # Batch records
    if path == "/api/record/batch" and method == "POST":
        records_data = body.get("records", [])
        created = []
        for item in records_data:
            app_name = item.get("app_name", "").strip()
            action = item.get("action", "open")
            if not app_name: continue
            ts = datetime.now(timezone.utc)
            record = insert_record(app_name, action, ts)
            if record: created.append(record.to_dict())
        return json_resp({"success": True, "count": len(created), "records": created}, 201)
    
    # AI ask
    if path == "/api/ask" and method == "POST":
        question = body.get("question", "").strip()
        if not question: return json_resp({"success": False, "error": "question required"}, 400)
        now = datetime.now(timezone.utc)
        start = now - timedelta(days=7)
        records = query_records("timestamp >= %s", (start,), "timestamp ASC", 1000)
        answer = analyze_usage_with_deepseek([r.to_dict() for r in records], question)
        return json_resp({"success": True, "question": question, "answer": answer, "record_count": len(records)})
    
    return json_resp({"success": False, "error": "Not found"}, 404)