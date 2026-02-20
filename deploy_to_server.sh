#!/bin/bash

# A股投研平台 - 服务器部署脚本

echo "========================================"
echo "A股投研平台 - 服务器部署"
echo "========================================"
echo ""

# 检查是否为root用户
if [ "$EUID" -ne 0 ]; then
    echo "请使用root用户运行此脚本"
    exit 1
fi

# 配置变量
DOMAIN="你的域名或IP"
PROJECT_DIR="/var/www/a-share-research"
GIT_REPO="https://github.com/你的用户名/a-share-research-platform.git"

echo "1. 安装系统依赖..."
apt update && apt install -y python3.9 python3.9-venv python3-pip nginx git curl

echo ""
echo "2. 创建项目目录..."
mkdir -p $PROJECT_DIR
cd $PROJECT_DIR

echo ""
echo "3. 克隆代码..."
git clone $GIT_REPO .

echo ""
echo "4. 创建虚拟环境..."
python3.9 -m venv venv
source venv/bin/activate

echo ""
echo "5. 安装Python依赖..."
pip install --upgrade pip
pip install -r requirements.txt

echo ""
echo "6. 配置环境变量..."
cat > .env << EOF
TUSHARE_TOKEN=你的Tushare_Token
ZHIPU_API_KEY=你的智谱AI_API_Key
PLATFORM_NAME=A股投研平台
DEFAULT_STOCK=000001.SZ
ANALYSIS_DAYS=90
EOF

echo ""
echo "7. 配置Streamlit..."
mkdir -p .streamlit
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

echo ""
echo "8. 配置Systemd服务..."
cat > /etc/systemd/system/a-share-platform.service << EOF
[Unit]
Description=A股投研平台
After=network.target

[Service]
Type=simple
User=www-data
WorkingDirectory=$PROJECT_DIR
Environment="PATH=$PROJECT_DIR/venv/bin"
ExecStart=$PROJECT_DIR/venv/bin/streamlit run app.py
Restart=always

[Install]
WantedBy=multi-user.target
EOF

echo ""
echo "9. 配置Nginx..."
cat > /etc/nginx/sites-available/a-share-research << EOF
server {
    listen 80;
    server_name $DOMAIN;

    location / {
        proxy_pass http://localhost:8501;
        proxy_http_version 1.1;
        proxy_set_header Upgrade \$http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_read_timeout 86400;
    }
}
EOF

ln -s /etc/nginx/sites-available/a-share-research /etc/nginx/sites-enabled/
nginx -t

echo ""
echo "10. 启动服务..."
systemctl daemon-reload
systemctl enable a-share-platform
systemctl start a-share-platform
systemctl enable nginx
systemctl start nginx

echo ""
echo "========================================"
echo "✅ 部署完成！"
echo "========================================"
echo ""
echo "访问地址: http://$DOMAIN"
echo "服务状态: systemctl status a-share-platform"
echo "查看日志: journalctl -u a-share-platform -f"
echo ""
