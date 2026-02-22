"""Tushare 数据获取客户端"""

import logging
from typing import Optional
import tushare as ts
from datetime import datetime

logger = logging.getLogger(__name__)


class TushareClient:
    """Tushare 客户端封装"""

    def __init__(self, token: str):
        """初始化 Tushare 客户端

        Args:
            token: Tushare API Token
        """
        ts.set_token(token)
        self.pro = ts.pro_api()

    async def get_daily_data(
        self,
        ts_code: str,
        start_date: str,
        end_date: str = None
    ) -> Optional[dict]:
        """获取日线数据

        Args:
            ts_code: 股票代码
            start_date: 开始日期（YYYYMMDD格式）
            end_date: 结束日期（可选）

        Returns:
            股票数据字典，失败返回None
        """
        try:
            df = self.pro.daily(
                ts_code=ts_code,
                start_date=start_date,
                end_date=end_date
            )

            if df is None or len(df) == 0:
                logger.warning(f"未获取到股票 {ts_code} 的数据")
                return None

            # 获取复权因子
            adj_df = self.pro.adj_factor(
                ts_code=ts_code,
                start_date=start_date,
                end_date=end_date
            )

            # 添加复权因子
            if len(adj_df) > 0:
                df = df.merge(
                    adj_df,
                    on=['trade_date', 'ts_code'],
                    how='left'
                )
                df['adj_factor'] = df['adj_factor'].fillna(1.0)
                df['close_adj'] = df['close'] * df['adj_factor']
            else:
                df['close_adj'] = df['close']

            return df.to_dict('records')

        except Exception as e:
            logger.error(f"获取日线数据失败: {e}")
            return None

    async def get_financial_data(
        self,
        ts_code: str
    ) -> Optional[dict]:
        """获取财务数据

        Args:
            ts_code: 股票代码

        Returns:
            财务数据字典，失败返回None
        """
        try:
            end_date = datetime.now().strftime('%Y%m%d')

            # 获取资产负债表
            balance_sheet = self.pro.balance_sheet(
                ts_code=ts_code,
                start_date=end_date,
                end_date=end_date,
                rows=5
            )

            # 获取利润表
            income_statement = self.pro.income(
                ts_code=ts_code,
                start_date=end_date,
                end_date=end_date,
                rows=5
            )

            if balance_sheet is None or len(balance_sheet) == 0:
                return None

            if income_statement is None or len(income_statement) == 0:
                return None

            # 合并数据
            import pandas as pd
            financial_df = pd.concat(
                [balance_sheet, income_statement],
                ignore_index=True
            )

            return financial_df.to_dict('records')

        except Exception as e:
            logger.error(f"获取财务数据失败: {e}")
            return None


# 全局客户端实例（从环境变量初始化）
_tushare_client: Optional[TushareClient] = None


def get_tushare_client() -> TushareClient:
    """获取全局 Tushare 客户端实例"""
    global _tushare_client

    if _tushare_client is None:
        import os
        token = os.getenv('TUSHARE_TOKEN')
        if not token:
            raise ValueError("TUSHARE_TOKEN 环境变量未设置")

        _tushare_client = TushareClient(token)

    return _tushare_client
