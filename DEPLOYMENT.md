# 🚀 A股投研平台 - GitHub仓库 & 部署指南

## 📋 项目概览

**项目名称**: A股投研平台
**技术栈**: OpenBB + Tushare + 智谱AI + Streamlit
**部署方式**: 云服务器 + GitHub Actions

## 📦 功能模块

### 1. 数据层 ✅
- [x] A股实时行情
- [x] 财务数据
- [x] 技术分析指标
- [x] 新闻资讯
- [x] 行业分析
- [x] 龙虎榜数据

### 2. 分析层 ✅
- [x] 自动选股策略
- [x] 风险评估
- [x] 组合分析
- [x] 回测系统
- [x] 量化策略

### 3. AI辅助 ✅
- [x] 智能研报生成
- [x] 数据自动解读
- [x] 投资建议
- [x] 问答系统

## 🔧 部署步骤

### 第一步：创建GitHub仓库

1. 访问 https://github.com/new
2. 仓库名称：`a-share-research-platform`
3. 设置：Public 或 Private
4. 点击 "Create repository"

### 第二步：推送代码

```bash
# 1. 添加远程仓库
cd C:\Users\32643\Desktop\OpenBB\A-share-Analysis
git remote add origin https://github.com/你的用户名/a-share-research-platform.git

# 2. 添加所有文件
git add .

# 3. 提交
git commit -m "初始提交：A股投研平台 v1.0"

# 4. 推送到GitHub
git push -u origin main
```

### 第三步：云服务器部署

#### 3.1 服务器准备

```bash
# 登录云服务器
ssh root@你的服务器IP

# 更新系统
apt update && apt upgrade -y

# 安装Python 3.9+
apt install python3.9 python3.9-venv python3-pip -y

# 安装Nginx
apt install nginx -y

# 安装Git
apt install git -y

# 安装Docker（可选）
curl -fsSL https://get.docker.com | bash
```

#### 3.2 部署应用

```bash
# 创建项目目录
mkdir -p /var/www/a-share-research
cd /var/www/a-share-research

# 克隆仓库
git clone https://github.com/你的用户名/a-share-research-platform.git .

# 创建虚拟环境
python3.9 -m venv venv
source venv/bin/activate

# 安装依赖
pip install -r requirements.txt

# 配置环境变量
cat > .env << EOF
TUSHARE_TOKEN=你的Tushare_Token
ZHIPU_API_KEY=你的智谱AI_API_Key
PLATFORM_NAME=A股投研平台
DEFAULT_STOCK=000001.SZ
ANALYSIS_DAYS=90
EOF

# 配置Streamlit
cat > .streamlit/config.toml << EOF
[server]
headless = true
port = 8501
address = "0.0.0.0"

[browser]
gatherUsageStats = false

[theme]
primaryColor = "#1f77b4"
backgroundColor = "#ffffff"
secondaryBackgroundColor = "#f0f2f6"
textColor = "#262730"
font = "sans serif"
EOF

# 创建Systemd服务
cat > /etc/systemd/system/a-share-platform.service << EOF
[Unit]
Description=A股投研平台
After=network.target

[Service]
Type=simple
User=www-data
WorkingDirectory=/var/www/a-share-research
Environment="PATH=/var/www/a-share-research/venv/bin"
ExecStart=/var/www/a-share-research/venv/bin/streamlit run app.py
Restart=always

[Install]
WantedBy=multi-user.target
EOF

# 启动服务
systemctl daemon-reload
systemctl enable a-share-platform
systemctl start a-share-platform

# 配置Nginx反向代理
cat > /etc/nginx/sites-available/a-share-research << EOF
server {
    listen 80;
    server_name 你的域名或IP;

    location / {
        proxy_pass http://localhost:8501;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
EOF

# 启用Nginx配置
ln -s /etc/nginx/sites-available/a-share-research /etc/nginx/sites-enabled/
nginx -t
systemctl restart nginx

# 配置HTTPS（可选）
# certbot --nginx -d 你的域名
```

#### 3.3 访问平台

浏览器访问：`http://你的服务器IP:8501`

## 🔑 需要的API密钥

### 必需的API密钥

1. **Tushare Token**
   - 用途：A股数据
   - 获取地址：https://tushare.pro/
   - 免费版限制：每天2000次调用

2. **智谱AI API Key**
   - 用途：AI分析
   - 获取地址：https://open.bigmodel.cn/
   - 免费版：GLM-4-Flash

### 可选的API密钥

3. **OpenBB Pro**（高级功能）
   - 用途：更多数据源
   - 获取地址：https://platform.openbb.co/

4. **飞书Webhook**（用于通知）
   - 用途：消息推送
   - 获取地址：飞书机器人配置

## 📊 功能清单

### 已实现功能 ✅

#### 数据层
- [x] A股实时行情（日线、分钟线）
- [x] 财务数据（资产负债表、利润表、现金流量表）
- [x] 技术分析指标（MA, MACD, RSI, 声林带）
- [x] 新闻资讯（公司新闻、行业新闻）
- [x] 行业分析（申万一级行业）
- [x] 龙虎榜数据

#### 分析层
- [x] 自动选股策略（多因子选股）
- [x] 风险评估（波动率、最大回撤）
- [x] 组合分析（资产配置）
- [x] 回测系统（策略回测）
- [x] 量化策略（趋势跟踪、均值回归）

#### AI辅助
- [x] 智能研报生成
- [x] 数据自动解读
- [x] 投资建议
- [x] 问答系统

### 待开发功能 🚧

#### 高级功能
- [ ] 实时行情推送
- [ ] 移动端适配
- [ ] 用户系统
- [ ] 数据导出（Excel、PDF）
- [ ] 策略回测可视化
- [ ] 交易信号提醒

## 📁 项目结构

```
a-share-research-platform/
├── app.py                    # 主应用
├── data_layer/               # 数据层
│   ├── a_stock_data.py
│   ├── financial_data.py
│   ├── news_data.py
│   └── technical_analysis.py
├── analysis_layer/           # 分析层
│   ├── stock_selection.py
│   ├── risk_assessment.py
│   ├── portfolio_analysis.py
│   └── backtest.py
├── ai_layer/                 # AI层
│   ├── report_generator.py
│   ├── data_interpreter.py
│   └── investment_advisor.py
├── frontend/                 # 前端（可选）
│   ├── index.html
│   └── static/
├── requirements.txt
├── .env.example
├── .streamlit/config.toml
├── Dockerfile
├── docker-compose.yml
└── README.md
```

## 🐳 Docker部署（推荐）

### 使用Docker部署

```bash
# 构建镜像
docker build -t a-share-platform:latest .

# 启动容器
docker run -d \
  --name a-share-platform \
  -p 8501:8501 \
  -v $(pwd)/.env:/app/.env \
  a-share-platform:latest

# 查看日志
docker logs -f a-share-platform

# 停止容器
docker stop a-share-platform
docker rm a-share-platform
```

### Docker Compose部署

```bash
# 启动所有服务
docker-compose up -d

# 查看状态
docker-compose ps

# 停止服务
docker-compose down
```

## 📊 性能优化

### 1. 数据缓存
- 使用 Redis 缓存历史数据
- 减少API调用次数

### 2. 并发处理
- 使用多线程/多进程
- 提高数据处理速度

### 3. 数据压缩
- 压缩历史数据
- 减少存储空间

### 4. 负载均衡
- Nginx反向代理
- 多实例部署

## 🔒 安全建议

1. **API密钥保护**
   - 使用环境变量
   - 不要提交到Git
   - 定期更换密钥

2. **网络安全**
   - 使用HTTPS
   - 配置防火墙
   - 限制访问IP

3. **数据安全**
   - 定期备份
   - 加密敏感数据
   - 记录访问日志

## 📈 监控和维护

### 日志查看
```bash
# Streamlit日志
tail -f /var/log/streamlit.log

# Nginx日志
tail -f /var/log/nginx/access.log
tail -f /var/log/nginx/error.log

# Systemd日志
journalctl -u a-share-platform -f
```

### 健康检查
```bash
# 检查服务状态
systemctl status a-share-platform

# 重启服务
systemctl restart a-share-platform

# 查看资源使用
docker stats a-share-platform
```

## 📞 技术支持

- **GitHub Issues**: https://github.com/你的用户名/a-share-research-platform/issues
- **Tushare文档**: https://tushare.pro/document/2
- **智谱AI文档**: https://open.bigmodel.cn/
- **OpenBB文档**: https://docs.openbb.co/

## 📝 更新日志

### v1.0.0 (2026-02-20)
- ✅ 初始版本发布
- ✅ 数据层完整实现
- ✅ 分析层完整实现
- ✅ AI层完整实现
- ✅ Docker部署支持

---

**部署状态**: 🚧 待部署
**预计时间**: 30-60分钟
**服务器要求**: 2核4G内存，50GB存储
