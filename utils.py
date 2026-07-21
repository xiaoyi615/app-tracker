import requests
import json
import logging
from datetime import datetime, timezone, timedelta
from config import BARK_URL, DEEPSEEK_API_KEY, DEEPSEEK_API_URL

logger = logging.getLogger(__name__)

def send_bark_push(title, body, url=None):
    """通过 Bark 发送推送通知"""
    try:
        payload = {
            'title': title,
            'body': body,
            'group': 'AppTracker'
        }
        if url:
            payload['url'] = url
        
        resp = requests.post(f'{BARK_URL}', json=payload, timeout=10)
        result = resp.json()
        if result.get('code') == 200:
            logger.info(f'Bark push sent: {title}')
            return True
        else:
            logger.warning(f'Bark push failed: {result}')
            return False
    except Exception as e:
        logger.error(f'Bark push error: {e}')
        return False


def query_deepseek(messages, max_tokens=1024):
    """调用 DeepSeek API"""
    if not DEEPSEEK_API_KEY:
        return None, 'DeepSeek API Key 未配置'
    
    try:
        headers = {
            'Authorization': f'Bearer {DEEPSEEK_API_KEY}',
            'Content-Type': 'application/json'
        }
        payload = {
            'model': 'deepseek-chat',
            'messages': messages,
            'max_tokens': max_tokens,
            'temperature': 0.3,
            'stream': False
        }
        resp = requests.post(DEEPSEEK_API_URL, headers=headers, json=payload, timeout=30)
        resp.raise_for_status()
        result = resp.json()
        return result['choices'][0]['message']['content'], None
    except Exception as e:
        logger.error(f'DeepSeek API error: {e}')
        return None, str(e)


def analyze_usage_with_deepseek(records, question):
    """使用 DeepSeek 分析使用记录"""
    if not records:
        return '目前还没有使用记录哦～'
    
    # 格式化记录为文本
    records_text = '\n'.join([
        f"{r['timestamp']} - {r['app_name']} ({'打开' if r['action']=='open' else '关闭'})"
        for r in records
    ])
    
    # 获取当前时间
    now = datetime.now(timezone.utc) + timedelta(hours=8)  # UTC+8
    
    system_prompt = f'''你是一个手机使用记录分析助手。当前时间：{now.strftime('%Y-%m-%d %H:%M')}

以下是用户手机 App 的使用记录（按时间排序）：

{records_text}

请回答用户的问题。答案要简洁、友好、基于数据。如果问题涉及"昨晚"，指前一天 18:00 到当天 06:00。
如果问题涉及时间计算，请精确计算分钟数。'''
    
    messages = [
        {'role': 'system', 'content': system_prompt},
        {'role': 'user', 'content': question}
    ]
    
    reply, error = query_deepseek(messages)
    if error:
        # 如果 DeepSeek 不可用，本地简单分析
        return _local_analyze(records, question)
    return reply


def _local_analyze(records, question):
    """本地简单分析（DeepSeek 不可用时备用）"""
    # 计算总使用时长
    from dateutil import parser as date_parser
    
    # 简化版：统计各 App 使用次数
    app_counts = {}
    for r in records:
        name = r['app_name']
        if r['action'] == 'open':
            app_counts[name] = app_counts.get(name, 0) + 1
    
    result = f'📊 共找到 {len(records)} 条记录，涉及 {len(app_counts)} 个 App：\n'
    for name, count in sorted(app_counts.items(), key=lambda x: -x[1]):
        result += f'  • {name}：打开 {count} 次\n'
    
    return result
