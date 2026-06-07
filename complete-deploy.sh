#!/bin/bash

echo "========================================="
echo "  TradingAgents-CN 完整部署脚本"
echo "  从零开始 → 构建部署 → 验证"
echo "========================================="
echo ""

# 步骤1: 清理所有旧环境
echo "[1/9] 清理旧环境..."
echo "-----------------------------------------"
docker-compose down 2>/dev/null
docker stop $(docker ps -aq) 2>/dev/null
docker rm $(docker ps -aq) 2>/dev/null
docker volume prune -f
docker system prune -f
echo "✓ 清理完成"
echo ""

# 步骤2: 创建docker-compose.yml
echo "[2/9] 创建配置文件..."
echo "-----------------------------------------"
cat > docker-compose.yml << 'EOF'
version: '3.8'
services:
  mongodb:
    image: mongo:4.4
    container_name: tradingagents-mongodb
    restart: unless-stopped
    ports:
      - "127.0.0.1:27017:27017"
    environment:
      MONGO_INITDB_ROOT_USERNAME: admin
      MONGO_INITDB_ROOT_PASSWORD: tradingagents123
      MONGO_INITDB_DATABASE: tradingagent
    volumes:
      - mongodb_data:/data/db
    networks:
      - tradingagents-network
    healthcheck:
      test: ["CMD", "mongo", "--eval", "db.adminCommand('ping')"]
      interval: 10s
      timeout: 5s
      retries: 5

  redis:
    image: redis:7-alpine
    container_name: tradingagents-redis
    restart: unless-stopped
    command: redis-server --appendonly yes --requirepass tradingagents123
    ports:
      - "127.0.0.1:6379:6379"
    volumes:
      - redis_data:/data
    networks:
      - tradingagents-network
    healthcheck:
      test: ["CMD", "redis-cli", "--raw", "incr", "ping"]
      interval: 10s
      timeout: 3s
      retries: 5

  backend:
    build:
      context: .
      dockerfile: Dockerfile.backend
    image: tradingagents-backend:v1.0.0-preview
    container_name: tradingagents-backend
    restart: unless-stopped
    depends_on:
      mongodb:
        condition: service_healthy
      redis:
        condition: service_healthy
    env_file:
      - .env
    environment:
      - MONGO_INITDB_ROOT_USERNAME=admin
      - MONGO_INITDB_ROOT_PASSWORD=tradingagents123
      - MONGO_INITDB_DATABASE=tradingagent
      - MONGODB_HOST=mongodb
      - REDIS_HOST=redis
      - PYTHONUNBUFFERED=1
      - TZ=Asia/Shanghai
    ports:
      - "8000:8000"
    networks:
      - tradingagents-network

  frontend:
    build:
      context: .
      dockerfile: Dockerfile.frontend
      args:
        VITE_API_BASE_URL: http://39.97.33.153:8000
    image: tradingagents-frontend:v1.0.0-preview
    container_name: tradingagents-frontend
    restart: unless-stopped
    depends_on:
      - backend
    ports:
      - "3000:80"
    networks:
      - tradingagents-network

volumes:
  mongodb_data:
  redis_data:

networks:
  tradingagents-network:
    driver: bridge
EOF

# 更新Dockerfile.frontend
cat > Dockerfile.frontend << 'EOF'
FROM node:22-alpine AS build
ARG VITE_API_BASE_URL=http://localhost:8000
ENV VITE_API_BASE_URL=${VITE_API_BASE_URL}
ENV NODE_ENV=production
WORKDIR /app/frontend
RUN corepack enable && corepack prepare yarn@1.22.22 --activate
COPY frontend/package.json frontend/yarn.lock frontend/.yarnrc ./
RUN yarn install --frozen-lockfile --production=false
COPY frontend/. ./
COPY assets /app/frontend/public/assets
COPY docs /app/docs
RUN yarn vite build
FROM nginx:alpine AS runtime
RUN apk add --no-cache curl
WORKDIR /usr/share/nginx/html
COPY --from=build /app/frontend/dist .
COPY docker/nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
EOF

# 检查.env
if [ ! -f .env ]; then
    cp .env.example .env
fi

echo "✓ 配置文件创建完成"
echo ""

# 步骤3: 构建所有镜像
echo "[3/9] 构建Docker镜像（预计5-15分钟）..."
echo "-----------------------------------------"
docker-compose build --no-cache --pull
echo "✓ 镜像构建完成"
echo ""

# 步骤4: 启动服务
echo "[4/9] 启动所有服务..."
echo "-----------------------------------------"
docker-compose up -d
echo "✓ 服务启动完成"
echo ""

# 步骤5: 等待服务启动
echo "[5/9] 等待服务完全启动（60秒）..."
echo "-----------------------------------------"
for i in {60..1}; do
    echo -ne "  剩余 $i 秒...\r"
    sleep 1
done
echo -ne "\n"
echo ""

# 步骤6: 检查容器状态
echo "[6/9] 检查容器状态..."
echo "-----------------------------------------"
docker-compose ps
echo ""

# 步骤7: 查看服务日志
echo "[7/9] 查看服务日志..."
echo "-----------------------------------------"
echo "=== 前端日志（最后10行） ==="
docker logs tradingagents-frontend --tail 10 2>&1
echo ""
echo "=== 后端日志（最后10行） ==="
docker logs tradingagents-backend --tail 10 2>&1
echo ""

# 步骤8: 验证配置和测试
echo "[8/9] 验证配置和测试..."
echo "-----------------------------------------"

# 验证API地址
echo "验证前端API地址："
if docker exec tradingagents-frontend grep -q "39.97.33.153" /usr/share/nginx/html/js/*.js 2>/dev/null; then
    echo "✓ API地址配置正确: http://39.97.33.153:8000"
else
    echo "✗ API地址未找到"
fi

# 健康检查
echo ""
echo "健康检查："
FRONTEND_HEALTH=$(curl -s http://localhost:3000/health 2>/dev/null)
if [ "$FRONTEND_HEALTH" == "healthy" ]; then
    echo "✓ 前端: healthy"
else
    echo "✗ 前端: $FRONTEND_HEALTH"
fi

BACKEND_HEALTH=$(curl -s http://localhost:8000/health 2>/dev/null)
if echo "$BACKEND_HEALTH" | grep -q "healthy"; then
    echo "✓ 后端: healthy"
else
    echo "✗ 后端: $BACKEND_HEALTH"
fi

# 端口检查
echo ""
echo "端口监听："
netstat -tlnp | grep -E ":(3000|8000)" 2>/dev/null || ss -tlnp | grep -E ":(3000|8000)" 2>/dev/null
echo ""

# 步骤9: 最终报告
echo "[9/9] 部署完成报告"
echo "-----------------------------------------"
echo ""
echo "✅ 部署成功！"
echo ""
echo "访问地址："
echo "  🌐 前端界面: http://39.97.33.153:3000"
echo "  📚 后端文档: http://39.97.33.153:8000/docs"
echo "  ❤️  健康检查: http://39.97.33.153:8000/health"
echo ""
echo "========================================="
echo ""
echo "常用命令："
echo "  查看所有日志: docker-compose logs -f"
echo "  查看前端日志: docker logs tradingagents-frontend -f"
echo "  查看后端日志: docker logs tradingagents-backend -f"
echo "  重启服务: docker-compose restart"
echo "  停止服务: docker-compose down"
echo ""
echo "部署时间: $(date)"
echo "========================================="
