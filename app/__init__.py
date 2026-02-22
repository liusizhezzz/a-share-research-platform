"""A-Share Research Platform - FastAPI Application"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(
    title="A-Share Research Platform",
    description="OpenBB Workspace Custom Backend - A股投研平台",
    version="1.0.0"
)

# 配置 CORS 允许 OpenBB Workspace 访问
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://pro.openbb.co", "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

from app.main import main_router

# 注册路由
app.include_router(stock_router, prefix="/api/stock", tags=["Stock"])
app.include_router(financial_router, prefix="/api/financial", tags=["Financial"])
app.include_router(ai_router, prefix="/api/ai", tags=["AI"])
