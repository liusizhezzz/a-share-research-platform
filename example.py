"""
OpenBB + Tushare A股数据分析示例
OpenBB Finance 数据开源平台 + Tushare 数据源
"""

from openbb import obb
import tushare as ts
import pandas as pd
import os

# ==================== 配置部分 ====================

# Tushare 配置 - 需要你注册获取 token
# 注册地址: https://tushare.pro/
TUSHARE_TOKEN = os.getenv('TUSHARE_TOKEN', 'YOUR_TUSHARE_TOKEN_HERE')

# 设置 Tushare token
ts.set_token(TUSHARE_TOKEN)
pro = ts.pro_api()

# ==================== OpenBB 基本用法 ====================

def openbb_basic_example():
    """OpenBB 基本示例"""
    print("=" * 60)
    print("OpenBB 基本示例")
    print("=" * 60)

    # 示例 1: 获取股票历史价格
    print("\n1. 获取股票历史价格 (以苹果 AAPL 为例):")
    try:
        output = obb.equity.price.historical("AAPL", start_date="2024-01-01", end_date="2024-01-31")
        df = output.to_dataframe()
        print(df.head())
    except Exception as e:
        print(f"错误: {e}")

    # 示例 2: 获取股票基本信息
    print("\n2. 获取股票基本信息:")
    try:
        output = obb.equity.overview("AAPL")
        df = output.to_dataframe()
        print(df)
    except Exception as e:
        print(f"错误: {e}")

    # 示例 3: 获取财务指标
    print("\n3. 获取财务指标:")
    try:
        output = obb.equity.factset.historical("AAPL")
        df = output.to_dataframe()
        print(df.head())
    except Exception as e:
        print(f"错误: {e}")

    # 示例 4: 技术分析指标
    print("\n4. 技术分析指标 (RSI, MACD等):")
    try:
        output = obb.equity.technical("AAPL", indicators=["rsi", "macd"])
        df = output.to_dataframe()
        print(df.head())
    except Exception as e:
        print(f"错误: {e}")

    # 示例 5: 获取期权链
    print("\n5. 获取期权链:")
    try:
        output = obb.equity.option.chain("AAPL")
        df = output.to_dataframe()
        print(df.head())
    except Exception as e:
        print(f"错误: {e}")

    # 示例 6: 获取新闻
    print("\n6. 获取新闻:")
    try:
        output = obb.news.search("AAPL")
        df = output.to_dataframe()
        print(df.head())
    except Exception as e:
        print(f"错误: {e}")

    # 示例 7: 经济数据
    print("\n7. 获取经济数据:")
    try:
        output = obb.eco.fred.search("GDP")
        df = output.to_dataframe()
        print(df.head())
    except Exception as e:
        print(f"错误: {e}")

# ==================== Tushare A股专用示例 ====================

def tushare_example():
    """Tushare A股专用示例"""
    print("\n" + "=" * 60)
    print("Tushare A股专用示例")
    print("=" * 60)

    # 示例 1: 获取股票列表
    print("\n1. 获取A股股票列表:")
    try:
        df = pro.stock_basic(exchange='', list_status='L', fields='ts_code,symbol,name,area,industry,list_date')
        print(f"总股票数: {len(df)}")
        print(df.head(10))
    except Exception as e:
        print(f"错误: {e}")

    # 示例 2: 获取实时行情
    print("\n2. 获取实时行情 (以平安银行 000001.SZ 为例):")
    try:
        df = pro.daily(ts_code='000001.SZ')
        print(f"获取数据行数: {len(df)}")
        print(df.head())
    except Exception as e:
        print(f"错误: {e}")

    # 示例 3: 获取日线行情
    print("\n3. 获取日线行情 (最近30天):")
    try:
        df = pro.daily(ts_code='000001.SZ', start_date='20240101', end_date='20240131')
        print(f"获取数据行数: {len(df)}")
        print(df.head())
    except Exception as e:
        print(f"错误: {e}")

    # 示例 4: 获取复权行情
    print("\n4. 获取前复权行情:")
    try:
        df = pro.adj_factor(ts_code='000001.SZ', start_date='20240101', end_date='20240131')
        print(f"获取数据行数: {len(df)}")
        print(df.head())
    except Exception as e:
        print(f"错误: {e}")

    # 示例 5: 获取财务数据
    print("\n5. 获取财务指标 (净利润):")
    try:
        df = pro.income(ts_code='000001.SZ', start_date='20230101', end_date='20231231')
        print(f"获取数据行数: {len(df)}")
        print(df.head())
    except Exception as e:
        print(f"错误: {e}")

    # 示例 6: 获取龙虎榜数据
    print("\n6. 获取龙虎榜数据:")
    try:
        df = pro.top_list(concept='', start_date='20240101', end_date='20240131')
        print(f"获取数据行数: {len(df)}")
        print(df.head(10))
    except Exception as e:
        print(f"错误: {e}")

    # 示例 7: 获取行业数据
    print("\n7. 获取申万一级行业数据:")
    try:
        df = pro.index_classify(level='L1', src='SW')
        print(f"获取数据行数: {len(df)}")
        print(df.head())
    except Exception as e:
        print(f"错误: {e}")

    # 示例 8: 获取个股资金流向
    print("\n8. 获取个股资金流向:")
    try:
        df = pro.moneyflow(stock_code='000001.SZ', start_date='20240101', end_date='20240131')
        print(f"获取数据行数: {len(df)}")
        print(df.head())
    except Exception as e:
        print(f"错误: {e}")

# ==================== 综合分析示例 ====================

def comprehensive_analysis():
    """综合分析示例"""
    print("\n" + "=" * 60)
    print("综合分析示例")
    print("=" * 60)

    # 分析几只股票
    stocks = ['000001.SZ', '000002.SZ', '600000.SH']  # 平安银行、万科A、浦发银行

    print(f"\n分析股票: {stocks}")

    # 使用 Tushare 获取数据
    print("\n1. 获取所有股票的日线数据:")
    try:
        all_data = []
        for stock in stocks:
            df = pro.daily(ts_code=stock, start_date='20240101', end_date='20240131')
            if len(df) > 0:
                df['ts_code'] = stock
                all_data.append(df)

        if all_data:
            combined = pd.concat(all_data, ignore_index=True)
            print(f"总数据行数: {len(combined)}")
            print(combined.head(15))
        else:
            print("未获取到数据")
    except Exception as e:
        print(f"错误: {e}")

    # 使用 OpenBB 获取财务数据
    print("\n2. 获取股票基本面数据:")
    for stock in stocks:
        try:
            code = stock.split('.')[0]
            output = obb.equity.overview(code)
            df = output.to_dataframe()
            print(f"\n{stock}:")
            print(df)
        except Exception as e:
            print(f"{stock} 错误: {e}")

# ==================== 主函数 ====================

def main():
    """主函数"""
    print("\n" + "=" * 60)
    print("OpenBB + Tushare A股数据分析系统")
    print("=" * 60)

    # 检查 Tushare token
    if TUSHARE_TOKEN == 'YOUR_TUSHARE_TOKEN_HERE':
        print("\n⚠️  警告: 请设置 TUSHARE_TOKEN 环境变量或修改脚本中的 token")
        print("   注册地址: https://tushare.pro/")
        print("   设置方法:")
        print("   - Windows: set TUSHARE_TOKEN=你的token")
        print("   - Linux/Mac: export TUSHARE_TOKEN=你的token")

    # 运行示例
    openbb_basic_example()
    tushare_example()
    comprehensive_analysis()

    print("\n" + "=" * 60)
    print("示例运行完成！")
    print("=" * 60)

if __name__ == "__main__":
    main()
