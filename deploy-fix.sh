#!/bin/bash

echo "========================================="
echo "开始修复部署..."
echo "========================================="

# 1. 停止所有容器
echo "1. 停止所有容器..."
docker-compose down

# 2. 清理MongoDB数据
echo "2. 清理MongoDB数据..."
docker volume rm tradingagents_mongodb_data 2>/dev/null
docker volume rm tradingagents_redis_data 2>/dev/null

# 3. 删除旧镜像
echo "3. 删除旧镜像..."
docker rmi tradingagents-frontend:v1.0.0-preview tradingagents-backend:v1.0.0-preview 2>/dev/null

# 4. 清理缓存
echo "4. 清理Docker缓存..."
docker system prune -f

# 5. 创建docker-compose.yml
echo "5. 创建docker-compose配置..."
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
      - MONGODB_HOST=mongodb
      - REDIS_HOST=redis
      - PYTHONUNBUFFERED=1
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

# 6. 更新Dockerfile.frontend
echo "6. 更新前端Dockerfile..."
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

echo "========================================="
echo "开始构建镜像（需要5-10分钟）..."
echo "========================================="

# 7. 构建镜像
docker-compose build --no-cache

echo "========================================="
echo "启动服务..."
echo "========================================="

# 8. 启动服务
docker-compose up -d

echo "等待服务启动..."
sleep 40

# 9. 检查状态
echo "========================================="
echo "检查服务状态..."
echo "========================================="
docker-compose ps

echo ""
echo "========================================="
echo "验证前端API地址..."
echo "========================================="
docker exec tradingagents-frontend grep -r "39.97.33.153" /usr/share/nginx/html/js/ | head -3

echo ""
echo "========================================="
echo "✅ 部署完成！"
echo "前端: http://39.97.33.153:3000"
echo "后端: http://39.97.33.153:8000/docs"
echo "========================================="
