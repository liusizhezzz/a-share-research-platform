#!/bin/bash

echo "========================================="
echo "  TradingAgents-CN 全自动部署"
echo "========================================="
echo ""

# 步骤1: 等待构建完成
echo "[步骤 1/10] 等待Docker镜像构建完成..."
echo "-----------------------------------------"
WAIT_COUNT=0
MAX_WAIT=60  # 最多等待30分钟（60次×30秒）

while [ $WAIT_COUNT -lt $MAX_WAIT ]; do
    if docker images | grep -q "tradingagents-backend.*v1.0.0-preview" && \
       docker images | grep -q "tradingagents-frontend.*v1.0.0-preview"; then
        echo "✓ 镜像构建完成！"
        break
    fi
    
    echo "[$(date +%H:%M:%S)] 等待构建中... ($((WAIT_COUNT * 30))秒)"
    sleep 30
    WAIT_COUNT=$((WAIT_COUNT + 1))
done

if [ $WAIT_COUNT -eq $MAX_WAIT ]; then
    echo "⚠ 等待超时，检查构建状态..."
    docker images | grep tradingagents
fi

echo ""

# 步骤2: 清理旧环境
echo "[步骤 2/10] 清理旧容器和数据..."
echo "-----------------------------------------"
docker-compose down 2>/dev/null
docker volume rm tradingagents_mongodb_data tradingagents_redis_data 2>/dev/null
echo "✓ 清理完成"
echo ""

# 步骤3: 创建配置文件
echo "[步骤 3/10] 创建配置文件..."
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
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 60s

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
    healthcheck:
      test: ["CMD-SHELL", "curl -f http://localhost/health || exit 1"]
      interval: 30s
      timeout: 10s
      retries: 3

volumes:
  mongodb_data:
  redis_data:

networks:
  tradingagents-network:
    driver: bridge
EOF

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

# 检查.env文件
if [ ! -f .env ]; then
    echo "⚠ .env文件不存在，复制模板..."
    cp .env.example .env
fi

echo "✓ 配置文件创建完成"
echo ""

# 步骤4: 启动服务
echo "[步骤 4/10] 启动所有服务..."
echo "-----------------------------------------"
docker-compose up -d
echo "✓ 服务启动完成"
echo ""

# 步骤5: 等待服务启动
echo "[步骤 5/10] 等待服务完全启动（60秒）..."
echo "-----------------------------------------"
for i in {60..1}; do
    echo -ne "  剩余 $i 秒...\r"
    sleep 1
done
echo -ne "\n"
echo ""

# 步骤6: 检查容器状态
echo "[步骤 6/10] 检查容器状态..."
echo "-----------------------------------------"
docker-compose ps
echo ""

# 步骤7: 查看服务日志
echo "[步骤 7/10] 查看服务日志..."
echo "-----------------------------------------"
echo "前端日志（最后10行）："
docker logs tradingagents-frontend --tail 10 2>&1
echo ""
echo "后端日志（最后10行）："
docker logs tradingagents-backend --tail 10 2>&1
echo ""

# 步骤8: 验证API地址
echo "[步骤 8/10] 验证前端API地址..."
echo "-----------------------------------------"
if docker exec tradingagents-frontend grep -q "39.97.33.153" /usr/share/nginx/html/js/*.js 2>/dev/null; then
    echo "✓ 前端API地址配置正确"
    docker exec tradingagents-frontend grep "39.97.33.153" /usr/share/nginx/html/js/*.js 2>/dev/null | head -1
else
    echo "✗ 前端API地址未找到"
fi
echo ""

# 步骤9: 健康检查
echo "[步骤 9/10] 测试服务健康状态..."
echo "-----------------------------------------"
FRONTEND_HEALTH=$(curl -s http://localhost:3000/health 2>/dev/null)
if [ "$FRONTEND_HEALTH" == "healthy" ]; then
    echo "✓ 前端健康检查通过"
else
    echo "✗ 前端健康检查失败: $FRONTEND_HEALTH"
fi

BACKEND_HEALTH=$(curl -s http://localhost:8000/health 2>/dev/null)
if echo "$BACKEND_HEALTH" | grep -q "healthy"; then
    echo "✓ 后端健康检查通过"
else
    echo "✗ 后端健康检查失败: $BACKEND_HEALTH"
fi
echo ""

# 步骤10: 端口检查
echo "[步骤 10/10] 检查端口监听..."
echo "-----------------------------------------"
netstat -tlnp | grep -E ":(3000|8000)" 2>/dev/null || ss -tlnp | grep -E ":(3000|8000)" 2>/dev/null
echo ""

# 最终报告
echo "========================================="
echo "  🎉 部署完成！"
echo "========================================="
echo ""
echo "访问地址："
echo "  🌐 前端: http://39.97.33.153:3000"
echo "  📚 后端: http://39.97.33.153:8000/docs"
echo "  ❤️  健康检查: http://39.97.33.153:8000/health"
echo ""
echo "========================================="
echo ""
echo "如果外网无法访问，请检查："
echo "1. 阿里云安全组规则（开放3000和8000端口）"
echo "2. 服务器防火墙设置"
echo ""
echo "常用命令："
echo "  查看日志: docker-compose logs -f"
echo "  重启服务: docker-compose restart"
echo "  停止服务: docker-compose down"
echo ""
echo "部署时间: $(date)"
echo "========================================="
