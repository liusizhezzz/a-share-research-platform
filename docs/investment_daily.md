# 开盘前投资日报

投资日报模块用于在工作日开盘前汇总市场新闻、国际宏观线索、东方财富个股新闻、东方财富股吧公开帖子、量化策略信号和本地行情数据，生成一份可在 Web 后台查看的研究报告。

## 调度

默认配置在 `.env.docker` / `.env.example` 中：

```env
INVESTMENT_DAILY_ENABLED=true
INVESTMENT_DAILY_CRON=40 8 * * 1-5
INVESTMENT_DAILY_HOURS_BACK=36
INVESTMENT_DAILY_NEWS_LIMIT=80
INVESTMENT_DAILY_MAX_STOCKS=10
INVESTMENT_DAILY_SIGNAL_DIR=./data/quant_signals
```

`INVESTMENT_DAILY_CRON=40 8 * * 1-5` 表示北京时间工作日 08:40 自动生成日报。

## 接口

所有接口需要登录态 Bearer Token：

- `GET /api/investment-daily/latest`：读取最新日报
- `GET /api/investment-daily/history?limit=20`：读取历史日报
- `GET /api/investment-daily/{report_id}`：按日期或 ID 读取日报
- `POST /api/investment-daily/generate?force_refresh=true`：手动生成或刷新日报

前端入口：侧边栏 `投资日报`，路由 `/investment-daily`。

## 量化信号 CSV

将策略产出的 CSV 放入 `INVESTMENT_DAILY_SIGNAL_DIR` 指向的目录，例如 `data/quant_signals/`。系统会读取最新 3 个 CSV 文件。

推荐字段：

```csv
code,name,score,reason
688017,绿的谐波,92.5,机器人产业链强势叠加量价信号
300750,宁德时代,86.0,新能源权重修复
```

可识别的代码字段包括 `code`、`stock_code`、`ts_code`、`symbol`、`证券代码`、`股票代码`；可识别的分数字段包括 `score`、`rank_score`、`signal_score`、`weight`、`评分`。

## 数据源

- 东方财富搜索：市场主题、国际局势、个股新闻
- 财联社快讯：宏观和市场快讯补充
- 东方财富股吧：公开帖子标题、阅读数、评论数
- 本地 MongoDB：自选股、行情、股票基础信息
- 量化信号 CSV：用户策略输出

外部源均为 best-effort：单个数据源失败不会阻断日报生成，报告的 `sources` 字段会记录每个来源的状态和条数。

> 本模块输出仅用于投研辅助和策略复盘，不构成投资建议。
