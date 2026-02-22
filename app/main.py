"""FastAPI 主入口 - 提供 widgets.json 和 apps.json 端点"""

import json
from pathlib import Path
from fastapi import FastAPI, APIRouter
from fastapi.responses import JSONResponse
from typing import Dict, Any

from app.routers.stock_router import router as stock_router
from app.routers.financial_router import router as financial_router
from app.routers.ai_router import router as ai_router

# 创建主路由器
main_router = APIRouter()

@main_router.get("/")
async def read_root() -> Dict[str, Any]:
    """根端点，返回基本信息"""
    return {
        "name": "A-Share Research Platform",
        "version": "1.0.0",
        "description": "OpenBB Workspace Custom Backend for A股投资研究"
    }

@main_router.get("/widgets.json")
async def get_widgets() -> JSONResponse:
    """返回 widgets.json 配置文件

    OpenBB Workspace 会自动调用此端点获取所有可用 widgets
    """
    widgets_file = Path(__file__).parent.parent.parent / "widgets.json"
    if widgets_file.exists():
        return JSONResponse(
            content=json.load(widgets_file.open())
        )
    else:
        return JSONResponse(
            content={"error": "widgets.json file not found"},
            status_code=404
        )

@main_router.get("/apps.json")
async def get_apps() -> JSONResponse:
    """返回 apps.json 配置文件

    OpenBB Workspace 会自动调用此端点获取 app 布局
    """
    apps_file = Path(__file__).parent.parent.parent / "apps.json"
    if apps_file.exists():
        return JSONResponse(
            content=json.load(apps_file.open())
        )
    else:
        return JSONResponse(
            content={"error": "apps.json file not found"},
            status_code=404
        )

# 注册所有路由
app.include_router(stock_router)
app.include_router(financial_router)
app.include_router(ai_router)
app.include_router(main_router)
