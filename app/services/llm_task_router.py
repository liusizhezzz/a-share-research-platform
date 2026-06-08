"""
Task-aware DashScope model router.

The router keeps model choice close to the task instead of hard-coding one
global model for every LLM call. It uses DashScope's OpenAI-compatible endpoint
so the rest of the app can treat Qwen and third-party models uniformly.
"""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import httpx

logger = logging.getLogger(__name__)

DASHSCOPE_COMPATIBLE_BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"


TASK_MODEL_DEFAULTS: Dict[str, str] = {
    "deep_stock_analysis": "qwen3.7-max",
    "event_impact": "qwen3.7-max",
    "risk_challenge": "deepseek-v4-pro",
    "daily_report": "qwen3.7-plus",
    "market_report": "qwen3.7-plus",
    "research_digest": "qwen3.7-plus",
    "news_clustering": "qwen3.6-flash",
    "sentiment_scoring": "qwen3.6-flash",
    "tag_extraction": "qwen3.6-flash",
    "event_flash": "deepseek-v4-flash",
    "summary": "qwen3.7-plus",
}


TASK_TOKEN_DEFAULTS: Dict[str, int] = {
    "deep_stock_analysis": 24000,
    "event_impact": 18000,
    "risk_challenge": 16000,
    "daily_report": 20000,
    "market_report": 20000,
    "research_digest": 18000,
    "news_clustering": 8000,
    "sentiment_scoring": 8000,
    "tag_extraction": 6000,
    "event_flash": 10000,
    "summary": 12000,
}


@dataclass
class LLMTaskConfig:
    task_type: str
    provider: str
    model: str
    base_url: str
    max_tokens: int
    temperature: float


class LLMTaskRouter:
    """Resolve task-specific model config and perform lightweight chat calls."""

    def __init__(self) -> None:
        self.base_url = (
            os.getenv("DASHSCOPE_BASE_URL")
            or os.getenv("DASHSCOPE_COMPATIBLE_BASE_URL")
            or DASHSCOPE_COMPATIBLE_BASE_URL
        ).rstrip("/")

    def config_for(self, task_type: str, *, temperature: Optional[float] = None) -> LLMTaskConfig:
        env_key = f"LLM_TASK_MODEL_{task_type.upper()}"
        model = os.getenv(env_key) or TASK_MODEL_DEFAULTS.get(task_type, "qwen3.7-plus")
        max_tokens = int(os.getenv(f"LLM_TASK_MAX_TOKENS_{task_type.upper()}", TASK_TOKEN_DEFAULTS.get(task_type, 12000)))
        return LLMTaskConfig(
            task_type=task_type,
            provider="dashscope",
            model=model,
            base_url=self.base_url,
            max_tokens=max_tokens,
            temperature=0.2 if temperature is None else temperature,
        )

    def public_policy(self) -> Dict[str, Any]:
        """Return non-secret routing policy for UI/methodology endpoints."""
        return {
            "provider": "dashscope",
            "base_url": self.base_url,
            "task_models": dict(TASK_MODEL_DEFAULTS),
            "token_defaults": dict(TASK_TOKEN_DEFAULTS),
            "secret_source": "DASHSCOPE_API_KEY environment variable",
        }

    async def chat_jsonish(
        self,
        *,
        task_type: str,
        messages: List[Dict[str, str]],
        temperature: Optional[float] = None,
        timeout: float = 120.0,
    ) -> Dict[str, Any]:
        """Call DashScope compatible chat API and return content plus metadata.

        The method is intentionally conservative: if the key is missing or the
        provider fails, callers still get a structured fallback instead of a hard
        dashboard failure.
        """
        cfg = self.config_for(task_type, temperature=temperature)
        api_key = os.getenv("DASHSCOPE_API_KEY")
        if not api_key:
            return {
                "status": "skipped",
                "model": cfg.model,
                "provider": cfg.provider,
                "content": "",
                "error": "DASHSCOPE_API_KEY is not configured",
            }

        payload = {
            "model": cfg.model,
            "messages": messages,
            "temperature": cfg.temperature,
            "max_tokens": cfg.max_tokens,
        }
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        try:
            async with httpx.AsyncClient(timeout=timeout, trust_env=False) as client:
                response = await client.post(f"{cfg.base_url}/chat/completions", json=payload, headers=headers)
                response.raise_for_status()
                data = response.json()
            choice = (data.get("choices") or [{}])[0]
            message = choice.get("message") or {}
            usage = data.get("usage") or {}
            return {
                "status": "ready",
                "model": cfg.model,
                "provider": cfg.provider,
                "content": message.get("content") or "",
                "usage": usage,
            }
        except Exception as exc:
            logger.warning("DashScope task call failed for %s/%s: %s", task_type, cfg.model, exc)
            return {
                "status": "error",
                "model": cfg.model,
                "provider": cfg.provider,
                "content": "",
                "error": str(exc),
            }


_llm_task_router: Optional[LLMTaskRouter] = None


def get_llm_task_router() -> LLMTaskRouter:
    global _llm_task_router
    if _llm_task_router is None:
        _llm_task_router = LLMTaskRouter()
    return _llm_task_router
