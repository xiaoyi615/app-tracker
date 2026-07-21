# 📱 App Tracker - 完整部署及使用指南

## 一、项目文件结构

```
app-tracker/
├── app.py              # Flask 主应用（所有API接口）
├── config.py           # 配置文件（Bark Key、DeepSeek Key等）
├── models.py           # 数据库模型
├── utils.py            # 工具函数（Bark推送、DeepSeek调用）
├── requirements.txt    # Python 依赖
├── render.yaml         # Render 部署配置
├── templates/
│   └── index.html      # Web 查看面板
└── static/             # 静态文件目录
```

## 二、部署到 Render（免费）

### 方法 1：使用 GitHub（推荐）

1. 将代码推送到你的 GitHub 仓库：
```bash
cd /home/app-tracker
git init
git add .
git commit -m "initial commit"
git remote add origin https://github.com/你的用户名/app-tracker.git
git push -u origin main
```

2. 打开 https://render.com ，用 GitHub 登录

3. 点击 **New +** → **Blueprint**（蓝图部署）
   - 连接你的 GitHub 仓库
   - Render 会自动识别 `render.yaml`，创建 Web Service + PostgreSQL 数据库
   - 部署完成后，你会得到一个公网地址：`https://app-tracker.onrender.com`

### 方法 2：手动部署到 Render

1. 点击 **New +** → **Web Service**
2. 选择 **Build and deploy from a Git repository**（或手动上传）
3. 设置：
   - Name: `app-tracker`
   - Runtime: `Python 3`
   - Build Command: `pip install -r requirements.txt`
   - Start Command: `gunicorn app:app --bind 0.0.0.0:$PORT --workers 2 --timeout 120`
4. 添加环境变量：
   - `DEEPSEEK_API_KEY` = 你的 DeepSeek API Key（问AI用的，可选）
   - `BARK_KEY` = 你的 Bark Key（已内置，可选改）
   - `SECRET_KEY` = 随机字符串
5. 创建免费的 PostgreSQL 数据库（在 Dashboard → New + → PostgreSQL）
6. 把数据库连接字符串设为环境变量 `DATABASE_URL`
7. 部署！

## 三、配置 iPhone 快捷指令

打开 iPhone **快捷指令 App**，创建自动化：

### 自动化 1：打开 App 时记录
1. 点底部 **自动化** → 创建个人自动化
2. 选择 **App** → **已打开** → 选择小红书、抖音等 App
3. 添加操作：**获取当前时间** → **获取日期**（格式设为 ISO 8601）
4. 添加操作：**URL** → 输入 `https://你的公网地址/api/record`
5. 添加操作：**获取URL内容**
   - 方法：POST
   - 请求体：JSON
   - 内容：`{"app_name":"小红书","action":"open","timestamp":"[[当前时间]]"}`
6. 关闭 **运行前询问**

### 自动化 2：关闭 App 时记录（同上，改 action 为 close）

> 💡 **简化方案**：只记录「打开」即可，省去关闭的自动化。

## 四、API 接口文档

### 1. 记录 App 使用事件

```
POST https://你的域名/api/record
Content-Type: application/json

{
    "app_name": "小红书",    // App 名称
    "action": "open",       // "open" 或 "close"
    "timestamp": "2026-07-21T10:30:00Z"  // 可选，不传则用服务器时间
}
```

**返回：**
```json
{
    "success": true,
    "record": {
        "id": 1,
        "app_name": "小红书",
        "action": "open",
        "timestamp": "2026-07-21T10:30:00"
    }
}
```

### 2. 批量记录

```
POST https://你的域名/api/record/batch
Content-Type: application/json

{
    "records": [
        {"app_name": "小红书", "action": "open", "timestamp": "..."},
        {"app_name": "抖音", "action": "open", "timestamp": "..."}
    ]
}
```

### 3. 获取今日统计

```
GET https://你的域名/api/records/today/stats
```

### 4. 获取今日记录

```
GET https://你的域名/api/records/today
```

### 5. 自定义时间范围查询

```
GET https://你的域名/api/records/range?start=2026-07-20&end=2026-07-21&app_name=抖音&limit=50
```

### 6. AI 智能问答

```
POST https://你的域名/api/ask
Content-Type: application/json

{
    "question": "我昨晚几点睡的？"
}
```

**或自定义时间范围：**
```json
{
    "question": "今天玩了多久抖音？",
    "days": 1
}
```

**返回示例：**
```json
{
    "success": true,
    "question": "我今天玩了多久抖音？",
    "answer": "根据记录，你今天一共打开了抖音2次。第一次在07:25，第二次在07:26，每次使用时长较短，累计约2分钟。",
    "record_count": 5
}
```

### 7. 健康检查

```
GET https://你的域名/api/health
```

### 8. 测试 Bark 推送

```
POST https://你的域名/api/push/test
Content-Type: application/json

{
    "title": "测试标题",
    "body": "测试内容"
}
```

## 五、访问 Web 面板

打开浏览器访问 `https://你的域名/` 即可看到漂亮的数据看板！

## 六、配置 DeepSeek API Key（让AI更聪明）

在 Render 的环境变量中设置：
```
DEEPSEEK_API_KEY = sk-你的DeepSeekKey
```
获取地址：https://platform.deepseek.com/

没有配置 Key 也能用，会使用本地分析功能（简单统计）。

## 七、注意事项

- Render 免费版如果15分钟无人访问会休眠，再次访问时会自动唤醒（等几秒）
- 建议部署后先调 `/api/health` 确认服务正常
- 快捷指令建议只记录「打开 App」，避免过于频繁
- 数据默认保留7天用于AI分析
