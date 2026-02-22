"""财务数据路由"""

import logging
from typing import Optional
from fastapi import APIRouter, HTTPException

from app.models.domain.stock import FinancialData
from app.utils.tushare_client import get_tushare_client

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/financial")


@router.get("/data")
async def get_financial_data(stock_code: str) -> dict:
    """获取财务数据

    Args:
        stock_code: 股票代码

    Returns:
        财务数据
    """
    try:
        client = get_tushare_client()

        # 获取财务数据
        data = await client.get_financial_data(stock_code)

        if data is None:
            raise HTTPException(status_code=404, detail="未找到财务数据")

        return {
            "stock_code": stock_code,
            "data": data
        }

    except Exception as e:
        logger.exception(f"获取财务数据失败: {e}")
        raise HTTPException(status_code=500, detail="服务器内部错误")
