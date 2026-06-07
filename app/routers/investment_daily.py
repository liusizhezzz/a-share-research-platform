"""
Investment daily report API.
"""
from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.core.response import ok
from app.routers.auth_db import get_current_user
from app.services.investment_daily_service import get_investment_daily_service

router = APIRouter(prefix="/api/investment-daily", tags=["investment-daily"])


@router.get("/latest", response_model=dict)
async def get_latest_investment_daily(current_user: dict = Depends(get_current_user)):
    service = await get_investment_daily_service()
    report = await service.get_latest_report()
    return ok(data=report, message="获取投资日报成功" if report else "暂无投资日报")


@router.get("/history", response_model=dict)
async def get_investment_daily_history(
    limit: int = Query(20, ge=1, le=100),
    current_user: dict = Depends(get_current_user),
):
    service = await get_investment_daily_service()
    reports = await service.get_history(limit=limit)
    return ok(data={"reports": reports, "count": len(reports)}, message="获取投资日报历史成功")


@router.get("/{report_id}", response_model=dict)
async def get_investment_daily_report(
    report_id: str,
    current_user: dict = Depends(get_current_user),
):
    service = await get_investment_daily_service()
    report = await service.get_report(report_id)
    if not report:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="投资日报不存在")
    return ok(data=report, message="获取投资日报成功")


@router.post("/generate", response_model=dict)
async def generate_investment_daily(
    force_refresh: bool = Query(True, description="是否强制刷新"),
    current_user: dict = Depends(get_current_user),
):
    service = await get_investment_daily_service()
    report = await service.generate_daily_report(force_refresh=force_refresh)
    return ok(data=report, message="投资日报生成成功")
