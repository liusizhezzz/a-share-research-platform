# 📈 A股投研平台 - 专业版

> 基于 OpenBB + Tushare + 智谱AI 的全功能A股投资研究平台

[![Python](https://img.shields.io/badge/Python-3.9+-blue.svg)](https://www.python.org/)
[![Streamlit](https://img.shields.io/badge/Streamlit-1.52.1-orange.svg)](https://streamlit.io/)
[![License](https://img.shields.io/badge/License-AGPL%203.0-green.svg)](LICENSE)

## ✨ 功能特性

### 📊 数据层（6大功能）

- ✅ **A股实时行情** - 日线、分钟线、复权数据
- ✅ **财务数据** - 资产负债表、利润表、现金流量表
- ✅ **技术分析指标** - MA, MACD, RSI, 布林带、成交量分析
- ✅ **新闻资讯** - 公司新闻、行业新闻、市场动态
- ✅ **行业分析** - 申万一级行业、行业指数
- ✅ **龙虎榜数据** - 机构买卖、游资动向

### 🧮 分析层（5大功能）

- ✅ **自动选股策略** - 多因子选股、量化选股
- ✅ **风险评估** - 波动率、最大回撤、夏普比率
- ✅ **组合分析** - 资产配置、风险分散
- ✅ **回测系统** - 策略回测、绩效评估
- ✅ **量化策略** - 趋势跟踪、均值回归、动量策略

### 🤖 AI辅助（4大功能）

- ✅ **智能研报生成** - 自动生成投资分析报告
- ✅ **数据自动解读** - AI解读技术指标
- ✅ **投资建议** - 买卖点建议、风险提示
- ✅ **问答系统** - 自然语言查询

## 🚀 快速开始

### 环境要求

- Python 3.9 - 3.12
- 2GB+ 内存
- 10GB+ 磁盘空间

### 安装步骤

```bash
# 1. 克隆仓库
git clone https://github.com/你的用户名/a-share-research-platform.git
cd a-share-research-platform

# 2. 安装依赖
pip install -r requirements.txt

# 3. 配置环境变量
cp .env.example .env
# 编辑 .env 文件，填入API密钥

# 4. 启动平台
streamlit run app.py
```

**访问地址**: http://localhost:8501

## ⚙️ 配置说明

### 环境变量 (.env)

```bash
# Tushare配置
TUSHARE_TOKEN=你的Tushare_Token

# 智谱AI配置
ZHIPU_API_KEY=你的智谱AI_API_Key
ZHIPU_MODEL=glm-4-flash

# 飞书机器人（可选）
FEISHU_WEBHOOK=飞书Webhook地址

# 平台配置
PLATFORM_NAME=A股投研平台
DEFAULT_STOCK=000001.SZ
ANALYSIS_DAYS=90
```

### 获取API密钥

1. **Tushare Token**: https://tushare.pro/
2. **智谱AI API Key**: https://open.bigmodel.cn/
3. **飞书Webhook**: 飞书机器人配置

## 📁 项目结构

```
a-share-research-platform/
├── app.py                      # 主应用
├── data_layer/                 # 数据层
│   ├── a_stock_data.py        # A股数据
│   ├── financial_data.py       # 财务数据
│   ├── news_data.py           # 新闻数据
│   └── technical_analysis.py  # 技术分析
├── analysis_layer/             # 分析层
│   ├── stock_selection.py     # 选股策略
│   ├── risk_assessment.py     # 风险评估
│   ├── portfolio_analysis.py  # 组合分析
│   └── backtest.py            # 回测系统
├── ai_layer/                   # AI层
│   ├── report_generator.py    # 研报生成
│   ├── data_interpreter.py    # 数据解读
│   └── investment_advisor.py  # 投资建议
├── feishu_bot.py               # 飞书机器人
├── requirements.txt            # 依赖列表
├── Dockerfile                  # Docker配置
├── docker-compose.yml          # Docker Compose
├── nginx.conf                  # Nginx配置
├── .env.example                # 环境变量示例
├── .streamlit/config.toml      # Streamlit配置
└── README.md                   # 本文档
```

## 🌐 部署方式

### 方式1：本地运行

```bash
streamlit run app.py
```

### 方式2：Docker部署

```bash
# 构建镜像
docker build -t a-share-platform:latest .

# 启动容器
docker run -d -p 8501:8501 --env-file .env a-share-platform:latest
```

### 方式3：云服务器部署

详见 [DEPLOYMENT.md](DEPLOYMENT.md)

## 📊 使用示例

### 1. 股票分析

```
股票代码: 000001.SZ
分析周期: 90天
分析选项: 技术分析、基本面分析、AI分析
```

### 2. 选股策略

```
策略类型: 多因子选股
因子: 市盈率、市净率、ROE、ROA
筛选条件: PE<30, PB<3, ROE>10%
```

### 3. 策略回测

```
策略: 趋势跟踪
周期: 1年
初始资金: 100万
交易成本: 0.3%
```

### 4. AI研报

```
输入: 股票代码 + 分析周期
输出: 技术分析 + 基本面分析 + 投资建议 + 风险提示
```

## 🎯 推荐股票

### 深圳股票 (.SZ)
- `000001.SZ` - 平安银行
- `000002.SZ` - 万科A
- `000858.SZ` - 五粮液
- `002594.SZ` - 比亚迪

### 上海股票 (.SH)
- `600519.SH` - 贵州茅台
- `600036.SH` - 招商银行
- `600900.SH` - 长江电力
- `601318.SH` - 中国平安

## 🔧 高级功能

### 1. 自定义技术指标

编辑 `data_layer/technical_analysis.py`，添加新的指标。

### 2. 自定义选股策略

编辑 `analysis_layer/stock_selection.py`，实现新的策略。

### 3. 自定义AI分析

编辑 `ai_layer/investment_advisor.py`，调整AI分析逻辑。

### 4. 飞书通知

编辑 `feishu_bot.py`，配置Webhook地址。

## 📈 性能优化

- ✅ 数据缓存（Redis）
- ✅ 并发处理
- ✅ 数据压缩
- ✅ 负载均衡

## 🔒 安全建议

- ✅ API密钥加密存储
- ✅ 使用HTTPS
- ✅ 配置防火墙
- ✅ 访问日志记录

## 🐛 常见问题

### Q1: API调用失败？

**A**: 检查API密钥是否正确，网络连接是否正常。

### Q2: 数据获取慢？

**A**: 可以增加缓存时间，使用复权数据。

### Q3: Docker启动失败？

**A**: 检查端口是否被占用，查看Docker日志。

## 📞 技术支持

- **GitHub Issues**: https://github.com/你的用户名/a-share-research-platform/issues
- **Tushare文档**: https://tushare.pro/document/2
- **智谱AI文档**: https://open.bigmodel.cn/
- **OpenBB文档**: https://docs.openbb.co/

## 📝 更新日志

### v1.0.0 (2026-02-20)
- ✅ 初始版本发布
- ✅ 数据层完整实现
- ✅ 分析层完整实现
- ✅ AI层完整实现
- ✅ Docker部署支持
- ✅ 飞书通知支持

## 📄 许可证

本项目采用 AGPL-3.0 许可证。

## 🤝 贡献

欢迎提交Issue和Pull Request！

## 🌟 Star History

如果这个项目对你有帮助，请给个Star ⭐️

---

**开发状态**: ✅ 已完成
**部署状态**: 🚧 待部署
**最后更新**: 2026-02-20
