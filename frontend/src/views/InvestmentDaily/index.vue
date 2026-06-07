<template>
  <div class="investment-daily">
    <div class="page-header">
      <div>
        <h1>投资日报</h1>
        <p>开盘前聚合量化信号、新闻、国际变量和公开评论</p>
      </div>
      <div class="header-actions">
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
          <div class="temperature-value">{{ report.market_temperature?.score ?? '-' }}</div>
          <div class="temperature-label">市场温度 {{ report.market_temperature?.label || '-' }}</div>
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
            <el-table :data="report.stocks || []" size="small" class="stock-table">
              <el-table-column prop="code" label="代码" width="92" />
              <el-table-column prop="name" label="名称" min-width="120">
                <template #default="{ row }">
                  <div class="stock-name">{{ row.name }}</div>
                  <div class="stock-source">{{ row.source }}</div>
                </template>
              </el-table-column>
              <el-table-column prop="score" label="综合分" width="86" sortable />
              <el-table-column prop="pct_chg" label="涨跌幅" width="88">
                <template #default="{ row }">
                  <span :class="priceClass(row.pct_chg)">{{ formatPct(row.pct_chg) }}</span>
                </template>
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
                <span class="news-meta">{{ item.source }} · {{ formatTime(item.publish_time) }}</span>
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
              </div>
            </template>
            <div class="news-grid">
              <a
                v-for="item in (report.market_news || []).slice(0, 18)"
                :key="item.title + item.source"
                class="news-card"
                :href="item.url"
                target="_blank"
                rel="noreferrer"
              >
                <div class="news-card-title">{{ item.title }}</div>
                <div class="news-card-meta">
                  <span>{{ item.source }}</span>
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
import { onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import {
  ChatDotRound,
  Connection,
  DataAnalysis,
  Document,
  Link,
  Refresh,
  TrendCharts,
  Warning
} from '@element-plus/icons-vue'
import { investmentDailyApi, type InvestmentDailyReport } from '@/api/investmentDaily'

const loading = ref(false)
const generating = ref(false)
const report = ref<InvestmentDailyReport | null>(null)

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
}
</style>
