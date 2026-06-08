"""
Research task registry for non-stock-analysis workflows.

Market intelligence and investment daily jobs are report/insight workflows, not
single-stock TradingAgents tasks.  This service records them in a shared shape
so the existing task center can monitor both kinds of work.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional

from bson import ObjectId

from app.core.database import get_mongo_db


CHINA_TZ = timezone(timedelta(hours=8))


def _now() -> datetime:
    return datetime.utcnow()


def _iso(value: Any) -> Any:
    if isinstance(value, datetime):
        dt = value.replace(tzinfo=CHINA_TZ) if value.tzinfo is None else value
        return dt.isoformat()
    return value


def _json_safe(value: Any) -> Any:
    if isinstance(value, ObjectId):
        return str(value)
    if isinstance(value, datetime):
        return _iso(value)
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    if isinstance(value, dict):
        return {key: _json_safe(item) for key, item in value.items()}
    return value


class ResearchTaskService:
    """Mongo-backed task registry for research/report workflows."""

    def __init__(self):
        self.db = get_mongo_db()
        self.collection = self.db.research_tasks
        self._indexes_ready = False

    async def ensure_indexes(self) -> None:
        if self._indexes_ready:
            return
        await self.collection.create_index("task_id", unique=True, background=True)
        await self.collection.create_index([("user_id", 1), ("created_at", -1)], background=True)
        await self.collection.create_index([("status", 1), ("created_at", -1)], background=True)
        await self.collection.create_index([("module", 1), ("created_at", -1)], background=True)
        self._indexes_ready = True

    async def create_task(
        self,
        *,
        user_id: str,
        title: str,
        module: str,
        task_type: str,
        parameters: Optional[Dict[str, Any]] = None,
        related_id: Optional[str] = None,
        route_path: Optional[str] = None,
        source: str = "manual",
        parent_task_id: Optional[str] = None,
        tags: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        await self.ensure_indexes()
        task_id = f"research-{uuid.uuid4()}"
        now = _now()
        doc = {
            "task_id": task_id,
            "task_kind": "research",
            "user_id": str(user_id or "system"),
            "title": title,
            "module": module,
            "task_type": task_type,
            "status": "pending",
            "progress": 0,
            "message": "任务已创建，等待执行",
            "current_step": "pending",
            "parameters": parameters or {},
            "related_id": related_id,
            "route_path": route_path,
            "source": source,
            "parent_task_id": parent_task_id,
            "tags": tags or [],
            "created_at": now,
            "updated_at": now,
            "started_at": None,
            "completed_at": None,
            "result": None,
            "last_error": None,
        }
        await self.collection.insert_one(doc)
        return self.to_task_item(doc)

    async def update_task(
        self,
        task_id: str,
        *,
        status: Optional[str] = None,
        progress: Optional[int] = None,
        message: Optional[str] = None,
        current_step: Optional[str] = None,
        result: Optional[Dict[str, Any]] = None,
        error_message: Optional[str] = None,
        extra: Optional[Dict[str, Any]] = None,
    ) -> Optional[Dict[str, Any]]:
        await self.ensure_indexes()
        now = _now()
        updates: Dict[str, Any] = {"updated_at": now}

        if status is not None:
            updates["status"] = status
            if status in {"processing", "running"}:
                updates["started_at"] = now
            if status in {"completed", "failed", "cancelled"}:
                updates["completed_at"] = now

        if progress is not None:
            updates["progress"] = max(0, min(100, int(progress)))
        if message is not None:
            updates["message"] = message
        if current_step is not None:
            updates["current_step"] = current_step
        if result is not None:
            updates["result"] = result
            if isinstance(result, dict):
                related_id = result.get("report_id") or result.get("_id") or result.get("event_id")
                if related_id:
                    updates["related_id"] = str(related_id)
                if result.get("route_path"):
                    updates["route_path"] = result.get("route_path")
        if error_message is not None:
            updates["last_error"] = error_message
            updates["error_message"] = error_message
        if extra:
            updates.update(extra)

        await self.collection.update_one({"task_id": task_id}, {"$set": updates})
        doc = await self.collection.find_one({"task_id": task_id})
        return self.to_task_item(doc) if doc else None

    async def mark_processing(self, task_id: str, message: str, *, progress: int = 10) -> Optional[Dict[str, Any]]:
        return await self.update_task(
            task_id,
            status="processing",
            progress=progress,
            message=message,
            current_step="processing",
        )

    async def mark_completed(
        self,
        task_id: str,
        *,
        result: Optional[Dict[str, Any]] = None,
        message: str = "任务完成",
    ) -> Optional[Dict[str, Any]]:
        return await self.update_task(
            task_id,
            status="completed",
            progress=100,
            message=message,
            current_step="completed",
            result=result,
        )

    async def mark_failed(self, task_id: str, error_message: str) -> Optional[Dict[str, Any]]:
        return await self.update_task(
            task_id,
            status="failed",
            progress=0,
            message="任务失败",
            current_step="failed",
            error_message=error_message,
        )

    async def get_task(self, task_id: str) -> Optional[Dict[str, Any]]:
        await self.ensure_indexes()
        doc = await self.collection.find_one({"task_id": task_id})
        return self.to_task_item(doc) if doc else None

    async def list_tasks(
        self,
        *,
        user_id: Optional[str] = None,
        status: Optional[str] = None,
        module: Optional[str] = None,
        limit: int = 20,
        offset: int = 0,
    ) -> Dict[str, Any]:
        await self.ensure_indexes()
        query: Dict[str, Any] = {}
        if user_id:
            query["user_id"] = {"$in": [str(user_id), "system"]}
        if status:
            query["status"] = "processing" if status == "running" else status
        if module:
            query["module"] = module

        total = await self.collection.count_documents(query)
        cursor = self.collection.find(query).sort("created_at", -1).skip(offset).limit(limit)
        tasks = []
        async for doc in cursor:
            tasks.append(self.to_task_item(doc))
        return {"tasks": tasks, "total": total}

    async def delete_task(self, task_id: str) -> bool:
        await self.ensure_indexes()
        result = await self.collection.delete_one({"task_id": task_id})
        return result.deleted_count > 0

    async def mark_task_failed(self, task_id: str, message: str = "用户手动标记为失败") -> bool:
        task = await self.get_task(task_id)
        if not task:
            return False
        await self.mark_failed(task_id, message)
        return True

    def to_task_item(self, doc: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        if not doc:
            return {}
        item = dict(doc)
        item.pop("_id", None)
        title = item.get("title") or item.get("task_type") or "投研任务"
        module = item.get("module") or "research"
        task_type = item.get("task_type") or "research_task"
        item.update({
            "task_kind": "research",
            "symbol": None,
            "stock_code": None,
            "stock_symbol": None,
            "stock_name": title,
            "display_title": title,
            "module": module,
            "task_type": task_type,
            "start_time": item.get("started_at") or item.get("created_at"),
            "end_time": item.get("completed_at"),
            "result_data": item.get("result"),
        })
        return _json_safe(item)

    def to_result_payload(self, task: Dict[str, Any]) -> Dict[str, Any]:
        result = task.get("result_data") or task.get("result") or {}
        if not isinstance(result, dict):
            result = {"raw_result": result}
        markdown = (
            result.get("markdown")
            or result.get("markdown_report")
            or result.get("analysis_markdown")
            or result.get("summary")
            or ""
        )
        summary = result.get("summary") or task.get("message") or task.get("title") or "任务结果"
        recommendation = markdown or summary
        reports = result.get("reports")
        if not reports:
            reports = {
                "result": markdown or summary,
                "metadata": result,
            }
        return _json_safe({
            "analysis_id": task.get("task_id"),
            "task_id": task.get("task_id"),
            "task_kind": "research",
            "module": task.get("module"),
            "task_type": task.get("task_type"),
            "title": task.get("title") or task.get("display_title"),
            "summary": summary,
            "recommendation": recommendation,
            "risk_level": result.get("risk_level", "中等"),
            "confidence_score": result.get("confidence_score", 0),
            "key_points": result.get("key_points", []),
            "reports": reports,
            "route_path": task.get("route_path"),
            "related_id": task.get("related_id"),
            "status": task.get("status"),
            "created_at": task.get("created_at"),
            "updated_at": task.get("updated_at"),
        })


_research_task_service: Optional[ResearchTaskService] = None


def get_research_task_service() -> ResearchTaskService:
    global _research_task_service
    if _research_task_service is None:
        _research_task_service = ResearchTaskService()
    return _research_task_service
