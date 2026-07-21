import os

# 数据库 - 使用 SQLite 本地存储，部署到 Render 可切换 PostgreSQL
# 本地开发用 SQLite，部署到 Render 后会自动用 PostgreSQL
DATABASE_URL = os.environ.get('DATABASE_URL', 'sqlite:///app_usage.db')

# 如果 Render 的 PostgreSQL URL 以 postgres:// 开头，需要转为 postgresql://
if DATABASE_URL and DATABASE_URL.startswith('postgres://'):
    DATABASE_URL = DATABASE_URL.replace('postgres://', 'postgresql://', 1)

# Bark 推送配置（用于推送提醒，可选）
BARK_KEY = os.environ.get('BARK_KEY', 'J9od2SYPxJHG6dCVtdBkAb')
BARK_URL = f'https://api.day.app/{BARK_KEY}'

# DeepSeek API 配置（用于 AI 问答）
DEEPSEEK_API_KEY = os.environ.get('DEEPSEEK_API_KEY', '')
DEEPSEEK_API_URL = 'https://api.deepseek.com/v1/chat/completions'

# 应用密钥
SECRET_KEY = os.environ.get('SECRET_KEY', 'app-tracker-secret-key-change-in-production')
