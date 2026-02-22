"""技术指标计算工具"""

import pandas as pd


def calculate_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """计算技术指标

    Args:
        df: 股票数据DataFrame

    Returns:
        添加技术指标的DataFrame
    """
    if df is None or len(df) < 20:
        return df

    # 移动平均线
    df['ma5'] = df['close_adj'].rolling(window=5).mean()
    df['ma10'] = df['close_adj'].rolling(window=10).mean()
    df['ma20'] = df['close_adj'].rolling(window=20).mean()
    df['ma60'] = df['close_adj'].rolling(window=60).mean()

    # RSI (相对强弱指标)
    delta = df['close_adj'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    rs = gain / loss
    df['rsi'] = 100 - (100 / (1 + rs))

    # MACD (指数平滑异同移动平均)
    exp1 = df['close_adj'].ewm(span=12, adjust=False).mean()
    exp2 = df['close_adj'].ewm(span=26, adjust=False).mean()
    df['macd'] = exp1 - exp2
    df['macd_signal'] = df['macd'].ewm(span=9, adjust=False).mean()

    # 布林带
    df['bb_middle'] = df['ma20']
    df['bb_std'] = df['close_adj'].rolling(window=20).std()
    df['bb_upper'] = df['bb_middle'] + 2 * df['bb_std']
    df['bb_lower'] = df['bb_middle'] - 2 * df['bb_std']

    return df
