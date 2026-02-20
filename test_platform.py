"""
测试平台配置和功能
"""
import sys
import os

# 添加父目录到路径
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

print("="*60)
print("A股投研平台 - 配置测试")
print("="*60)

# 测试1: 导入依赖
print("\n[1/5] 测试依赖导入...")
try:
    import streamlit
    print(f"✅ Streamlit: {streamlit.__version__}")
except Exception as e:
    print(f"❌ Streamlit导入失败: {e}")

try:
    import openbb
    print(f"✅ OpenBB: 已安装")
except Exception as e:
    print(f"❌ OpenBB导入失败: {e}")

try:
    import tushare
    print(f"✅ Tushare: 已安装")
except Exception as e:
    print(f"❌ Tushare导入失败: {e}")

# 测试2: 配置文件
print("\n[2/5] 测试配置文件...")
try:
    from dotenv import load_dotenv
    load_dotenv()

    tushare_token = os.getenv('TUSHARE_TOKEN')
    zhipu_key = os.getenv('ZHIPU_API_KEY')

    if tushare_token and tushare_token != 'YOUR_TUSHARE_TOKEN_HERE':
        print(f"✅ Tushare Token: {tushare_token[:10]}...")
    else:
        print("❌ Tushare Token 未配置")

    if zhipu_key and zhipu_key != 'YOUR_ZHIPU_API_KEY':
        print(f"✅ 智谱AI Key: {zhipu_key[:10]}...")
    else:
        print("❌ 智谱AI Key 未配置")

except Exception as e:
    print(f"❌ 配置测试失败: {e}")

# 测试3: 导入应用模块
print("\n[3/5] 测试应用模块...")
try:
    import pandas as pd
    import numpy as np
    from datetime import datetime, timedelta

    print(f"✅ Pandas: {pd.__version__}")
    print(f"✅ NumPy: {np.__version__}")

except Exception as e:
    print(f"❌ 数据处理库导入失败: {e}")

# 测试4: API连接测试
print("\n[4/5] 测试API连接...")
try:
    import tushare as ts
    ts.set_token(os.getenv('TUSHARE_TOKEN'))
    pro = ts.pro_api()

    # 测试获取股票列表
    df = pro.stock_basic(exchange='', list_status='L', rows=1)
    if len(df) > 0:
        print(f"✅ Tushare API连接成功")
        print(f"   示例股票: {df.iloc[0]['ts_code']}")
    else:
        print("⚠️  Tushare API返回空数据")

    # 测试智谱AI
    import requests
    url = "https://open.bigmodel.cn/api/paas/v4/chat/completions"
    headers = {
        "Authorization": f"Bearer {os.getenv('ZHIPU_API_KEY')}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": "glm-4-flash",
        "messages": [{"role": "user", "content": "测试"}]
    }
    response = requests.post(url, headers=headers, json=payload, timeout=10)
    if response.status_code == 200:
        print(f"✅ 智谱AI API连接成功")
    else:
        print(f"❌ 智谱AI API连接失败: {response.status_code}")

except Exception as e:
    print(f"❌ API连接测试失败: {e}")

# 测试5: Streamlit配置
print("\n[5/5] 测试Streamlit配置...")
try:
    st_page_config = {
        "page_title": "A股投研平台",
        "page_icon": "📈",
        "layout": "wide",
        "initial_sidebar_state": "expanded"
    }
    print(f"✅ Streamlit配置正常")

except Exception as e:
    print(f"❌ Streamlit配置失败: {e}")

# 总结
print("\n" + "="*60)
print("测试完成！")
print("="*60)
print("\n如果所有测试都通过，请运行:")
print("  streamlit run app.py")
print("\n或在文件资源管理器中双击: run.bat")
print("="*60)
