"""股票数据路由"""

import logging
from typing import Optional
from fastapi import APIRouter, HTTPException
from datetime import datetime, timedelta

from app.models.domain.stock import (
    StockRequest,
    StockAnalysis,
    TechnicalIndicator
)
from app.utils.tushare_client import get_tushare_client
from app.utils.indicators import calculate_indicators

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/stock")


@router.post("/analyze")
async def analyze_stock(request: StockRequest) -> dict:
    """分析股票数据

    Args:
        request: 股票分析请求

    Returns:
        股票分析结果
    """
    try:
        client = get_tushare_client()

        # 计算日期范围
        end_date = datetime.now().strftime('%Y%m%d')
        start_date = (datetime.now() - timedelta(days=request.days)).strftime('%Y%m%d')

        # 获取股票数据
        data = await client.get_daily_data(
            ts_code=request.stock_code,
            start_date=start_date,
            end_date=end_date
        )

        if data is None:
            raise HTTPException(status_code=404, detail="未找到股票数据")

        import pandas as pd
        df = pd.DataFrame(data)

        # 计算技术指标
        df = calculate_indicators(df)

        # 获取最新数据
        latest = df.iloc[-1]
        prev = df.iloc[-2] if len(df) > 1 else latest

        # 计算涨跌幅
        change_pct = (
            (latest['close_adj'] - prev['close_adj'])
            / prev['close_adj'] * 100
        )

        # 生成买卖信号
        signal = _generate_signal(latest)

        return {
            "stock_code": request.stock_code,
            "current_price": float(latest['close_adj']),
            "change_pct": round(change_pct, 2),
            "ma20": float(latest.get('ma20', 0)),
            "rsi": float(latest.get('rsi', 0)),
            "signal": signal,
            "data": df.to_dict('records')
        }

    except ValueError as e:
        logger.error(f"参数错误: {e}")
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        logger.exception(f"分析失败: {e}")
        raise HTTPException(status_code=500, detail="服务器内部错误")


def _generate_signal(latest: dict) -> str:
    """生成买卖信号

    Args:
        latest: 最新股票数据

    Returns:
        信号: BUY/HOLD/SELL
    """
    rsi = latest.get('rsi', 50)
    price = latest.get('close_adj', 0)
    ma20 = latest.get('ma20', 0)

    # RSI 信号
    if rsi > 70:
        return "BUY"  # 超买，可能面临回调
    elif rsi < 30:
        return "SELL"  # 超卖，可能存在反弹
    # 趋势信号
    elif price > ma20:
        return "BUY"  # 站上MA20，上升趋势
    elif price < ma20:
        return "SELL"  # 跌破MA20，下降趋势

    return "HOLD"  # 持有
