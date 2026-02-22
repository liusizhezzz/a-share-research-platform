"""AI 分析路由"""

import logging
import os
from typing import Optional
from fastapi import APIRouter, HTTPException
import httpx

from app.models.domain.stock import AIAnalysis

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/ai")


async def _call_zhipu_api(
    content: str,
    temperature: float = 0.7
) -> Optional[str]:
    """调用智谱 AI API

    Args:
        content: 分析内容
        temperature: 温度参数

    Returns:
        AI 响应内容，失败返回 None
    """
    try:
        api_key = os.getenv('ZHIPU_API_KEY')
        if not api_key:
            logger.warning("ZHIPU_API_KEY 未设置")
            return None

        model = os.getenv('ZHIPU_MODEL', 'glm-4-flash')

        url = "https://open.bigmodel.cn/api/paas/v4/chat/completions"
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }

        payload = {
            "model": model,
            "messages": [
                {
                    "role": "system",
                    "content": "你是一个专业的A股投资分析师，擅长技术分析和基本面分析，提供客观、专业的投资建议。"
                },
                {
                    "role": "user",
                    "content": content
                }
            ],
            "temperature": temperature
        }

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(url, headers=headers, json=payload)
            response.raise_for_status()

            result = response.json()
            ai_content = result['choices'][0]['message']['content']
            return ai_content

    except httpx.HTTPError as e:
        logger.error(f"智谱 API 调用失败: {e}")
        return None
    except Exception as e:
        logger.exception(f"AI 分析失败: {e}")
        return None


@router.post("/analyze")
async def analyze_with_ai(content: str) -> dict:
    """AI 技术分析

    Args:
        content: 分析内容

    Returns:
        AI 分析结果（Markdown 格式）
    """
    ai_content = await _call_zhipu_api(content)

    if ai_content is None:
        raise HTTPException(status_code=502, detail="AI 分析服务不可用")

    return {
        "type": "technical",
        "content": ai_content
    }


@router.post("/stock-recommendation")
async def get_stock_recommendation() -> dict:
    """AI 选股建议

    Returns:
        AI 选股推荐结果
    """
    prompt = """请基于当前A股市场情况，推荐3-5只优质股票，包括：
1. 股票代码
2. 推荐理由
3. 风险提示

格式：
| 股票代码 | 推荐理由 | 风险提示 |
"""

    ai_content = await _call_zhipu_api(prompt)

    if ai_content is None:
        raise HTTPException(status_code=502, detail="AI 分析服务不可用")

    # 解析 AI 返回的表格
    lines = ai_content.strip().split('\n')
    recommendations = []

    for line in lines:
        if '|' in line:
            parts = [p.strip() for p in line.split('|')]
            if len(parts) >= 4:
                recommendations.append({
                    "code": parts[1].strip(),
                    "reason": parts[2].strip(),
                    "risk": parts[3].strip()
                })

    return {
        "type": "recommendation",
        "content": ai_content,
        "recommendations": recommendations
    }
