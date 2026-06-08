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
from app.services.research_task_service import get_research_task_service

router = APIRouter(prefix="/api/market-intelligence", tags=["market-intelligence"])


REPORT_TYPE_LABELS = {
    "pre_market": "开盘前市场情报报告",
    "intraday": "盘中市场情报快报",
    "closing": "收盘复盘",
    "event_flash": "突发事件影响卡片",
    "research_digest": "研报深度摘要",
}


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
    task_service = get_research_task_service()
    task = await task_service.create_task(
        user_id=str(current_user.get("id") or current_user.get("_id") or "system"),
        title=REPORT_TYPE_LABELS.get(report_type, "市场情报报告"),
        module="market_intelligence",
        task_type="market_intelligence_report",
        parameters={"report_type": report_type, "force_refresh": force_refresh},
        route_path="/market-intelligence",
        source="manual",
        tags=["市场情报", "报告生成"],
    )
    task_id = task["task_id"]
    try:
        await task_service.mark_processing(task_id, "正在生成市场情报报告", progress=15)
        report = await service.generate_report(report_type=report_type, force_refresh=force_refresh)
        report_id = str(report.get("_id") or report.get("report_id") or "")
        result_payload = {
            **report,
            "report_id": report_id,
            "route_path": "/market-intelligence",
        }
        await task_service.mark_completed(
            task_id,
            result=result_payload,
            message=f"{REPORT_TYPE_LABELS.get(report_type, '市场情报报告')}生成完成",
        )
        report["task_id"] = task_id
    except Exception as exc:
        await task_service.mark_failed(task_id, str(exc))
        raise
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


@router.get("/documents", response_model=dict)
async def get_market_documents(
    hours: int = Query(36, ge=1, le=168),
    code: str = Query("", description="可选股票代码"),
    cluster_id: str = Query("", description="可选事件簇ID"),
    source: str = Query("", description="可选来源"),
    document_type: str = Query("", description="news|stock_news|social_comment|announcement|research_report|quant_signal"),
    limit: int = Query(100, ge=1, le=300),
    current_user: dict = Depends(get_current_user),
):
    service = await get_market_intelligence_service()
    docs = await service.get_documents(
        hours=hours,
        code=code or None,
        cluster_id=cluster_id or None,
        source=source or None,
        document_type=document_type or None,
        limit=limit,
    )
    return ok(data={"documents": docs, "count": len(docs)}, message="获取市场证据成功")


@router.get("/event-clusters", response_model=dict)
async def get_event_clusters(
    hours: int = Query(36, ge=1, le=168),
    limit: int = Query(50, ge=1, le=100),
    current_user: dict = Depends(get_current_user),
):
    service = await get_market_intelligence_service()
    clusters = await service.get_event_clusters(hours=hours, limit=limit)
    return ok(data={"clusters": clusters, "count": len(clusters)}, message="获取事件聚合成功")


@router.post("/events/{event_id}/analyze", response_model=dict)
async def analyze_event_impact(
    event_id: str,
    force: bool = Query(False, description="是否强制重新分析"),
    current_user: dict = Depends(get_current_user),
):
    service = await get_market_intelligence_service()
    task_service = get_research_task_service()
    event = await service.get_global_event(event_id)
    if not event:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="全球事件不存在")
    task = await task_service.create_task(
        user_id=str(current_user.get("id") or current_user.get("_id") or "system"),
        title=f"事件影响分析：{event.get('title') or event_id}",
        module="market_intelligence",
        task_type="event_impact_analysis",
        parameters={"event_id": event_id, "force": force},
        related_id=event_id,
        route_path="/market-intelligence",
        source="manual",
        tags=["市场情报", "事件分析"],
    )
    task_id = task["task_id"]
    try:
        await task_service.mark_processing(task_id, "事件影响分析已加入后台队列", progress=10)
        await service.queue_event_impact_analysis(
            [event],
            queue_source="manual",
            force=force,
            kick=True,
            research_task_id=task_id,
        )
        analysis = await service.get_event_analysis(event_id) or {
            "event_id": event_id,
            "event_title": event.get("title"),
            "status": "queued",
            "research_task_id": task_id,
        }
        analysis["task_id"] = task_id
        await task_service.update_task(
            task_id,
            status="processing",
            progress=15,
            message="事件影响分析排队中，后台完成后自动刷新",
            current_step="queued",
            result={**analysis, "route_path": "/market-intelligence"},
        )
    except ValueError:
        await task_service.mark_failed(task_id, "全球事件不存在")
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="全球事件不存在")
    except Exception as exc:
        await task_service.mark_failed(task_id, str(exc))
        raise
    return ok(data=analysis, message="事件影响分析已加入后台队列")


@router.get("/events/{event_id}/analysis", response_model=dict)
async def get_event_impact_analysis(
    event_id: str,
    current_user: dict = Depends(get_current_user),
):
    service = await get_market_intelligence_service()
    analysis = await service.get_event_analysis(event_id)
    if not analysis:
        return ok(data={"event_id": event_id, "status": "not_started"}, message="事件尚未分析")
    return ok(data=analysis, message="获取事件影响分析成功")


@router.get("/regions/{region_id}/events", response_model=dict)
async def get_region_events(
    region_id: str,
    hours: int = Query(72, ge=1, le=168),
    current_user: dict = Depends(get_current_user),
):
    service = await get_market_intelligence_service()
    events = await service.get_global_events(hours=hours, severity="all")
    region_lower = region_id.lower()
    filtered = [
        event for event in events
        if region_lower in str(event.get("region") or "").lower()
        or region_lower in str(event.get("country") or "").lower()
        or region_lower in str(event.get("location_name") or "").lower()
    ]
    return ok(data={"events": filtered, "count": len(filtered)}, message="获取区域事件成功")


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


@router.get("/stocks/{code}/detail", response_model=dict)
async def get_stock_intelligence_detail(
    code: str,
    hours: int = Query(72, ge=1, le=168),
    current_user: dict = Depends(get_current_user),
):
    service = await get_market_intelligence_service()
    stock = await service.get_stock_detail(code, hours=hours)
    if not stock:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="个股情报不存在")
    return ok(data=stock, message="获取个股情报详情成功")


@router.get("/stocks/{code}/comments", response_model=dict)
async def get_stock_comments(
    code: str,
    hours: int = Query(72, ge=1, le=168),
    limit: int = Query(200, ge=1, le=500),
    current_user: dict = Depends(get_current_user),
):
    service = await get_market_intelligence_service()
    comments = await service.get_stock_comments(code, hours=hours, limit=limit)
    return ok(data=comments, message="获取个股评论舆情成功")


@router.get("/methodology", response_model=dict)
async def get_market_intelligence_methodology(
    current_user: dict = Depends(get_current_user),
):
    service = await get_market_intelligence_service()
    methodology = await service.get_methodology()
    return ok(data=methodology, message="获取评分方法论成功")


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
