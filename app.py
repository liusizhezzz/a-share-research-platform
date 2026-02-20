"""
A股投研平台 - OpenBB + Tushare + 智谱AI
完整的A股投资研究平台
"""

import streamlit as st
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from datetime import datetime, timedelta
import os
import sys

# 添加父目录到路径
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from openbb import obb
import tushare as ts
from dotenv import load_dotenv

# 加载环境变量
load_dotenv()

# ==================== 配置 ====================

TUSHARE_TOKEN = os.getenv('TUSHARE_TOKEN')
ZHIPU_API_KEY = os.getenv('ZHIPU_API_KEY')
ZHIPU_MODEL = os.getenv('ZHIPU_MODEL', 'glm-4-flash')

# 设置 Tushare
ts.set_token(TUSHARE_TOKEN)
pro = ts.pro_api()

# ==================== 页面配置 ====================

st.set_page_config(
    page_title="A股投研平台",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded"
)

# 自定义CSS
st.markdown("""
<style>
    .main-header {
        font-size: 2.5rem;
        font-weight: bold;
        color: #1f77b4;
        text-align: center;
        padding: 1rem;
    }
    .metric-card {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        color: white;
        border-radius: 10px;
        padding: 1.5rem;
        text-align: center;
    }
    .chart-container {
        padding: 1rem;
        background: white;
        border-radius: 10px;
        box-shadow: 0 2px 4px rgba(0,0,0,0.1);
    }
</style>
""", unsafe_allow_html=True)

# ==================== 初始化 ====================

if "session_started" not in st.session_state:
    st.session_state.session_started = False

if not st.session_state.session_started:
    st.title("📈 A股投研平台")
    st.markdown("---")
    st.markdown("""
    ## 欢迎使用A股投研平台

    本平台集成以下功能：
    - **数据层**: OpenBB + Tushare（A股实时行情、财务数据）
    - **分析层**: 技术分析、基本面分析
    - **AI层**: 智谱AI智能分析
    - **可视化**: 专业图表展示

    **开始使用请点击下方按钮**
    """)

    if st.button("🚀 开始分析", type="primary", use_container_width=True):
        st.session_state.session_started = True
        st.rerun()

    st.stop()

# ==================== 侧边栏 ====================

with st.sidebar:
    st.markdown("### 📊 分析设置")

    # 股票选择
    stock_code = st.text_input(
        "股票代码 (如 000001.SZ)",
        value=os.getenv('DEFAULT_STOCK', '000001.SZ'),
        help="深圳股票以.SZ结尾，上海股票以.SH结尾"
    )

    # 分析周期
    days = st.slider(
        "分析周期 (天)",
        30, 365,
        int(os.getenv('ANALYSIS_DAYS', '90'))
    )

    # 分析选项
    with st.expander("📈 技术分析选项"):
        indicators = st.multiselect(
            "技术指标",
            ["MA", "MACD", "RSI", "布林带", "成交量"],
            default=["MA", "MACD", "RSI"]
        )

    with st.expander("💰 基本面分析选项"):
        show_financial = st.checkbox("显示财务数据", value=True)

    # AI分析选项
    with st.expander("🤖 AI分析选项"):
        ai_enabled = st.checkbox("启用AI分析", value=True)
        ai_depth = st.select_slider(
            "分析深度",
            options=["简单", "中等", "详细"],
            value="中等"
        )

    st.markdown("---")
    st.markdown("### ⚙️ 系统信息")
    st.info(f"数据源: OpenBB + Tushare")
    st.info(f"AI模型: {ZHIPU_MODEL}")
    st.info(f"Tushare Token: {'✅ 已配置' if TUSHARE_TOKEN else '❌ 未配置'}")

# ==================== 主页面 ====================

st.markdown('<div class="main-header">📈 A股投研平台</div>', unsafe_allow_html=True)

# ==================== 数据获取 ====================

@st.cache_data
def get_stock_data(ts_code, start_date):
    """获取股票数据"""
    try:
        # 获取日线数据
        df = pro.daily(ts_code=ts_code, start_date=start_date)

        if len(df) == 0:
            return None

        # 添加复权因子
        adj_df = pro.adj_factor(ts_code=ts_code, start_date=start_date)
        if len(adj_df) > 0:
            df = df.merge(adj_df, on=['trade_date', 'ts_code'], how='left')
            df['adj_factor'] = df['adj_factor'].fillna(1.0)
            df['close_adj'] = df['close'] * df['adj_factor']
        else:
            df['close_adj'] = df['close']

        # 计算技术指标
        df = calculate_technical_indicators(df)

        return df
    except Exception as e:
        st.error(f"获取数据失败: {e}")
        return None

def calculate_technical_indicators(df):
    """计算技术指标"""
    if df is None or len(df) == 0:
        return df

    # 移动平均线
    df['ma5'] = df['close_adj'].rolling(window=5).mean()
    df['ma10'] = df['close_adj'].rolling(window=10).mean()
    df['ma20'] = df['close_adj'].rolling(window=20).mean()
    df['ma60'] = df['close_adj'].rolling(window=60).mean()

    # RSI
    delta = df['close_adj'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    rs = gain / loss
    df['rsi'] = 100 - (100 / (1 + rs))

    # MACD
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

# 显示加载状态
with st.spinner("正在获取数据..."):
    end_date = datetime.now().strftime('%Y%m%d')
    start_date = (datetime.now() - timedelta(days=days)).strftime('%Y%m%d')

    df = get_stock_data(stock_code, start_date)

if df is not None and len(df) > 0:
    # ==================== 关键指标 ====================

    col1, col2, col3, col4 = st.columns(4)

    latest = df.iloc[-1]
    prev = df.iloc[-2]

    # 价格信息
    change = (latest['close_adj'] - prev['close_adj']) / prev['close_adj'] * 100
    change_color = "🟢" if change >= 0 else "🔴"

    col1.metric("最新价格", f"¥{latest['close_adj']:.2f}")
    col2.metric("涨跌幅", f"{change:.2f}%", change_color)
    col3.metric("MA20", f"¥{latest['ma20']:.2f}")
    col4.metric("RSI", f"{latest['rsi']:.2f}")

    st.markdown("---")

    # ==================== 图表展示 ====================

    st.subheader("📊 价格走势与技术指标")

    chart_cols = st.columns(3)

    # 价格走势
    with chart_cols[0]:
        fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 8), sharex=True)

        ax1.plot(df.index, df['close_adj'], label='收盘价', color='blue', linewidth=1.5)
        ax1.plot(df.index, df['ma5'], label='MA5', color='orange', linewidth=1)
        ax1.plot(df.index, df['ma10'], label='MA10', color='green', linewidth=1)
        ax1.plot(df.index, df['ma20'], label='MA20', color='red', linewidth=1)
        ax1.fill_between(df.index, df['bb_upper'], df['bb_lower'], alpha=0.1, color='purple')

        ax1.set_title(f'{stock_code} 价格走势', fontsize=12)
        ax1.legend(loc='best')
        ax1.grid(True, alpha=0.3)

        ax2.plot(df.index, df['macd'], label='MACD', color='blue', linewidth=1.5)
        ax2.plot(df.index, df['macd_signal'], label='信号线', color='red', linewidth=1.5)
        ax2.bar(df.index, df['macd'] - df['macd_signal'], alpha=0.3)

        ax2.set_title('MACD指标', fontsize=10)
        ax2.legend(loc='best')
        ax2.grid(True, alpha=0.3)

        plt.tight_layout()
        st.pyplot(fig)

    # RSI
    with chart_cols[1]:
        fig, ax = plt.subplots(figsize=(10, 4))
        ax.plot(df.index, df['rsi'], label='RSI', color='purple', linewidth=1.5)
        ax.axhline(y=70, color='red', linestyle='--', alpha=0.5, label='超买线')
        ax.axhline(y=30, color='green', linestyle='--', alpha=0.5, label='超卖线')
        ax.fill_between(df.index, 70, 30, alpha=0.1, color='gray')

        ax.set_title(f'{stock_code} RSI指标', fontsize=12)
        ax.legend(loc='best')
        ax.grid(True, alpha=0.3)

        plt.tight_layout()
        st.pyplot(fig)

    # 成交量
    with chart_cols[2]:
        fig, ax = plt.subplots(figsize=(10, 4))
        ax.bar(df.index, df['vol'], alpha=0.6, color='skyblue')
        ax.plot(df.index, df['ma5'], label='MA5成交量', color='orange', linewidth=1)

        ax.set_title(f'{stock_code} 成交量', fontsize=12)
        ax.legend(loc='best')
        ax.grid(True, alpha=0.3)

        plt.tight_layout()
        st.pyplot(fig)

    st.markdown("---")

    # ==================== 数据表格 ====================

    st.subheader("📋 详细数据")

    data_cols = ['trade_date', 'close_adj', 'ma5', 'ma10', 'ma20', 'ma60', 'rsi', 'macd']
    st.dataframe(df[data_cols].tail(10), use_container_width=True, height=300)

    # ==================== AI分析 ====================

    if ai_enabled:
        st.markdown("---")
        st.subheader("🤖 智谱AI智能分析")

        with st.spinner("正在分析数据..."):
            ai_analysis = analyze_with_zhipu(df, stock_code, change)

        if ai_analysis:
            st.markdown(ai_analysis)

    # ==================== 基本面分析 ====================

    if show_financial:
        st.markdown("---")
        st.subheader("💰 基本面分析")

        with st.spinner("正在获取财务数据..."):
            financial_data = get_financial_data(stock_code)

        if financial_data:
            st.dataframe(financial_data, use_container_width=True)

    # ==================== AI选股建议 ====================

    st.markdown("---")
    st.subheader("🎯 AI选股建议")

    if st.button("生成选股建议", type="primary"):
        with st.spinner("正在分析市场..."):
            stock_recommendations = ai_stock_recommendation()

        if stock_recommendations:
            st.dataframe(stock_recommendations, use_container_width=True)

else:
    st.error(f"未找到股票 {stock_code} 的数据，请检查代码格式")

# ==================== AI函数 ====================

def analyze_with_zhipu(df, stock_code, change):
    """使用智谱AI分析股票"""
    try:
        import requests

        # 构建分析内容
        latest = df.iloc[-1]
        prev = df.iloc[-2]

        analysis_text = f"""
**股票代码**: {stock_code}
**分析日期**: {datetime.now().strftime('%Y-%m-%d')}
**最新价格**: ¥{latest['close_adj']:.2f}
**涨跌幅**: {change:.2f}%
**RSI指标**: {latest['rsi']:.2f}
**MACD**: {latest['macd']:.4f}
**MACD信号线**: {latest['macd_signal']:.4f}

**技术分析要点**:
"""

        # RSI分析
        if latest['rsi'] > 70:
            analysis_text += "- RSI超买，可能面临回调压力\n"
        elif latest['rsi'] < 30:
            analysis_text += "- RSI超卖，可能存在反弹机会\n"
        else:
            analysis_text += "- RSI在正常区间，趋势相对稳定\n"

        # MACD分析
        if latest['macd'] > latest['macd_signal']:
            analysis_text += "- MACD金叉，买入信号\n"
        else:
            analysis_text += "- MACD死叉，卖出信号\n"

        # 价格趋势
        if latest['close_adj'] > latest['ma20']:
            analysis_text += "- 价格站上MA20，上升趋势\n"
        else:
            analysis_text += "- 价格跌破MA20，下降趋势\n"

        # 调用智谱AI
        url = "https://open.bigmodel.cn/api/paas/v4/chat/completions"
        headers = {
            "Authorization": f"Bearer {ZHIPU_API_KEY}",
            "Content-Type": "application/json"
        }

        payload = {
            "model": ZHIPU_MODEL,
            "messages": [
                {
                    "role": "system",
                    "content": "你是一个专业的A股投资分析师，擅长技术分析和基本面分析，提供客观、专业的投资建议。"
                },
                {
                    "role": "user",
                    "content": analysis_text
                }
            ],
            "temperature": 0.7
        }

        response = requests.post(url, headers=headers, json=payload, timeout=30)
        response.raise_for_status()

        result = response.json()
        ai_content = result['choices'][0]['message']['content']

        return f"""
### 📊 技术面分析

{ai_content}
"""

    except Exception as e:
        st.error(f"AI分析失败: {e}")
        return None

def get_financial_data(ts_code):
    """获取财务数据"""
    try:
        # 获取资产负债表
        balance_sheet = pro.balance_sheet(
            ts_code=ts_code,
            start_date=datetime.now().strftime('%Y%m%d'),
            end_date=datetime.now().strftime('%Y%m%d'),
            rows=5
        )

        # 获取利润表
        income_statement = pro.income(
            ts_code=ts_code,
            start_date=datetime.now().strftime('%Y%m%d'),
            end_date=datetime.now().strftime('%Y%m%d'),
            rows=5
        )

        # 合并数据
        if len(balance_sheet) > 0 and len(income_statement) > 0:
            financial_data = pd.concat([balance_sheet, income_statement], ignore_index=True)
            return financial_data
        else:
            return None

    except Exception as e:
        st.error(f"获取财务数据失败: {e}")
        return None

def ai_stock_recommendation():
    """AI选股建议"""
    try:
        import requests

        url = "https://open.bigmodel.cn/api/paas/v4/chat/completions"
        headers = {
            "Authorization": f"Bearer {ZHIPU_API_KEY}",
            "Content-Type": "application/json"
        }

        payload = {
            "model": ZHIPU_MODEL,
            "messages": [
                {
                    "role": "system",
                    "content": "你是一个专业的量化投资分析师，擅长基于技术指标和市场数据提供选股建议。请提供3-5只优质股票代码及其推荐理由。"
                },
                {
                    "role": "user",
                    "content": """
请基于当前A股市场情况，推荐3-5只优质股票，包括：
1. 股票代码
2. 推荐理由
3. 风险提示

格式：
| 股票代码 | 推荐理由 | 风险提示 |
"""
                }
            ],
            "temperature": 0.7
        }

        response = requests.post(url, headers=headers, json=payload, timeout=30)
        response.raise_for_status()

        result = response.json()
        ai_content = result['choices'][0]['message']['content']

        return ai_content

    except Exception as e:
        st.error(f"AI选股失败: {e}")
        return None

# ==================== 主函数 ====================

if __name__ == "__main__":
    app()
