"""
飞书机器人配置和通知功能
用于同步平台状态和重要通知
"""

import requests
import os
from datetime import datetime

# 飞书Webhook配置
FEISHU_WEBHOOK = os.getenv('FEISHU_WEBHOOK', '')

def send_feishu_message(message, level="info"):
    """
    发送飞书消息

    Args:
        message (str): 消息内容
        level (str): 消息级别 (info, success, warning, error)
    """
    if not FEISHU_WEBHOOK:
        print(f"[飞书] 未配置Webhook，跳过发送")
        return

    try:
        # 设置消息颜色
        colors = {
            "info": "blue",
            "success": "green",
            "warning": "orange",
            "error": "red"
        }
        color = colors.get(level, "blue")

        # 构建消息内容
        msg_content = {
            "msg_type": "interactive",
            "card": {
                "header": {
                    "title": {
                        "content": f"📊 A股投研平台通知",
                        "tag": "plain_text"
                    },
                    "template": color
                },
                "elements": [
                    {
                        "tag": "div",
                        "text": {
                            "content": message,
                            "tag": "lark_md"
                        }
                    },
                    {
                        "tag": "hr"
                    },
                    {
                        "tag": "div",
                        "text": {
                            "content": f"🕐 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
                            "tag": "plain_text"
                        }
                    }
                ]
            }
        }

        # 发送消息
        response = requests.post(
            FEISHU_WEBHOOK,
            json=msg_content,
            headers={"Content-Type": "application/json"},
            timeout=10
        )

        if response.status_code == 200:
            print(f"[飞书] 消息发送成功")
        else:
            print(f"[飞书] 消息发送失败: {response.status_code}")

    except Exception as e:
        print(f"[飞书] 发送异常: {e}")

def notify_platform_start():
    """通知平台启动"""
    message = """
### 🎉 平台启动成功

✅ A股投研平台已成功启动
✅ 所有服务正常运行
✅ 数据源连接正常

**访问地址**: http://你的域名

---
*系统自动通知*
"""
    send_feishu_message(message, "success")

def notify_platform_stop():
    """通知平台停止"""
    message = """
### ⚠️ 平台停止

⚠️ A股投研平台已停止运行
⚠️ 所有服务已关闭

---
*系统自动通知*
"""
    send_feishu_message(message, "warning")

def notify_api_failure(service, error):
    """通知API失败"""
    message = f"""
### ❌ API调用失败

**服务**: {service}
**错误**: {error}

---
*系统自动通知*
"""
    send_feishu_message(message, "error")

def notify_data_update(stock_code, data_count):
    """通知数据更新"""
    message = f"""
### 📊 数据更新完成

**股票代码**: {stock_code}
**数据量**: {data_count} 条

---
*系统自动通知*
"""
    send_feishu_message(message, "info")

def notify_backtest_complete(strategy, return_rate, max_drawdown):
    """通知回测完成"""
    message = f"""
### 📈 回测完成

**策略**: {strategy}
**收益率**: {return_rate}%
**最大回撤**: {max_drawdown}%

---
*系统自动通知*
"""
    send_feishu_message(message, "success")

if __name__ == "__main__":
    # 测试消息
    send_feishu_message("这是一条测试消息", "info")
