#!/bin/bash
set -e

echo "========================================="
echo "修复WebSocket连接问题"
echo "========================================="
echo ""

# 检查是否已安装Nginx
if ! command -v nginx &> /dev/null; then
    echo "❌ Nginx未安装，正在安装..."
    sudo apt update
    sudo apt install nginx -y
fi

echo "✓ Nginx已安装"
echo ""

# 配置WebSocket代理
echo "步骤1: 配置Nginx WebSocket代理..."

sudo tee /etc/nginx/sites-available/tradingagents-frontend > /dev/null << 'EOF'
server {
    listen 80;
    server_name _;

    # 前端静态文件
    location / {
        proxy_pass http://localhost:3000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection 'upgrade';
        proxy_set_header Host $host;
        proxy_cache_bypass $http_upgrade;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    # WebSocket 代理 - 通知
    location /api/ws/notifications {
        proxy_pass http://localhost:8000/api/ws/notifications;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        # WebSocket 超时设置
        proxy_connect_timeout 7d;
        proxy_send_timeout 7d;
        proxy_read_timeout 7d;
    }

    # WebSocket 代理 - 任务进度
    location /api/ws/tasks {
        proxy_pass http://localhost:8000/api/ws/tasks;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        # WebSocket 超时设置
        proxy_connect_timeout 7d;
        proxy_send_timeout 7d;
        proxy_read_timeout 7d;
    }

    # 后端API（其他请求）
    location /api/ {
        proxy_pass http://localhost:8000/api/;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection 'upgrade';
        proxy_set_header Host $host;
        proxy_cache_bypass $http_upgrade;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        # 超时设置（AI分析可能需要较长时间）
        proxy_connect_timeout 300;
        proxy_send_timeout 300;
        proxy_read_timeout 300;
    }

    # 健康检查端点
    location /health {
        proxy_pass http://localhost:3000/health;
        access_log off;
    }

    # 后端健康检查
    location /api/health {
        proxy_pass http://localhost:8000/health;
        access_log off;
    }
}
EOF

echo "✓ Nginx配置文件已更新"
echo ""

# 删除旧配置链接（如果存在）
sudo rm -f /etc/nginx/sites-enabled/default
sudo rm -f /etc/nginx/sites-enabled/tradingagents-frontend

# 创建新链接
sudo ln -s /etc/nginx/sites-available/tradingagents-frontend /etc/nginx/sites-enabled/

echo "步骤2: 测试Nginx配置..."
if sudo nginx -t; then
    echo "✓ Nginx配置测试通过"
else
    echo "✗ Nginx配置测试失败"
    exit 1
fi
echo ""

echo "步骤3: 重启Nginx..."
sudo systemctl restart nginx
echo "✓ Nginx已重启"
echo ""

echo "步骤4: 修改docker-compose端口映射..."
echo "将前端和后端端口改为仅监听本地"

# 检查docker-compose.simple.yml是否存在
if [ -f /root/TradingAgents-CN/docker-compose.simple.yml ]; then
    cd /root/TradingAgents-CN

    # 备份原配置
    cp docker-compose.simple.yml docker-compose.simple.yml.backup

    # 修改端口映射
    sed -i 's/"3000:80"/"127.0.0.1:3000:80"/g' docker-compose.simple.yml
    sed -i 's/"8000:8000"/"127.0.0.1:8000:8000"/g' docker-compose.simple.yml

    echo "✓ 端口映射已修改"
    echo "  前端: 127.0.0.1:3000:80"
    echo "  后端: 127.0.0.1:8000:8000"
    echo ""

    echo "步骤5: 重启Docker容器..."
    docker-compose -f docker-compose.simple.yml down
    docker-compose -f docker-compose.simple.yml up -d

    echo "✓ 容器已重启"
else
    echo "⚠️  docker-compose.simple.yml 不存在，跳过容器重启"
fi

echo ""
echo "========================================="
echo "✓ WebSocket配置完成！"
echo "========================================="
echo ""
echo "配置说明："
echo "1. Nginx监听80端口，处理所有外部请求"
echo "2. WebSocket连接通过Nginx代理到后端"
echo "3. 前端和后端仅监听本地127.0.0.1"
echo ""
echo "访问地址："
echo "  前端: http://39.97.33.153"
echo "  后端: http://39.97.33.153/api/..."
echo ""
echo "测试WebSocket："
echo "1. 打开浏览器访问: http://39.97.33.153"
echo "2. 登录系统"
echo "3. 查看浏览器控制台，WebSocket应该连接成功"
echo ""
