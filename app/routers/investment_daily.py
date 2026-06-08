"""
Investment daily report API.
"""
import json

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse

from app.core.response import ok
from app.routers.auth_db import get_current_user
from app.services.investment_daily_service import get_investment_daily_service
from app.services.research_task_service import get_research_task_service

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
    task_service = get_research_task_service()
    task = await task_service.create_task(
        user_id=str(current_user.get("id") or current_user.get("_id") or "system"),
        title="投资日报生成",
        module="investment_daily",
        task_type="investment_daily_report",
        parameters={"force_refresh": force_refresh},
        route_path="/investment-daily",
        source="manual",
        tags=["投资日报", "报告生成"],
    )
    task_id = task["task_id"]
    try:
        await task_service.mark_processing(task_id, "正在生成投资日报", progress=15)
        report = await service.generate_daily_report(force_refresh=force_refresh)
        report_id = str(report.get("_id") or report.get("report_id") or "")
        await task_service.mark_completed(
            task_id,
            result={
                **report,
                "report_id": report_id,
                "route_path": "/investment-daily",
            },
            message="投资日报生成完成",
        )
        report["task_id"] = task_id
    except Exception as exc:
        await task_service.mark_failed(task_id, str(exc))
        raise
    return ok(data=report, message="投资日报生成成功")


@router.post("/{report_id}/preanalyze", response_model=dict)
async def preanalyze_investment_daily_candidates(
    report_id: str,
    limit: int = Query(8, ge=1, le=10),
    current_user: dict = Depends(get_current_user),
):
    service = await get_investment_daily_service()
    task_service = get_research_task_service()
    task = await task_service.create_task(
        user_id=str(current_user.get("id") or current_user.get("_id") or "system"),
        title="投资日报候选股预分析",
        module="investment_daily",
        task_type="investment_daily_preanalysis",
        parameters={"report_id": report_id, "limit": limit},
        related_id=report_id,
        route_path="/investment-daily",
        source="manual",
        tags=["投资日报", "候选股预分析", "TradingAgents"],
    )
    task_id = task["task_id"]
    try:
        await task_service.mark_processing(task_id, "正在提交候选股 TradingAgents 并发分析", progress=35)
        result = await service.preanalyze_report_candidates(
            report_id,
            user_id=str(current_user.get("id") or current_user.get("_id") or ""),
            limit=limit,
        )
        result["task_id"] = task_id
        await task_service.mark_completed(
            task_id,
            result={
                **result,
                "report_id": report_id,
                "route_path": "/investment-daily",
            },
            message=f"已提交 {result.get('count', len(result.get('task_ids', [])))} 个候选股分析任务",
        )
    except ValueError:
        await task_service.mark_failed(task_id, "投资日报不存在")
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="投资日报不存在")
    except Exception as exc:
        await task_service.mark_failed(task_id, str(exc))
        raise
    return ok(data=result, message="候选股预分析已提交")


@router.get("/{report_id}/download")
async def download_investment_daily_report(
    report_id: str,
    format: str = Query("pdf", description="pdf|markdown|json"),
    current_user: dict = Depends(get_current_user),
):
    service = await get_investment_daily_service()
    report = await service.get_report(report_id)
    if not report:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="投资日报不存在")

    report_date = report.get("report_date") or "daily"
    markdown_content = report.get("markdown") or f"# {report.get('title', '投资日报')}\n\n{report.get('summary', '')}"

    if format == "json":
        content = json.dumps(report, ensure_ascii=False, indent=2, default=str).encode("utf-8")
        return StreamingResponse(
            iter([content]),
            media_type="application/json",
            headers={"Content-Disposition": f"attachment; filename=investment_daily_{report_date}.json"},
        )

    if format in {"markdown", "md"}:
        return StreamingResponse(
            iter([markdown_content.encode("utf-8")]),
            media_type="text/markdown",
            headers={"Content-Disposition": f"attachment; filename=investment_daily_{report_date}.md"},
        )

    if format == "pdf":
        try:
            from app.utils.report_exporter import report_exporter

            html_content = report_exporter._markdown_to_html(markdown_content)
            pdf_content = report_exporter._generate_pdf_with_pdfkit(html_content)
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"PDF生成失败: {str(e)}")
        return StreamingResponse(
            iter([pdf_content]),
            media_type="application/pdf",
            headers={"Content-Disposition": f"attachment; filename=investment_daily_{report_date}.pdf"},
        )

    raise HTTPException(status_code=400, detail=f"不支持的下载格式: {format}")
