import os
import logging
from datetime import datetime, timezone, timedelta
from flask import Flask, request, jsonify, render_template
from flask_cors import CORS
from dateutil import parser as date_parser

from config import SECRET_KEY
from models import db, AppRecord
from utils import send_bark_push, analyze_usage_with_deepseek

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.config['SECRET_KEY'] = SECRET_KEY
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL', 'sqlite:///app_usage.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db_url = app.config['SQLALCHEMY_DATABASE_URI']
if db_url and db_url.startswith('postgres://'):
    app.config['SQLALCHEMY_DATABASE_URI'] = db_url.replace('postgres://', 'postgresql://', 1)

CORS(app)
db.init_app(app)

with app.app_context():
    db.create_all()


# ============ 网页页面 ============

@app.route('/')
def index():
    """主页 - Web 查看面板"""
    return render_template('index.html')

@app.route('/api/records/today')
def today_records():
    """获取今天的记录（JSON）"""
    now = datetime.now(timezone.utc)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    records = AppRecord.query.filter(AppRecord.timestamp >= today_start).order_by(AppRecord.timestamp.desc()).all()
    return jsonify({'success': True, 'records': [r.to_dict() for r in records]})

@app.route('/api/records/today/stats')
def today_stats():
    """获取今天的统计摘要"""
    now = datetime.now(timezone.utc)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    records = AppRecord.query.filter(AppRecord.timestamp >= today_start).order_by(AppRecord.timestamp.asc()).all()
    
    app_opens = {}
    for r in records:
        if r.action == 'open':
            app_opens[r.app_name] = app_opens.get(r.app_name, 0) + 1
    
    total_opens = sum(app_opens.values())
    top_apps = sorted(app_opens.items(), key=lambda x: -x[1])[:10]
    
    # 简单计算使用时长（基于开/关配对）
    app_sessions = {}
    for r in records:
        if r.app_name not in app_sessions:
            app_sessions[r.app_name] = []
        app_sessions[r.app_name].append(r)
    
    return jsonify({
        'success': True,
        'date': now.strftime('%Y-%m-%d'),
        'total_records': len(records),
        'total_opens': total_opens,
        'top_apps': [{'name': n, 'count': c} for n, c in top_apps]
    })

@app.route('/api/records/range')
def records_range():
    """按时间范围查询记录"""
    start = request.args.get('start')
    end = request.args.get('end')
    app_name = request.args.get('app_name')
    limit = request.args.get('limit', 100, type=int)
    
    query = AppRecord.query
    
    if start:
        try:
            dt_start = date_parser.parse(start)
            query = query.filter(AppRecord.timestamp >= dt_start)
        except:
            pass
    
    if end:
        try:
            dt_end = date_parser.parse(end)
            query = query.filter(AppRecord.timestamp <= dt_end)
        except:
            pass
    
    if app_name:
        query = query.filter(AppRecord.app_name.ilike(f'%{app_name}%'))
    
    records = query.order_by(AppRecord.timestamp.desc()).limit(limit).all()
    return jsonify({'success': True, 'records': [r.to_dict() for r in records]})



# ============ 记录接口（供快捷指令调用） ============

@app.route('/api/record', methods=['POST'])
def create_record():
    """记录 App 打开/关闭事件"""
    data = request.get_json(silent=True)
    if not data:
        return jsonify({'success': False, 'error': '请传入 JSON 数据'}), 400
    
    app_name = data.get('app_name', '').strip()
    action = data.get('action', 'open').strip()
    timestamp_str = data.get('timestamp')
    
    if not app_name:
        return jsonify({'success': False, 'error': 'app_name 不能为空'}), 400
    
    if action not in ['open', 'close']:
        action = 'open'
    
    if timestamp_str:
        try:
            ts = date_parser.parse(timestamp_str)
        except:
            ts = datetime.now(timezone.utc)
    else:
        ts = datetime.now(timezone.utc)
    
    record = AppRecord(app_name=app_name, action=action, timestamp=ts)
    db.session.add(record)
    db.session.commit()
    
    logger.info(f'Recorded: {app_name} {action}')
    
    # 推送 Bark 通知（只有打开时才推，避免太频繁）
    if action == 'open':
        send_bark_push(
            title='📱 打开 App',
            body=f'{app_name}',
            url='https://app-tracker.onrender.com/'
        )
    
    return jsonify({'success': True, 'record': record.to_dict()}), 201


@app.route('/api/record/batch', methods=['POST'])
def batch_records():
    """批量记录（快捷指令可批量上报）"""
    data = request.get_json(silent=True)
    if not data or 'records' not in data:
        return jsonify({'success': False, 'error': '请传入 {"records": [...]}'}), 400
    
    records_data = data['records']
    created = []
    for item in records_data:
        app_name = item.get('app_name', '').strip()
        action = item.get('action', 'open')
        timestamp_str = item.get('timestamp')
        
        if not app_name:
            continue
        
        if timestamp_str:
            try:
                ts = date_parser.parse(timestamp_str)
            except:
                ts = datetime.now(timezone.utc)
        else:
            ts = datetime.now(timezone.utc)
        
        record = AppRecord(app_name=app_name, action=action, timestamp=ts)
        db.session.add(record)
        created.append(record.to_dict())
    
    db.session.commit()
    logger.info(f'Batch recorded {len(created)} records')
    return jsonify({'success': True, 'count': len(created), 'records': created}), 201


# ============ AI 问答接口 ============

@app.route('/api/ask', methods=['POST'])
def ask_ai():
    """向 AI 提问使用情况"""
    data = request.get_json(silent=True)
    if not data:
        return jsonify({'success': False, 'error': '请传入 JSON'}), 400
    
    question = data.get('question', '').strip()
    if not question:
        return jsonify({'success': False, 'error': '请输入问题'}), 400
    
    # 获取相关记录（默认最近 7 天）
    now = datetime.now(timezone.utc)
    week_ago = now - timedelta(days=7)
    records = AppRecord.query.filter(AppRecord.timestamp >= week_ago).order_by(AppRecord.timestamp.asc()).all()
    
    # 用 DeepSeek 分析
    answer = analyze_usage_with_deepseek([r.to_dict() for r in records], question)
    
    return jsonify({
        'success': True,
        'question': question,
        'answer': answer,
        'record_count': len(records)
    })


@app.route('/api/ask/v2', methods=['POST'])
def ask_ai_v2():
    """AI 问答 v2 - 支持自定义时间范围"""
    data = request.get_json(silent=True)
    if not data:
        return jsonify({'success': False, 'error': '请传入 JSON'}), 400
    
    question = data.get('question', '').strip()
    days = data.get('days', 7)
    
    if not question:
        return jsonify({'success': False, 'error': '请输入问题'}), 400
    
    now = datetime.now(timezone.utc)
    start_time = now - timedelta(days=days)
    records = AppRecord.query.filter(AppRecord.timestamp >= start_time).order_by(AppRecord.timestamp.asc()).all()
    
    answer = analyze_usage_with_deepseek([r.to_dict() for r in records], question)
    
    return jsonify({
        'success': True,
        'question': question,
        'answer': answer,
        'days': days,
        'record_count': len(records)
    })


# ============ Bark 推送测试 ============

@app.route('/api/push/test', methods=['POST'])
def test_push():
    """测试 Bark 推送"""
    data = request.get_json(silent=True) or {}
    title = data.get('title', '测试推送')
    body = data.get('body', 'App Tracker 推送测试成功！🎉')
    
    result = send_bark_push(title, body)
    return jsonify({'success': result, 'message': '推送成功' if result else '推送失败'})


# ============ 健康检查 ============

@app.route('/api/health')
def health_check():
    """健康检查"""
    record_count = AppRecord.query.count()
    return jsonify({
        'success': True,
        'status': 'running',
        'total_records': record_count,
        'version': '1.0.0'
    })


# ============ 启动 ============

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=True)
