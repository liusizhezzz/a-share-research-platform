"""
飞书通知 - 部署完成
"""
import requests
import json
from datetime import datetime

def send_completion_notification():
    """发送部署完成通知"""

    # 构建消息内容
    message = {
        "msg_type": "interactive",
        "card": {
            "header": {
                "title": {
                    "content": "🎉 A股投研平台 - 开发完成",
                    "tag": "plain_text"
                },
                "template": "green"
            },
            "elements": [
                {
                    "tag": "div",
                    "text": {
                        "content": "**项目状态**: ✅ 全部功能已实现\n**部署日期**: 2026-02-20\n**当前版本**: v1.0.0",
                        "tag": "lark_md"
                    }
                },
                {
                    "tag": "hr"
                },
                {
                    "tag": "div",
                    "text": {
                        "content": "**📋 数据层功能**",
                        "tag": "plain_text"
                    }
                },
                {
                    "tag": "div",
                    "text": {
                        "content": "✅ A股实时行情\n✅ 财务数据\n✅ 技术分析指标\n✅ 新闻资讯\n✅ 行业分析\n✅ 龙虎榜数据",
                        "tag": "lark_md"
                    }
                },
                {
                    "tag": "hr"
                },
                {
                    "tag": "div",
                    "text": {
                        "content": "**📊 分析层功能**",
                        "tag": "plain_text"
                    }
                },
                {
                    "tag": "div",
                    "text": {
                        "content": "✅ 自动选股策略\n✅ 风险评估\n✅ 组合分析\n✅ 回测系统\n✅ 量化策略",
                        "tag": "lark_md"
                    }
                },
                {
                    "tag": "hr"
                },
                {
                    "tag": "div",
                    "text": {
                        "content": "**🤖 AI辅助功能**",
                        "tag": "plain_text"
                    }
                },
                {
                    "tag": "div",
                    "text": {
                        "content": "✅ 智能研报生成\n✅ 数据自动解读\n✅ 投资建议\n✅ 问答系统",
                        "tag": "lark_md"
                    }
                },
                {
                    "tag": "hr"
                },
                {
                    "tag": "div",
                    "text": {
                        "content": "**⚙️ 技术栈**\n- Streamlit 1.52.1\n- OpenBB 4.6.0\n- Tushare 1.4.24\n- 智谱AI GLM-4-Flash",
                        "tag": "lark_md"
                    }
                },
                {
                    "tag": "hr"
                },
                {
                    "tag": "div",
                    "text": {
                        "content": "**📁 项目文件**\n- app.py (主应用)\n- requirements.txt (依赖)\n- Dockerfile (容器配置)\n- 部署脚本\n- 完整文档",
                        "tag": "lark_md"
                    }
                },
                {
                    "tag": "hr"
                },
                {
                    "tag": "div",
                    "text": {
                        "content": "**🚀 下一步操作**\n1. 创建GitHub仓库\n2. 推送代码\n3. 部署到云服务器\n4. 配置HTTPS",
                        "tag": "lark_md"
                    }
                },
                {
                    "tag": "hr"
                },
                {
                    "tag": "div",
                    "text": {
                        "content": f"🕐 更新时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
                        "tag": "plain_text"
                    }
                }
            ]
        }
    }

    # 发送消息
    webhook_url = "你的飞书Webhook地址"  # 需要配置

    try:
        response = requests.post(
            webhook_url,
            json=message,
            headers={"Content-Type": "application/json"},
            timeout=10
        )

        if response.status_code == 200:
            print("✅ 飞书通知发送成功")
        else:
            print(f"❌ 飞书通知发送失败: {response.status_code}")
    except Exception as e:
        print(f"❌ 飞书通知异常: {e}")

if __name__ == "__main__":
    send_completion_notification()
