"""
Market intelligence dashboard API.
"""
import asyncio

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.core.response import ok
from app.routers.auth_db import get_current_user
from app.services.market_intelligence_service import (
    REPORT_TYPES,
    get_market_intelligence_service,
)
from app.services.market_evidence_service import get_market_evidence_service

router = APIRouter(prefix="/api/market-intelligence", tags=["market-intelligence"])


@router.get("/latest", response_model=dict)
async def get_latest_market_intelligence(
    hours: int = Query(36, ge=1, le=168),
    current_user: dict = Depends(get_current_user),
):
    service = await get_market_intelligence_service()
    dashboard = await service.build_dashboard(hours=hours)
    return ok(data=dashboard, message="获取市场情报看板成功")


@router.post("/generate", response_model=dict)
async def generate_market_intelligence_report(
    report_type: str = Query("pre_market", description="pre_market|intraday|closing|event_flash"),
    force_refresh: bool = Query(True, description="是否先执行36小时强刷"),
    current_user: dict = Depends(get_current_user),
):
    service = await get_market_intelligence_service()
    if report_type not in REPORT_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"不支持的报告类型: {report_type}",
        )
    report = await service.generate_report(report_type=report_type, force_refresh=force_refresh)
    return ok(data=report, message="市场情报报告生成成功")


@router.get("/history", response_model=dict)
async def get_market_intelligence_history(
    limit: int = Query(20, ge=1, le=100),
    current_user: dict = Depends(get_current_user),
):
    service = await get_market_intelligence_service()
    reports = await service.get_history(limit=limit)
    return ok(data={"reports": reports, "count": len(reports)}, message="获取市场情报历史成功")


@router.get("/global-events", response_model=dict)
async def get_global_events(
    hours: int = Query(36, ge=1, le=168),
    severity: str = Query("all", description="all|high"),
    current_user: dict = Depends(get_current_user),
):
    service = await get_market_intelligence_service()
    events = await service.get_global_events(hours=hours, severity=severity)
    return ok(data={"events": events, "count": len(events)}, message="获取全球事件成功")


@router.get("/global-events/{event_id}", response_model=dict)
async def get_global_event(
    event_id: str,
    current_user: dict = Depends(get_current_user),
):
    service = await get_market_intelligence_service()
    event = await service.get_global_event(event_id)
    if not event:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="全球事件不存在")
    return ok(data=event, message="获取全球事件详情成功")


@router.get("/themes", response_model=dict)
async def get_theme_signals(current_user: dict = Depends(get_current_user)):
    service = await get_market_intelligence_service()
    themes = await service.get_themes()
    return ok(data={"themes": themes, "count": len(themes)}, message="获取主题信号成功")


@router.get("/stocks/{code}", response_model=dict)
async def get_stock_signal(
    code: str,
    current_user: dict = Depends(get_current_user),
):
    service = await get_market_intelligence_service()
    stock = await service.get_stock_signal(code)
    if not stock:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="个股信号不存在")
    return ok(data=stock, message="获取个股信号成功")


@router.get("/stocks/{code}/evidence", response_model=dict)
async def get_stock_evidence(
    code: str,
    hours: int = Query(36, ge=1, le=168),
    company_name: str = Query("", description="可选股票名称，用于显示和相关性补充"),
    current_user: dict = Depends(get_current_user),
):
    service = get_market_evidence_service()
    evidence = await asyncio.to_thread(
        service.build_stock_evidence_context,
        code,
        hours=hours,
        company_name=company_name,
        refresh_if_stale=False,
        max_chars=16000,
    )
    return ok(data={"code": code, "hours": hours, "evidence_markdown": evidence}, message="获取个股市场证据成功")


@router.post("/stocks/{code}/refresh-evidence", response_model=dict)
async def refresh_stock_evidence(
    code: str,
    company_name: str = Query("", description="可选股票名称，用于提高搜索相关度"),
    current_user: dict = Depends(get_current_user),
):
    service = get_market_evidence_service()
    result = await asyncio.to_thread(
        service.refresh_stock_evidence_sync,
        code,
        company_name=company_name,
    )
    return ok(data=result, message="个股证据刷新完成")


@router.get("/sources/status", response_model=dict)
async def get_market_intelligence_source_status(
    current_user: dict = Depends(get_current_user),
):
    service = await get_market_intelligence_service()
    statuses = await service.get_source_status()
    return ok(data={"sources": statuses, "count": len(statuses)}, message="获取数据源状态成功")
