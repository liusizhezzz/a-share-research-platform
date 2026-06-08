<template>
  <div class="investment-daily">
    <div class="page-header">
      <div>
        <h1>投资日报</h1>
        <p>开盘前聚合量化信号、新闻、国际变量和公开评论</p>
      </div>
      <div class="header-actions">
        <el-button v-if="reportId" @click="preanalyzeCandidates" :loading="preanalyzing">
          <el-icon><DataAnalysis /></el-icon>
          并发预分析
        </el-button>
        <el-dropdown v-if="reportId" trigger="click">
          <el-button>
            <el-icon><Download /></el-icon>
            下载
          </el-button>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item @click="downloadReport('pdf')">PDF 报告</el-dropdown-item>
              <el-dropdown-item @click="downloadReport('markdown')">Markdown</el-dropdown-item>
              <el-dropdown-item @click="downloadReport('json')">JSON 数据</el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
        <el-button @click="loadLatest" :loading="loading">
          <el-icon><Refresh /></el-icon>
          刷新
        </el-button>
        <el-button type="primary" @click="generateReport" :loading="generating">
          <el-icon><Document /></el-icon>
          生成今日日报
        </el-button>
      </div>
    </div>

    <el-empty v-if="!loading && !report" description="暂无投资日报">
      <el-button type="primary" @click="generateReport" :loading="generating">立即生成</el-button>
    </el-empty>

    <template v-if="report">
      <div class="summary-band">
        <div class="summary-main">
          <div class="report-date">{{ report.title }}</div>
          <div class="summary-text">{{ report.summary }}</div>
          <div class="meta-row">
            <span>生成时间 {{ formatTime(report.generated_at) }}</span>
            <span>新闻 {{ report.market_temperature?.news_count || 0 }} 条</span>
            <span>候选 {{ report.stocks?.length || 0 }} 只</span>
          </div>
        </div>
        <div class="temperature">
          <el-popover placement="left" width="360" trigger="click">
            <template #reference>
              <button class="temperature-button">
                <div class="temperature-value">{{ report.market_temperature?.score ?? '-' }}</div>
                <div class="temperature-label">市场温度 {{ report.market_temperature?.label || '-' }}</div>
              </button>
            </template>
            <div class="formula-popover">
              <div class="formula-title">市场温度计算</div>
              <div>{{ report.market_temperature?.score_breakdown?.formula || '暂无公式' }}</div>
              <div class="formula-sub">{{ report.market_temperature?.score_breakdown?.normalization_method || '暂无归一化说明' }}</div>
              <pre>{{ stringify(report.market_temperature?.score_breakdown?.input_values) }}</pre>
            </div>
          </el-popover>
        </div>
      </div>

      <el-row :gutter="16" class="section-row">
        <el-col :xs="24" :lg="10">
          <el-card shadow="never" class="panel">
            <template #header>
              <div class="panel-header">
                <span><el-icon><TrendCharts /></el-icon> 方向热度</span>
              </div>
            </template>
            <div v-if="report.directions?.length" class="direction-list">
              <div v-for="item in report.directions" :key="item.name" class="direction-item">
                <div class="direction-top">
                  <strong>{{ item.name }}</strong>
                  <el-tag size="small" type="success">热度 {{ item.heat }}</el-tag>
                </div>
                <el-progress :percentage="Math.min(100, Math.round(item.score))" :show-text="false" />
                <div class="direction-headline">{{ item.headlines?.[0] || '暂无代表标题' }}</div>
              </div>
            </div>
            <el-empty v-else description="暂无方向数据" :image-size="80" />
          </el-card>
        </el-col>

        <el-col :xs="24" :lg="14">
          <el-card shadow="never" class="panel">
            <template #header>
              <div class="panel-header">
                <span><el-icon><DataAnalysis /></el-icon> 股票候选</span>
              </div>
            </template>
            <el-alert
              v-if="report.preanalysis?.mapping?.length"
              class="preanalysis-alert"
              type="success"
              show-icon
              :closable="false"
              :title="`已提交 ${report.preanalysis.mapping.length} 只候选股 TradingAgents 并发分析`"
            />
            <el-table
              :data="report.stocks || []"
              size="small"
              class="stock-table"
              highlight-current-row
              @row-click="openStock"
            >
              <el-table-column prop="code" label="代码" width="92" />
              <el-table-column prop="name" label="名称" min-width="120">
                <template #default="{ row }">
                  <div class="stock-name">{{ row.name }}</div>
                  <div class="stock-source">{{ row.prediction_horizon || row.source }}</div>
                </template>
              </el-table-column>
              <el-table-column prop="score" label="预测分" width="92" sortable>
                <template #default="{ row }">
                  <el-popover placement="left" width="390" trigger="click">
                    <template #reference>
                      <el-tag class="score-tag" effect="plain">{{ Number(row.score || 0).toFixed(1) }}</el-tag>
                    </template>
                    <div class="formula-popover">
                      <div class="formula-title">{{ row.name }} 预测分</div>
                      <div>{{ row.score_breakdown?.formula || '暂无公式' }}</div>
                      <div class="formula-sub">{{ row.score_breakdown?.normalization_method || '暂无归一化说明' }}</div>
                      <pre>{{ stringify(row.score_breakdown?.input_values) }}</pre>
                    </div>
                  </el-popover>
                </template>
              </el-table-column>
              <el-table-column prop="pct_chg" label="涨跌幅" width="88">
                <template #default="{ row }">
                  <span :class="priceClass(row.pct_chg)">{{ formatPct(row.pct_chg) }}</span>
                </template>
              </el-table-column>
              <el-table-column prop="price_in_penalty" label="Price-in" width="92">
                <template #default="{ row }">{{ Number(row.price_in_penalty || 0).toFixed(1) }}</template>
              </el-table-column>
              <el-table-column prop="industry" label="行业" width="110" />
              <el-table-column label="线索" min-width="180">
                <template #default="{ row }">
                  <div class="clue">{{ row.reason }}</div>
                  <div v-if="row.headlines?.length" class="sub-clue">{{ row.headlines[0] }}</div>
                </template>
              </el-table-column>
            </el-table>
          </el-card>
        </el-col>
      </el-row>

      <el-row :gutter="16" class="section-row">
        <el-col :xs="24">
          <el-card shadow="never" class="panel">
            <template #header>
              <div class="panel-header">
                <span><el-icon><Connection /></el-icon> 新闻事件簇</span>
              </div>
            </template>
            <div v-if="report.event_clusters?.length" class="cluster-list">
              <div v-for="cluster in report.event_clusters.slice(0, 8)" :key="cluster.cluster_id" class="cluster-item">
                <div class="cluster-title">{{ cluster.title }}</div>
                <div class="cluster-meta">
                  <span>{{ cluster.item_count || cluster.items?.length || 0 }} 条</span>
                  <span>{{ (cluster.sources || []).join(' / ') || '多源' }}</span>
                  <span>{{ formatTime(cluster.last_published_at) }}</span>
                </div>
                <div class="cluster-tags">
                  <el-tag v-for="theme in cluster.themes || []" :key="theme" size="small" effect="plain">{{ theme }}</el-tag>
                  <el-tag v-for="symbol in cluster.symbols || []" :key="symbol" size="small" type="success" effect="plain">{{ symbol }}</el-tag>
                </div>
              </div>
            </div>
            <el-empty v-else description="暂无聚合事件" :image-size="80" />
          </el-card>
        </el-col>
      </el-row>

      <el-row :gutter="16" class="section-row">
        <el-col :xs="24" :lg="12">
          <el-card shadow="never" class="panel">
            <template #header>
              <div class="panel-header">
                <span><el-icon><Connection /></el-icon> 国际与宏观</span>
              </div>
            </template>
            <div class="news-list">
              <a
                v-for="item in (report.international_news || []).slice(0, 10)"
                :key="item.title"
                class="news-item"
                :href="item.url"
                target="_blank"
                rel="noreferrer"
              >
                <span class="news-title">{{ item.title }}</span>
                <span class="news-meta">{{ sourceLabel(item.source) }} · {{ newsTimeLabel(item) }}</span>
              </a>
            </div>
          </el-card>
        </el-col>

        <el-col :xs="24" :lg="12">
          <el-card shadow="never" class="panel">
            <template #header>
              <div class="panel-header">
                <span><el-icon><ChatDotRound /></el-icon> 民众评论</span>
              </div>
            </template>
            <div class="comment-list">
              <a
                v-for="item in (report.social_comments || []).slice(0, 10)"
                :key="item.content + item.symbol"
                class="comment-item"
                :href="item.url"
                target="_blank"
                rel="noreferrer"
              >
                <el-tag size="small">{{ item.symbol || '市场' }}</el-tag>
                <span>{{ item.content }}</span>
              </a>
            </div>
          </el-card>
        </el-col>
      </el-row>

      <el-row :gutter="16" class="section-row">
        <el-col :xs="24" :lg="16">
          <el-card shadow="never" class="panel">
            <template #header>
              <div class="panel-header">
                <span><el-icon><Link /></el-icon> 市场新闻</span>
                <el-select v-model="newsOrder" size="small" style="width: 128px">
                  <el-option label="新到旧" value="desc" />
                  <el-option label="旧到新" value="asc" />
                </el-select>
              </div>
            </template>
            <div class="news-grid">
              <a
                v-for="item in sortedMarketNews.slice(0, 18)"
                :key="item.title + item.source"
                class="news-card"
                :href="item.url"
                target="_blank"
                rel="noreferrer"
              >
                <div class="news-card-title">{{ item.title }}</div>
                <div class="news-card-meta">
                  <span>{{ sourceLabel(item.source) }}</span>
                  <span class="time-label">{{ newsTimeLabel(item) }}</span>
                  <el-tag size="small" :type="sentimentTag(item.sentiment)">{{ sentimentText(item.sentiment) }}</el-tag>
                </div>
              </a>
            </div>
          </el-card>
        </el-col>

        <el-col :xs="24" :lg="8">
          <el-card shadow="never" class="panel">
            <template #header>
              <div class="panel-header">
                <span><el-icon><Warning /></el-icon> 风险与源状态</span>
              </div>
            </template>
            <div class="risk-list">
              <div v-for="item in report.risk_warnings || []" :key="item" class="risk-item">{{ item }}</div>
            </div>
            <el-divider />
            <div class="source-list">
              <div v-for="item in report.sources || []" :key="item.name" class="source-item">
                <span>{{ item.name }}</span>
                <el-tag size="small" :type="item.ok ? 'success' : 'warning'">
                  {{ item.ok ? `${item.count} 条` : '未命中' }}
                </el-tag>
              </div>
            </div>
          </el-card>
        </el-col>
      </el-row>
    </template>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import {
  ChatDotRound,
  Connection,
  DataAnalysis,
  Document,
  Download,
  Link,
  Refresh,
  TrendCharts,
  Warning
} from '@element-plus/icons-vue'
import { investmentDailyApi, type DailyNewsItem, type InvestmentDailyReport } from '@/api/investmentDaily'

const router = useRouter()
const loading = ref(false)
const generating = ref(false)
const preanalyzing = ref(false)
const newsOrder = ref<'desc' | 'asc'>('desc')
const report = ref<InvestmentDailyReport | null>(null)

const reportId = computed(() => String(report.value?._id || ''))

const sortedMarketNews = computed(() => {
  const items = [...(report.value?.market_news || [])]
  const direction = newsOrder.value === 'asc' ? 1 : -1
  return items.sort((a, b) => {
    const left = new Date(newsTimestamp(a) || 0).getTime() || 0
    const right = new Date(newsTimestamp(b) || 0).getTime() || 0
    return (left - right) * direction
  })
})

const loadLatest = async () => {
  loading.value = true
  try {
    const response = await investmentDailyApi.getLatest()
    report.value = response.data || null
  } catch (error) {
    console.error('加载投资日报失败:', error)
  } finally {
    loading.value = false
  }
}

const generateReport = async () => {
  generating.value = true
  try {
    const response = await investmentDailyApi.generate(true)
    report.value = response.data
    ElMessage.success('投资日报已生成')
  } catch (error) {
    console.error('生成投资日报失败:', error)
  } finally {
    generating.value = false
  }
}

const downloadReport = async (format: 'pdf' | 'markdown' | 'json') => {
  if (!reportId.value) return
  try {
    await investmentDailyApi.download(reportId.value, format)
  } catch (error) {
    console.error('下载日报失败:', error)
    ElMessage.error('下载日报失败')
  }
}

const preanalyzeCandidates = async () => {
  if (!reportId.value) return
  preanalyzing.value = true
  try {
    const response = await investmentDailyApi.preanalyze(reportId.value, 8)
    report.value = {
      ...(report.value as InvestmentDailyReport),
      preanalysis: {
        submitted_at: new Date().toISOString(),
        task_ids: response.data.task_ids,
        mapping: response.data.mapping
      }
    }
    ElMessage.success(`已提交 ${response.data.count || 0} 只候选股并发分析`)
  } catch (error) {
    console.error('提交候选股预分析失败:', error)
    ElMessage.error('提交候选股预分析失败')
  } finally {
    preanalyzing.value = false
  }
}

const openStock = (row: { code?: string }) => {
  if (!row?.code) return
  router.push({ name: 'StockDetail', params: { code: row.code } })
}

const stringify = (value?: Record<string, any>) => {
  if (!value) return '{}'
  try {
    return JSON.stringify(value, null, 2)
  } catch {
    return String(value)
  }
}

const formatTime = (value?: string) => {
  if (!value) return '-'
  try {
    return new Date(value).toLocaleString('zh-CN', {
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit'
    })
  } catch {
    return value
  }
}

const technicalSources = new Set(['database', 'realtime', 'none', 'mongodb', 'cache_or_api'])

const sourceLabel = (source?: string) => {
  const value = String(source || '').trim()
  if (!value || technicalSources.has(value.toLowerCase())) return '未知来源'
  return value
}

const newsTimestamp = (item: DailyNewsItem) => {
  return item.publish_time || item.first_seen_at || item.ingested_at || ''
}

const newsTimeLabel = (item: DailyNewsItem) => {
  const formatted = formatTime(newsTimestamp(item))
  if (formatted === '-') return '-'
  if (item.published_at_quality === 'ingest_fallback') return `首次收录 ${formatted}`
  if (item.published_at_quality === 'estimated_from_url_or_title') return `估 ${formatted}`
  return formatted
}

const formatPct = (value?: number) => {
  const num = Number(value || 0)
  return `${num > 0 ? '+' : ''}${num.toFixed(2)}%`
}

const priceClass = (value?: number) => {
  const num = Number(value || 0)
  return num > 0 ? 'price-up' : num < 0 ? 'price-down' : ''
}

const sentimentTag = (sentiment?: string) => {
  if (sentiment === 'positive') return 'success'
  if (sentiment === 'negative') return 'danger'
  return 'info'
}

const sentimentText = (sentiment?: string) => {
  if (sentiment === 'positive') return '积极'
  if (sentiment === 'negative') return '谨慎'
  return '中性'
}

onMounted(loadLatest)
</script>

<style scoped lang="scss">
.investment-daily {
  padding: 24px;
}

.page-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 16px;
  margin-bottom: 20px;

  h1 {
    margin: 0;
    font-size: 24px;
    font-weight: 650;
  }

  p {
    margin: 6px 0 0;
    color: var(--el-text-color-secondary);
  }
}

.header-actions {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
  justify-content: flex-end;
}

.summary-band {
  display: grid;
  grid-template-columns: 1fr 160px;
  gap: 16px;
  align-items: stretch;
  padding: 18px 20px;
  margin-bottom: 16px;
  background: var(--el-fill-color-blank);
  border: 1px solid var(--el-border-color-light);
  border-radius: 8px;
}

.report-date {
  font-size: 18px;
  font-weight: 650;
  margin-bottom: 8px;
}

.summary-text {
  font-size: 15px;
  line-height: 1.7;
  color: var(--el-text-color-primary);
}

.meta-row {
  display: flex;
  gap: 16px;
  flex-wrap: wrap;
  margin-top: 12px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
}

.temperature {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  border-left: 1px solid var(--el-border-color-lighter);
}

.temperature-button {
  display: grid;
  place-items: center;
  width: 100%;
  border: none;
  background: transparent;
  cursor: pointer;
}

.temperature-value {
  font-size: 34px;
  font-weight: 700;
  color: var(--el-color-primary);
}

.temperature-label {
  color: var(--el-text-color-secondary);
  font-size: 13px;
}

.section-row {
  margin-top: 16px;
}

.panel {
  height: 100%;
  border-radius: 8px;
}

.panel-header {
  display: flex;
  align-items: center;
  justify-content: space-between;

  span {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    font-weight: 600;
  }
}

.direction-list {
  display: grid;
  gap: 14px;
}

.direction-item {
  padding-bottom: 12px;
  border-bottom: 1px solid var(--el-border-color-lighter);

  &:last-child {
    border-bottom: none;
    padding-bottom: 0;
  }
}

.direction-top {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
  margin-bottom: 8px;
}

.direction-headline,
.sub-clue,
.stock-source,
.news-meta {
  margin-top: 4px;
  color: var(--el-text-color-secondary);
  font-size: 12px;
  line-height: 1.5;
}

.stock-name {
  font-weight: 600;
}

.stock-table {
  cursor: pointer;
}

.preanalysis-alert {
  margin-bottom: 10px;
}

.score-tag {
  cursor: help;
}

.clue {
  line-height: 1.5;
}

.price-up {
  color: #d03050;
}

.price-down {
  color: #0a8f5a;
}

.news-list,
.comment-list,
.risk-list,
.source-list {
  display: grid;
  gap: 10px;
}

.news-item,
.comment-item {
  display: grid;
  gap: 4px;
  color: inherit;
  text-decoration: none;
  padding-bottom: 10px;
  border-bottom: 1px solid var(--el-border-color-lighter);

  &:last-child {
    border-bottom: none;
    padding-bottom: 0;
  }
}

.comment-item {
  grid-template-columns: auto 1fr;
  align-items: start;
}

.news-title {
  font-weight: 500;
  line-height: 1.5;
}

.news-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 10px;
}

.news-card {
  display: grid;
  gap: 10px;
  padding: 12px;
  color: inherit;
  text-decoration: none;
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 8px;
  min-height: 96px;
}

.news-card-title {
  line-height: 1.5;
  font-weight: 500;
}

.news-card-meta,
.source-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  color: var(--el-text-color-secondary);
  font-size: 12px;
}

.risk-item {
  padding: 10px 12px;
  background: var(--el-fill-color-light);
  border-radius: 8px;
  line-height: 1.6;
}

.cluster-list {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
}

.cluster-item {
  padding: 12px;
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 8px;
  background: var(--el-fill-color-light);
}

.cluster-title {
  font-weight: 650;
  line-height: 1.5;
}

.cluster-meta {
  display: flex;
  gap: 10px;
  flex-wrap: wrap;
  margin-top: 6px;
  color: var(--el-text-color-secondary);
  font-size: 12px;
}

.cluster-tags {
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
  margin-top: 10px;
}

.formula-popover {
  color: var(--el-text-color-primary);
  line-height: 1.6;

  pre {
    max-height: 220px;
    overflow: auto;
    padding: 10px;
    margin: 10px 0 0;
    border-radius: 8px;
    background: var(--el-fill-color-light);
    font-size: 12px;
  }
}

.formula-title {
  margin-bottom: 6px;
  font-weight: 700;
}

.formula-sub {
  margin-top: 6px;
  color: var(--el-text-color-secondary);
  font-size: 12px;
}

@media (max-width: 900px) {
  .investment-daily {
    padding: 16px;
  }

  .page-header,
  .summary-band {
    grid-template-columns: 1fr;
  }

  .page-header {
    display: grid;
  }

  .temperature {
    border-left: none;
    border-top: 1px solid var(--el-border-color-lighter);
    padding-top: 12px;
  }

  .news-grid {
    grid-template-columns: 1fr;
  }

  .cluster-list {
    grid-template-columns: 1fr;
  }
}
</style>
