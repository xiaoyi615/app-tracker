import os
import requests
from datetime import datetime, timezone, timedelta

BARK_KEY = os.environ.get("BARK_KEY", "Mu6APQR5GZnCtgUxqZtpXD")
DEEPSEEK_API_KEY = os.environ.get("DEEPSEEK_API_KEY", "")
DEEPSEEK_API_URL = "https://api.deepseek.com/v1/chat/completions"

def send_bark_push(title, body, url=None):
    try:
        payload = {"title": title, "body": body, "group": "AppTracker"}
        if url:
            payload["url"] = url
        resp = requests.post("https://api.day.app/Mu6APQR5GZnCtgUxqZtpXD", json=payload, timeout=10)
        return resp.json().get("code") == 200
    except:
        return False

def query_deepseek(messages, max_tokens=1024):
    if not DEEPSEEK_API_KEY:
        return None, "DeepSeek key not set"}

def analyze_usage_with_deepseek(records, question):
    if not records:
        return "No records available"
    text = "\\n".join([f"{r['app_name']} @ {r['timestamp']}" for r in records])
    prompt = f"You are a phone usage analyst. Analyze this: {text}"
    msgs = [{"role": "system", "content": prompt}, {"role": "user", "content": question}]
    reply, err = query_deepseek(msgs)
    if err:
        return f"Found {len(records)} records, but AI unavailable"
    return reply
