# Note: This file needs psycopg2-binary and you must set POSTGRES_URL env var in Vercel

from http.server import BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
from datetime import datetime, timezone, timedelta
import json

from api.db import init_db, query_records, insert_record, count_records, AppRecord, use_pg
from api.utils import send_bark_push, analyze_usage_with_deepseek

init_db()

def app(handler, request):
    path = urlparse(request["path"]).path
    method = request["method"]
    params = parse_qs(urlparse(request["path"]).query)
    
    try:
        body = {}
        if method == "POST":
            cl = int(request.get("headers", {}).get("content-length", 0))
            if cl > 0:
                body = json.loads(request["body"])
    except:
        pass
    
    # Health check
    if path == "/api/health":
        return json_resp({"success": True, "status": "running", "total_records": count_records(), "version": "1.0.0", "db_type": "postgresql" if use_pg else "none"})
    
    # Get today records
    if path == "/api/records/today":
        today = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
        records = query_records("timestamp >= %s", (today, ), "timestamp DESC", 200)
        return json_resp({"success": True, "records": [r.to_dict() for r in records]})
    
    # Get today stats
    if path == "/api/records/today/stats":
        today = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
        records = query_records("timestamp >= %s", (today, ), "timestamp ASC", 500)
        app_opens = {}
        for r in records:
            if r.action == "open":
                app_opens[r.app_name] = app_opens.get(r.app_name, 0) + 1
        total = sum(app_opens.values())
        top = sorted(app_opens.items(), key=lambda x: -x[1])[:10]
        now = datetime.now(timezone.utc)
        return json_resp({"success": True, "date": now.strftime("%Y-%m-%d"), "total_records": len(records), "total_opens": total, "top_apps": [{"name": n, "count": c} for n, c in top]})
    
    # Record app open/close
    if path == "/api/record" and method == "POST":
        app_name = body.get("app_name", "").strip()
        action = body.get("action", "open").strip()
        if not app_name:
            return json_resp({"success": False, "error": "app_name required"}, 400)
        if action not in ["open", "close"]:
            action = "open"
        ts = datetime.now(timezone.utc)
        record = insert_record(app_name, action, ts)
        if record and action == "open":
            send_bark_push("App Opened", app_name)
        return json_resp({"success": True, "record": record.to_dict() if record else {"app_name": app_name}}, 201)
    
    # AI ask
    if path == "/api/ask" and method == "POST":
        question = body.get("question", "").strip()
        if not question:
            return json_resp({"success": False, "error": "question required"}, 400)
        now = datetime.now(timezone.utc)
        start = now - timedelta(days=7)
        records = query_records("timestamp >= %s", (start, ), "timestamp ASC", 1000)
        answer = analyze_usage_with_deepseek([r.to_dict() for r in records], question)
        return json_resp({"success": True, "question": question, "answer": answer, "record_count": len(records)})
    
    # Push test
    if path == "/api/push/test" and method == "POST":
        title = body.get("title", "Test")
        body_text = body.get("body", "Hello!")
        res = send_bark_push(title, body_text)
        return json_resp({"success": res})
    
    return json_resp({"success": False, "error": "Not found"}, 404)


def json_resp(data, status=200):
    return (status, {"Content-Type": "application/json"}, json.dumps(data, ensure_ascii=False))

# Vercel requires this to be called 'handler'
def handler(request, context):
    return app(handler, request)