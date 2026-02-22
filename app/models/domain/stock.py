"""股票数据模型定义"""

from pydantic import BaseModel, Field
from typing import Optional


class StockRequest(BaseModel):
    """股票数据请求模型"""
    stock_code: str = Field(..., description="股票代码（如 000001.SZ）")
    days: int = Field(90, description="分析周期（天）", ge=30, le=365)
    indicators: list[str] = Field(
        default=["MA", "MACD", "RSI"],
        description="技术指标列表"
    )
    show_financial: bool = Field(False, description="是否显示财务数据")
    ai_enabled: bool = Field(True, description="是否启用AI分析")
    ai_depth: str = Field("中等", description="AI分析深度")


class TechnicalIndicator(BaseModel):
    """技术指标数据"""
    trade_date: str = Field(..., description="交易日期")
    close: float = Field(..., description="收盘价")
    ma5: Optional[float] = Field(None, description="5日均线")
    ma10: Optional[float] = Field(None, description="10日均线")
    ma20: Optional[float] = Field(None, description="20日均线")
    ma60: Optional[float] = Field(None, description="60日均线")
    rsi: Optional[float] = Field(None, description="RSI指标")
    macd: Optional[float] = Field(None, description="MACD值")
    macd_signal: Optional[float] = Field(None, description="MACD信号线")
    bb_upper: Optional[float] = Field(None, description="布林带上轨")
    bb_middle: Optional[float] = Field(None, description="布林带中轨")
    bb_lower: Optional[float] = Field(None, description="布林带下轨")


class FinancialData(BaseModel):
    """财务数据模型"""
    ts_code: str = Field(..., description="股票代码")
    end_date: str = Field(..., description="报告期")
    assets: Optional[float] = Field(None, description="总资产")
    equity: Optional[float] = Field(None, description="股东权益")
    roe: Optional[float] = Field(None, description="净资产收益率")


class StockAnalysis(BaseModel):
    """股票分析结果"""
    stock_code: str = Field(..., description="股票代码")
    current_price: float = Field(..., description="当前价格")
    change_pct: float = Field(..., description="涨跌幅（%）")
    ma20: float = Field(..., description="MA20")
    rsi: float = Field(..., description="RSI")
    signal: str = Field(..., description="买卖信号")


class AIAnalysis(BaseModel):
    """AI分析结果"""
    content: str = Field(..., description="AI分析内容（Markdown格式）")
