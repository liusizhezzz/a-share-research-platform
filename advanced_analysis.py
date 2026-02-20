"""
OpenBB + Tushare 高级分析示例
包含技术分析、量化策略、数据可视化等
"""

from openbb import obb
import tushare as ts
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from datetime import datetime, timedelta
import os

# ==================== 配置 ====================

TUSHARE_TOKEN = os.getenv('TUSHARE_TOKEN', 'YOUR_TUSHARE_TOKEN_HERE')

# 设置 Tushare
ts.set_token(TUSHARE_TOKEN)
pro = ts.pro_api()

# ==================== 数据获取函数 ====================

def get_stock_data(ts_code, start_date, end_date, adjust='qfq'):
    """
    获取股票数据
    :param ts_code: 股票代码 (如 000001.SZ)
    :param start_date: 开始日期 (YYYYMMDD)
    :param end_date: 结束日期 (YYYYMMDD)
    :param adjust: 复权类型 (qfq=前复权, hfq=后复权, qfq=不复权)
    :return: DataFrame
    """
    try:
        df = pro.daily(ts_code=ts_code, start_date=start_date, end_date=end_date)
        if len(df) == 0:
            print(f"未获取到 {ts_code} 的数据")
            return None

        # 添加复权因子
        adj_df = pro.adj_factor(ts_code=ts_code, start_date=start_date, end_date=end_date)
        if len(adj_df) > 0:
            df = df.merge(adj_df, on=['trade_date', 'ts_code'], how='left')
            df['adj_factor'] = df['adj_factor'].fillna(1.0)
            df['close_adj'] = df['close'] * df['adj_factor']

        # 添加技术指标
        df = calculate_technical_indicators(df)
        return df
    except Exception as e:
        print(f"获取 {ts_code} 数据失败: {e}")
        return None

def calculate_technical_indicators(df):
    """计算技术指标"""
    if df is None or len(df) == 0:
        return df

    # 计算移动平均线
    df['ma5'] = df['close_adj'].rolling(window=5).mean()
    df['ma10'] = df['close_adj'].rolling(window=10).mean()
    df['ma20'] = df['close_adj'].rolling(window=20).mean()
    df['ma60'] = df['close_adj'].rolling(window=60).mean()

    # 计算波动率
    df['volatility'] = df['close_adj'].pct_change().rolling(window=20).std()

    # 计算相对强弱指标 (RSI)
    delta = df['close_adj'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    rs = gain / loss
    df['rsi'] = 100 - (100 / (1 + rs))

    # 计算布林带
    df['bb_middle'] = df['ma20']
    df['bb_std'] = df['close_adj'].rolling(window=20).std()
    df['bb_upper'] = df['bb_middle'] + 2 * df['bb_std']
    df['bb_lower'] = df['bb_middle'] - 2 * df['bb_std']

    # 计算MACD
    exp1 = df['close_adj'].ewm(span=12, adjust=False).mean()
    exp2 = df['close_adj'].ewm(span=26, adjust=False).mean()
    df['macd'] = exp1 - exp2
    df['macd_signal'] = df['macd'].ewm(span=9, adjust=False).mean()

    return df

# ==================== 技术分析函数 ====================

def technical_analysis(df, stock_code):
    """技术分析"""
    print(f"\n{'='*60}")
    print(f"{stock_code} 技术分析")
    print(f"{'='*60}")

    if df is None or len(df) < 60:
        print("数据不足，无法进行技术分析")
        return

    latest = df.iloc[-1]
    prev = df.iloc[-2]

    # 价格分析
    print("\n【价格分析】")
    print(f"最新收盘价: {latest['close_adj']:.2f}")
    print(f"MA5: {latest['ma5']:.2f}")
    print(f"MA10: {latest['ma10']:.2f}")
    print(f"MA20: {latest['ma20']:.2f}")
    print(f"MA60: {latest['ma60']:.2f}")

    # 趋势判断
    if latest['close_adj'] > latest['ma20']:
        trend = "上升趋势"
    elif latest['close_adj'] < latest['ma20']:
        trend = "下降趋势"
    else:
        trend = "盘整趋势"
    print(f"当前趋势: {trend}")

    # RI分析
    print(f"\n【RSI分析】")
    print(f"RSI(14): {latest['rsi']:.2f}")
    if latest['rsi'] > 70:
        print("⚠️ RSI超买，可能回调")
    elif latest['rsi'] < 30:
        print("⚠️ RSI超卖，可能反弹")
    else:
        print("RSI在正常区间")

    # MACD分析
    print(f"\n【MACD分析】")
    print(f"MACD: {latest['macd']:.4f}")
    print(f"MACD信号线: {latest['macd_signal']:.4f}")
    if latest['macd'] > latest['macd_signal']:
        print("📈 MACD金叉，买入信号")
    else:
        print("📉 MACD死叉，卖出信号")

    # 布林带分析
    print(f"\n【布林带分析】")
    print(f"上轨: {latest['bb_upper']:.2f}")
    print(f"中轨: {latest['bb_middle']:.2f}")
    print(f"下轨: {latest['bb_lower']:.2f}")
    print(f"当前价格: {latest['close_adj']:.2f}")

    if latest['close_adj'] > latest['bb_upper']:
        print("⚠️ 价格突破上轨，可能超买")
    elif latest['close_adj'] < latest['bb_lower']:
        print("⚠️ 价格跌破下轨，可能超卖")
    else:
        print("价格在布林带内")

# ==================== 可视化函数 ====================

def plot_stock_chart(df, stock_code):
    """绘制股票图表"""
    if df is None or len(df) < 30:
        print("数据不足，无法绘图")
        return

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(14, 10), sharex=True)

    # 主图：价格和均线
    ax1.plot(df.index, df['close_adj'], label='收盘价', color='blue', linewidth=1.5)
    ax1.plot(df.index, df['ma5'], label='MA5', color='orange', linewidth=1)
    ax1.plot(df.index, df['ma10'], label='MA10', color='green', linewidth=1)
    ax1.plot(df.index, df['ma20'], label='MA20', color='red', linewidth=1)
    ax1.plot(df.index, df['bb_upper'], label='BB上轨', color='purple', linestyle='--')
    ax1.plot(df.index, df['bb_lower'], label='BB下轨', color='purple', linestyle='--')
    ax1.fill_between(df.index, df['bb_upper'], df['bb_lower'], alpha=0.1, color='purple')

    ax1.set_title(f'{stock_code} 价格走势', fontsize=14)
    ax1.set_ylabel('价格', fontsize=12)
    ax1.legend(loc='best')
    ax1.grid(True, alpha=0.3)

    # 次图：MACD
    ax2.plot(df.index, df['macd'], label='MACD', color='blue', linewidth=1.5)
    ax2.plot(df.index, df['macd_signal'], label='信号线', color='red', linewidth=1.5)
    ax2.bar(df.index, df['macd'] - df['macd_signal'], label='柱状图', alpha=0.3)

    ax2.set_title('MACD指标', fontsize=12)
    ax2.set_ylabel('MACD', fontsize=12)
    ax2.legend(loc='best')
    ax2.grid(True, alpha=0.3)

    plt.tight_layout()
    plt.savefig(f'{stock_code}_chart.png', dpi=150, bbox_inches='tight')
    print(f"\n图表已保存: {stock_code}_chart.png")
    plt.close()

# ==================== 策略回测函数 ====================

def simple_strategy(df, stock_code):
    """简单策略回测"""
    print(f"\n{'='*60}")
    print(f"{stock_code} 策略回测")
    print(f"{'='*60}")

    if df is None or len(df) < 60:
        print("数据不足，无法回测")
        return

    # 策略：金叉买入，死叉卖出
    buy_signals = []
    sell_signals = []

    for i in range(1, len(df)):
        prev_macd = df['macd'].iloc[i-1]
        prev_signal = df['macd_signal'].iloc[i-1]
        curr_macd = df['macd'].iloc[i]
        curr_signal = df['macd_signal'].iloc[i]

        if prev_macd <= prev_signal and curr_macd > curr_signal:
            buy_signals.append(i)
        elif prev_macd >= prev_signal and curr_macd < curr_signal:
            sell_signals.append(i)

    print(f"买入信号: {len(buy_signals)} 次")
    print(f"卖出信号: {len(sell_signals)} 次")

    if buy_signals:
        last_buy = buy_signals[-1]
        current_price = df['close_adj'].iloc[-1]
        buy_price = df['close_adj'].iloc[last_buy]
        profit = (current_price - buy_price) / buy_price * 100
        print(f"最新买入价格: {buy_price:.2f}")
        print(f"当前价格: {current_price:.2f}")
        print(f"收益率: {profit:.2f}%")

# ==================== 主函数 ====================

def main():
    """主函数"""
    print("\n" + "="*60)
    print("OpenBB + Tushare 高级分析系统")
    print("="*60)

    # 检查 token
    if TUSHARE_TOKEN == 'YOUR_TUSHARE_TOKEN_HERE':
        print("\n⚠️  请设置 TUSHARE_TOKEN")
        return

    # 设置日期
    end_date = datetime.now().strftime('%Y%m%d')
    start_date = (datetime.now() - timedelta(days=90)).strftime('%Y%m%d')

    print(f"\n分析周期: {start_date} - {end_date}")

    # 分析的股票列表
    stocks = ['000001.SZ', '000002.SZ', '600000.SH']

    for stock in stocks:
        print(f"\n正在分析: {stock}")
        print("-" * 60)

        # 获取数据
        df = get_stock_data(stock, start_date, end_date)

        if df is not None and len(df) > 0:
            # 技术分析
            technical_analysis(df, stock)

            # 策略回测
            simple_strategy(df, stock)

            # 绘图
            plot_stock_chart(df, stock)

    print("\n" + "="*60)
    print("分析完成！")
    print("="*60)

if __name__ == "__main__":
    main()
