#!/bin/bash

# A股投研平台 - 服务器部署脚本
# 自动化部署到阿里云服务器

echo "========================================"
echo "A股投研平台 - 自动部署脚本"
echo "========================================"
echo ""

# 配置变量
SERVER_IP="39.97.33.153"
SERVER_USER="root"
SERVER_PASS="@20080415Ab"
PROJECT_DIR="/var/www/a-share-research"
GIT_REPO="https://github.com/你的用户名/a-share-research-platform.git"

# 使用expect自动输入密码
expect << 'EOF'
set timeout 300
spawn ssh -o StrictHostKeyChecking=no root@39.97.33.153 "uptime && netstat -tuln | grep -E ':(3000|8501|80|443)'"
expect {
    "password:" {
        send "@20080415Ab\r"
        exp_continue
    }
    eof
}
EOF

echo ""
echo "部署脚本已准备，请手动执行以下步骤："
echo ""
echo "1. 创建GitHub仓库：https://github.com/new"
echo "2. 推送代码："
echo "   git remote add origin https://github.com/你的用户名/a-share-research-platform.git"
echo "   git push -u origin main"
echo "3. SSH连接到服务器："
echo "   ssh root@39.97.33.153"
echo "4. 运行部署脚本："
echo "   bash deploy_to_server.sh"
echo ""
echo "或者使用一键部署脚本："
echo "   bash deploy_to_server.sh"
