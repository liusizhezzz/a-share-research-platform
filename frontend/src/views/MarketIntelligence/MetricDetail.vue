<template>
  <div class="metric-detail">
    <div class="detail-header">
      <el-button class="back-button" text @click="goBack">
        <el-icon><ArrowLeft /></el-icon>
        返回市场情报
      </el-button>
      <div class="header-copy">
        <p class="eyebrow">市场情报指标解析</p>
        <h1>{{ metricView.title }}</h1>
        <p>{{ metricView.subtitle }}</p>
      </div>
      <div class="header-reading" :class="metricView.tone">
        <span>当前读数</span>
        <strong>{{ metricView.value }}</strong>
        <small>{{ metricView.status }}</small>
      </div>
    </div>

    <el-skeleton v-if="loading" class="loading-shell" :rows="10" animated />
    <el-empty v-else-if="!dashboard" description="暂无可解析的市场情报数据">
      <el-button type="primary" @click="loadData">重新加载</el-button>
    </el-empty>

    <template v-else>
      <div class="metric-tabs">
        <button
          v-for="item in metricTabs"
          :key="item.key"
          :class="{ active: item.key === metricKey }"
          @click="openMetric(item.key)"
        >
          <el-icon><component :is="item.icon" /></el-icon>
          {{ item.label }}
        </button>
      </div>

      <div class="overview-grid">
        <section class="panel reading-panel">
          <div class="section-header">
            <span><el-icon><TrendCharts /></el-icon>当前读数</span>
            <el-tag :type="metricView.tagType" effect="plain">{{ metricView.badge }}</el-tag>
          </div>
          <div class="meter">
            <el-progress
              type="dashboard"
              :percentage="metricView.progress"
              :stroke-width="12"
              :color="metricView.progressColor"
            >
              <template #default>
                <span class="meter-value">{{ metricView.value }}</span>
              </template>
            </el-progress>
          </div>
          <p class="metric-summary">{{ metricView.interpretation }}</p>
          <div class="freshness-row">
            <span>最近抓取 {{ formatTime(dashboard.last_ingested_at) }}</span>
            <span>最近报告 {{ formatTime(dashboard.last_report_generated_at) }}</span>
          </div>
        </section>

        <section class="panel formula-panel">
          <div class="section-header">
            <span><el-icon><DataAnalysis /></el-icon>计算口径</span>
          </div>
          <div class="formula-box">{{ metricView.formula }}</div>
          <div class="normalization">{{ metricView.normalization }}</div>
          <div class="input-grid">
            <div v-for="item in metricView.inputs" :key="item.label" class="input-item">
              <span>{{ item.label }}</span>
              <strong>{{ item.value }}</strong>
            </div>
          </div>
        </section>
      </div>

      <div class="content-grid">
        <section class="panel">
          <div class="section-header">
            <span><el-icon><Connection /></el-icon>分项拆解</span>
          </div>
          <div class="breakdown-list">
            <div v-for="row in metricView.breakdown" :key="row.label" class="breakdown-row">
              <div class="breakdown-main">
                <strong>{{ row.label }}</strong>
                <span>{{ row.description }}</span>
              </div>
              <div class="breakdown-score">
                <b>{{ row.value }}</b>
                <el-progress
                  :percentage="scoreToProgress(row.score)"
                  :stroke-width="8"
                  :show-text="false"
                  :color="row.color || metricView.progressColor"
                />
              </div>
            </div>
          </div>
        </section>

        <section class="panel action-panel">
          <div class="section-header">
            <span><el-icon><Bell /></el-icon>投研含义</span>
          </div>
          <div class="action-list">
            <div v-for="action in metricView.actions" :key="action.title" class="action-item">
              <strong>{{ action.title }}</strong>
              <span>{{ action.description }}</span>
            </div>
          </div>
        </section>
      </div>

      <section class="panel evidence-panel">
        <div class="section-header">
          <span><el-icon><Document /></el-icon>输入证据</span>
          <el-tag effect="plain">{{ evidenceItems.length }} 条重点证据</el-tag>
        </div>
        <div class="evidence-grid">
          <button
            v-for="item in evidenceItems"
            :key="item.id"
            class="evidence-card"
            @click="openEvidence(item)"
          >
            <span class="evidence-type">{{ item.type }}</span>
            <strong>{{ item.title }}</strong>
            <span class="evidence-meta">{{ item.meta }}</span>
            <span class="evidence-desc">{{ item.description }}</span>
            <span v-if="item.tags?.length" class="evidence-tags">
              <el-tag v-for="tag in item.tags.slice(0, 4)" :key="tag" size="small" effect="plain">
                {{ tag }}
              </el-tag>
            </span>
          </button>
        </div>
      </section>

      <section v-if="metricKey === 'automation'" class="panel schedule-panel">
        <div class="section-header">
          <span><el-icon><Clock /></el-icon>自动化任务表</span>
          <el-tag effect="plain">生产监控</el-tag>
        </div>
        <div class="schedule-grid">
          <div v-for="job in automationSchedule" :key="job.name" class="schedule-item">
            <strong>{{ job.time }}</strong>
            <span>{{ job.name }}</span>
            <small>{{ job.description }}</small>
          </div>
        </div>
      </section>
    </template>
  </div>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import {
  ArrowLeft,
  Bell,
  Clock,
  Connection,
  DataAnalysis,
  Document,
  Timer,
  TrendCharts,
  WarningFilled
} from '@element-plus/icons-vue'
import {
  marketIntelligenceApi,
  type GlobalEvent,
  type MarketIntelligenceDashboard
} from '@/api/marketIntelligence'

type MetricKey = 'temperature' | 'risk' | 'coverage' | 'automation'
type TagType = 'success' | 'warning' | 'danger' | 'info' | 'primary'

interface BreakdownRow {
  label: string
  value: string
  description: string
  score: number
  color?: string
}

interface MetricInput {
  label: string
  value: string
}

interface ActionItem {
  title: string
  description: string
}

interface EvidenceItem {
  id: string
  type: string
  title: string
  meta: string
  description: string
  tags?: string[]
  route?: Record<string, any>
}

interface MetricView {
  title: string
  subtitle: string
  value: string
  status: string
  badge: string
  tagType: TagType
  tone: string
  progress: number
  progressColor: string
  interpretation: string
  formula: string
  normalization: string
  inputs: MetricInput[]
  breakdown: BreakdownRow[]
  actions: ActionItem[]
}

const route = useRoute()
const router = useRouter()
const loading = ref(false)
const dashboard = ref<MarketIntelligenceDashboard | null>(null)
const methodology = ref<Record<string, any> | null>(null)
let refreshTimer: number | undefined

const metricTabs: Array<{ key: MetricKey; label: string; icon: any }> = [
  { key: 'temperature', label: '市场温度', icon: TrendCharts },
  { key: 'risk', label: '全球风险', icon: WarningFilled },
  { key: 'coverage', label: '数据覆盖', icon: Connection },
  { key: 'automation', label: '自动化', icon: Timer }
]

const metricKey = computed<MetricKey>(() => {
  const value = String(route.params.metric || '')
  return metricTabs.some((item) => item.key === value) ? (value as MetricKey) : 'temperature'
})

const hours = computed(() => {
  const value = Number(route.query.hours || 168)
  return Number.isFinite(value) && value > 0 ? value : 168
})

const themes = computed(() => dashboard.value?.theme_heatmap_nodes || [])
const events = computed(() => dashboard.value?.global_events || [])
const stocks = computed(() => dashboard.value?.stock_opportunities || [])
const clusters = computed(() => dashboard.value?.event_clusters || [])
const sourceEnvelopes = computed(() => dashboard.value?.source_envelopes || [])
const crawlerStatuses = computed(() => dashboard.value?.crawler_statuses || [])

const marketTemperature = computed(() => {
  if (!themes.value.length) return 0
  return average(themes.value.map((theme) => Number(theme.score || 0)))
})

const globalRisk = computed(() => Math.max(0, ...events.value.map((event) => Number(event.severity || 0))))

const coverageScore = computed(() => Number(dashboard.value?.source_coverage?.score || 0))

const staleSourceCount = computed(() =>
  crawlerStatuses.value.filter((source) => !source.ok || Number(source.lag_minutes || 0) > 15).length
)

const highRiskEvents = computed(() => events.value.filter((event) => Number(event.severity || 0) >= 72))

const topThemes = computed(() =>
  [...themes.value].sort((a, b) => Number(b.score || 0) - Number(a.score || 0)).slice(0, 8)
)

const topEvents = computed(() =>
  [...events.value]
    .sort((a, b) => eventPriorityScore(b) - eventPriorityScore(a))
    .slice(0, 10)
)

const topStocks = computed(() =>
  [...stocks.value].sort((a, b) => Number(b.score || 0) - Number(a.score || 0)).slice(0, 8)
)

const freshestEnvelopeCount = computed(() =>
  sourceEnvelopes.value.filter((source) => source.state === 'fresh').length
)

const totalEnvelopeRecords = computed(() =>
  sourceEnvelopes.value.reduce((sum, source) => sum + Number(source.record_count || 0), 0)
)

const latestIngestAge = computed(() => minutesSince(dashboard.value?.last_ingested_at))

const latestReportAge = computed(() => minutesSince(dashboard.value?.last_report_generated_at))

const metricView = computed<MetricView>(() => {
  if (metricKey.value === 'risk') return buildRiskView()
  if (metricKey.value === 'coverage') return buildCoverageView()
  if (metricKey.value === 'automation') return buildAutomationView()
  return buildTemperatureView()
})

const evidenceItems = computed<EvidenceItem[]>(() => {
  if (metricKey.value === 'risk') return riskEvidence()
  if (metricKey.value === 'coverage') return coverageEvidence()
  if (metricKey.value === 'automation') return automationEvidence()
  return temperatureEvidence()
})

const automationSchedule = [
  { time: '每 5 分钟', name: '增量抓取', description: '新闻、全球事件、股吧评论、行情、资金、公告、研报元数据。' },
  { time: '08:20', name: '开盘前增强抓取', description: '回看 36 小时并检查核心数据源健康。' },
  { time: '08:35', name: '开盘前报告', description: '基于滚动证据池生成市场情报和投资日报。' },
  { time: '10:30 / 13:30 / 14:45', name: '盘中快报', description: '只刷新重点变化、突发事件和候选信号。' },
  { time: '16:30', name: '收盘复盘', description: '对当日预测、资金、量价和事件兑现情况复盘。' },
  { time: '19:30', name: '研报深度摘要', description: '仅解析新增 PDF，做行业与个股映射。' }
]

function buildTemperatureView(): MetricView {
  const method = methodology.value?.market_temperature_formula || {}
  const activeThemeCount = themes.value.filter((theme) => Number(theme.score || 0) >= 70).length
  const positiveStockCount = stocks.value.filter((stock) => Number(stock.score || 0) > 0).length
  const newsActivity = clusters.value.reduce((sum, cluster) => sum + Number(cluster.document_count || 0), 0)
  const eventDrag = globalRisk.value
  const status = marketTemperature.value >= 75 ? '高热，需要检查是否已 price-in' : '主题均分 / 资金量价等待确认'
  return {
    title: '市场温度解析',
    subtitle: '解释当前市场是否处在可交易的主题扩散阶段，并把热度、资金、量价和全球风险拆开看。',
    value: formatScore(marketTemperature.value),
    status,
    badge: activeThemeCount ? `${activeThemeCount} 个活跃主题` : '主题等待扩散',
    tagType: marketTemperature.value >= 75 ? 'warning' : 'info',
    tone: 'temperature',
    progress: scoreToProgress(marketTemperature.value),
    progressColor: '#37d4b5',
    interpretation:
      marketTemperature.value >= 75
        ? '温度偏高，下一步重点不是追热度，而是检查资金确认、候选股票是否已经充分反映。'
        : '温度处在中性偏热区间，说明主题有材料支撑，但还需要成交、资金和价格结构进一步确认。',
    formula: method.formula || '25%市场广度 + 20%成交/换手 + 20%主题热度 + 15%新闻舆情 + 15%资金确认 - 15%全球风险',
    normalization: method.normalization_method || '主题、新闻、资金和风险因子使用 z-score、百分位和 sigmoid 归一化，避免简单封顶导致全部 100。',
    inputs: [
      { label: '主题数量', value: `${themes.value.length}` },
      { label: '主题均分', value: formatScore(marketTemperature.value) },
      { label: '活跃主题', value: `${activeThemeCount}` },
      { label: '事件新闻簇', value: `${clusters.value.length}` },
      { label: '证据文档', value: `${newsActivity}` },
      { label: '全球风险拖累', value: formatScore(eventDrag) }
    ],
    breakdown: [
      {
        label: '主题热度',
        value: formatScore(marketTemperature.value),
        description: '取当前主题热力图的真实均分，反映题材扩散强度。',
        score: marketTemperature.value
      },
      {
        label: '活跃主题占比',
        value: `${activeThemeCount}/${themes.value.length || 0}`,
        description: '70 分以上主题越多，市场情绪越容易从单点扩散到板块。',
        score: themes.value.length ? (activeThemeCount / themes.value.length) * 100 : 0
      },
      {
        label: '候选股覆盖',
        value: `${positiveStockCount}/${stocks.value.length || 0}`,
        description: '候选池不是涨幅榜，而是从事件、主题、资金和量价中筛出的可观察标的。',
        score: stocks.value.length ? (positiveStockCount / stocks.value.length) * 100 : 0
      },
      {
        label: '全球风险拖累',
        value: formatScore(eventDrag),
        description: '全球风险越高，市场温度越需要用避险、汇率、能源和供应链风险校正。',
        score: 100 - scoreToProgress(eventDrag),
        color: '#ff7186'
      }
    ],
    actions: [
      { title: '先看主线，不先看涨幅榜', description: '从高分主题进入事件簇，再看哪些公司有新增催化、资金确认和未充分 price-in。' },
      { title: '用风险拖累过滤热度', description: '当全球风险高而市场温度也高时，优先选择受益链条明确、基本面可兑现的方向。' },
      { title: '关注长线兑现', description: '温度只是入口，最终仍要回到产业地位、供应链暴露、订单和财务兑现。' }
    ]
  }
}

function buildRiskView(): MetricView {
  const method = methodology.value?.global_risk_formula || {}
  const topRisk = globalRisk.value
  const mappedThemeCount = new Set(events.value.flatMap((event) => event.mapped_themes || [])).size
  const influenceAvg = average(events.value.map((event) => Number(event.influence_score || event.focus_score || event.severity || 0)))
  return {
    title: '全球风险解析',
    subtitle: '把全球事件按严重度、来源影响力、地理汇聚和 A股映射拆开，判断风险是否会传导到资产与行业。',
    value: formatScore(topRisk),
    status: `${events.value.length} 个事件 / ${highRiskEvents.value.length} 个高危`,
    badge: topRisk >= 80 ? '高风险置顶' : '常规监控',
    tagType: topRisk >= 80 ? 'danger' : 'warning',
    tone: 'risk',
    progress: scoreToProgress(topRisk),
    progressColor: '#ff7186',
    interpretation:
      topRisk >= 80
        ? '全球风险处在高位，事件地图和影响链需要优先查看，特别是能源、汇率、航运和供应链通道。'
        : '全球风险尚未进入极端区间，但仍应检查高影响事件是否映射到 A股主线。',
    formula: method.formula || '50%国家/区域风险 + 30%地理事件汇聚 + 20%基础设施/供应链风险 + 突发新闻加成',
    normalization: method.normalization_method || '事件严重度、来源权重、地理汇聚和 A股映射强度统一归一化，并对突发高影响事件加权。',
    inputs: [
      { label: '事件总数', value: `${events.value.length}` },
      { label: '最高严重度', value: formatScore(topRisk) },
      { label: '高危事件', value: `${highRiskEvents.value.length}` },
      { label: '映射主题', value: `${mappedThemeCount}` },
      { label: '平均影响力', value: formatScore(influenceAvg) },
      { label: '地图图层', value: `${dashboard.value?.map_layers?.length || 0}` }
    ],
    breakdown: [
      {
        label: '最高严重度',
        value: formatScore(topRisk),
        description: '顶部全球风险卡取当前窗口内最高事件严重度，避免重大事件被平均值淹没。',
        score: topRisk
      },
      {
        label: '高危事件密度',
        value: `${highRiskEvents.value.length}/${events.value.length || 0}`,
        description: '72 分以上事件越多，说明风险不是孤立点，而是区域或主题聚集。',
        score: events.value.length ? (highRiskEvents.value.length / events.value.length) * 100 : 0
      },
      {
        label: '来源与影响力',
        value: formatScore(influenceAvg),
        description: '综合来源权重、内容影响、事件聚合和 A股映射后的关注度。',
        score: influenceAvg
      },
      {
        label: 'A股主题映射',
        value: `${mappedThemeCount} 个主题`,
        description: '风险只有能映射到产业链、资产变量或上市公司时才进入交易推演。',
        score: Math.min(100, mappedThemeCount * 12)
      }
    ],
    actions: [
      { title: '先点地图事件', description: '进入具体地点和事件详情，看新闻、资产变量、传导渠道、A股主题和候选股票。' },
      { title: '区分风险和机会', description: '同一事件可能让油气、军工、黄金受益，也可能让航空、化工、出口链承压。' },
      { title: '跟踪是否扩散', description: '单点事件只做观察，区域聚集和多源确认才提高交易权重。' }
    ]
  }
}

function buildCoverageView(): MetricView {
  const coverage = dashboard.value?.source_coverage
  const breakdown = (coverage?.score_breakdown || {}) as Record<string, any>
  const okCount = Number(coverage?.ok_count || 0)
  const total = Number(coverage?.total || 0)
  const stale = staleSourceCount.value
  return {
    title: '数据覆盖解析',
    subtitle: '检查当前证据池是不是足够新鲜、足够多源，避免 AI 基于过时或单一来源做判断。',
    value: `${formatScore(coverageScore.value)}%`,
    status: coverage?.label || '数据源健康度',
    badge: stale ? `${stale} 个源需关注` : '健康',
    tagType: stale ? 'warning' : 'success',
    tone: 'coverage',
    progress: scoreToProgress(coverageScore.value),
    progressColor: '#7aa7ff',
    interpretation:
      stale > 0
        ? '覆盖率整体可用，但存在超过 15 分钟未成功抓取的数据源，相关分析需要标记新鲜度。'
        : '核心数据源状态健康，当前报告可以使用滚动证据池作为主要输入。',
    formula: breakdown.formula || 'ok_count / total * 100',
    normalization: breakdown.normalization_method || '按核心源最近一次成功抓取状态计算；源超过 15 分钟未成功则进入黄色预警。',
    inputs: [
      { label: '健康源', value: `${okCount}` },
      { label: '总源数', value: `${total}` },
      { label: '数据包', value: `${sourceEnvelopes.value.length}` },
      { label: '新鲜包', value: `${freshestEnvelopeCount.value}` },
      { label: '记录数', value: `${totalEnvelopeRecords.value}` },
      { label: '预警源', value: `${stale}` }
    ],
    breakdown: [
      {
        label: '核心源健康率',
        value: `${okCount}/${total}`,
        description: '用于判断东方财富、公开新闻、全球事件、评论、研报等源是否持续可用。',
        score: coverageScore.value
      },
      {
        label: '数据包新鲜度',
        value: `${freshestEnvelopeCount.value}/${sourceEnvelopes.value.length || 0}`,
        description: 'World Monitor 风格 envelope 用于观察每类情报包的新鲜度和覆盖范围。',
        score: sourceEnvelopes.value.length ? (freshestEnvelopeCount.value / sourceEnvelopes.value.length) * 100 : coverageScore.value
      },
      {
        label: '证据记录量',
        value: `${totalEnvelopeRecords.value}`,
        description: '记录数越多，AI 分析越不容易只依赖几条新闻。',
        score: Math.min(100, Math.log10(totalEnvelopeRecords.value + 1) * 28)
      },
      {
        label: '延迟预警',
        value: `${stale} 个`,
        description: '核心源超过 15 分钟未成功抓取时会降低置信度，而不是悄悄使用旧材料。',
        score: Math.max(0, 100 - stale * 18),
        color: '#f5b24c'
      }
    ],
    actions: [
      { title: '先看新鲜度再看结论', description: '当某类源 stale 时，对应新闻、评论或全球事件结论要降低置信度。' },
      { title: '多源交叉确认', description: '同一事件被 RSS、API、股吧、公告或研报共同验证时，信号权重提高。' },
      { title: '缺源时允许 partial', description: '系统仍可生成报告，但需要把缺失源和风险写进报告。' }
    ]
  }
}

function buildAutomationView(): MetricView {
  const okCount = crawlerStatuses.value.filter((source) => source.ok).length
  const total = crawlerStatuses.value.length
  const ingestAge = latestIngestAge.value
  const reportAge = latestReportAge.value
  const saved = crawlerStatuses.value.reduce((sum, source) => sum + Number(source.saved || 0), 0)
  const fetched = crawlerStatuses.value.reduce((sum, source) => sum + Number(source.fetched || 0), 0)
  const freshnessScore = ingestAge === null ? 0 : Math.max(0, 100 - Math.max(0, ingestAge - 5) * 6)
  return {
    title: '自动化抓取解析',
    subtitle: '查看 5 分钟增量抓取、固定报告任务、数据源延迟和报告生成节奏是否正常。',
    value: '5min',
    status: `最近抓取 ${formatTime(dashboard.value?.last_ingested_at)}`,
    badge: ingestAge !== null && ingestAge <= 15 ? '持续运行' : '抓取延迟',
    tagType: ingestAge !== null && ingestAge <= 15 ? 'success' : 'warning',
    tone: 'automation',
    progress: scoreToProgress(freshnessScore),
    progressColor: '#f5b24c',
    interpretation:
      ingestAge !== null && ingestAge <= 15
        ? '增量抓取仍在 15 分钟健康窗口内，日报和市场情报会基于滚动证据池更新。'
        : '最近抓取已超过健康窗口，需要检查 APScheduler、爬虫源和容器日志。',
    formula: '每 5 分钟增量抓取 + 固定时间生成报告；抓取任务只做入库和信号预计算，定时报点和突发事件才生成 GPT 报告。',
    normalization: '自动化健康度以最近抓取时间、核心源成功率、失败数和报告生成时间综合判断；超过 15 分钟触发黄色预警。',
    inputs: [
      { label: '抓取间隔', value: '5 分钟' },
      { label: '抓取延迟', value: ingestAge === null ? '-' : `${Math.round(ingestAge)} 分钟` },
      { label: '报告延迟', value: reportAge === null ? '-' : `${Math.round(reportAge)} 分钟` },
      { label: '健康任务', value: `${okCount}/${total || 0}` },
      { label: '抓取量', value: `${fetched}` },
      { label: '入库量', value: `${saved}` }
    ],
    breakdown: [
      {
        label: '抓取新鲜度',
        value: ingestAge === null ? '-' : `${Math.round(ingestAge)} 分钟`,
        description: '5 分钟任务从上次成功时间回退 10 分钟，避免漏抓。',
        score: freshnessScore
      },
      {
        label: '任务成功率',
        value: `${okCount}/${total || 0}`,
        description: '每个任务会写入 crawler_runs，前端据此判断是否健康。',
        score: total ? (okCount / total) * 100 : coverageScore.value
      },
      {
        label: '增量入库',
        value: `${saved}/${fetched}`,
        description: '抓取数和保存数分离，去重后的保存数才进入证据池。',
        score: fetched ? Math.min(100, (saved / fetched) * 100) : 0
      },
      {
        label: '报告节奏',
        value: reportAge === null ? '-' : `${Math.round(reportAge)} 分钟`,
        description: '报告按 08:35、盘中、16:30、19:30 生成，抓取任务不重复生成长报告。',
        score: reportAge === null ? 0 : Math.max(0, 100 - Math.max(0, reportAge - 360) / 12)
      }
    ],
    actions: [
      { title: '抓取和报告分离', description: '5 分钟任务只负责滚动证据池，报告节点才调用 GPT 生成长文。' },
      { title: '关注 15 分钟窗口', description: '核心源超过 15 分钟未成功，顶部看板和本页都会提示预警。' },
      { title: '突发事件可插队', description: '高严重度全球事件入库后会触发地图、影响链和事件卡片刷新。' }
    ]
  }
}

function temperatureEvidence(): EvidenceItem[] {
  const themeEvidence = topThemes.value.map((theme) => ({
    id: `theme-${theme.name}`,
    type: '主题',
    title: theme.name,
    meta: `${formatScore(theme.score)} 分 · 新闻 ${theme.news_count || 0} · 事件 ${theme.event_count || 0}`,
    description: (theme.headlines || theme.keywords || []).slice(0, 2).join(' / ') || '主题热度来自新闻、事件、情绪和来源影响力综合计算。',
    tags: theme.keywords || []
  }))
  const stockEvidence = topStocks.value.slice(0, 4).map((stock) => ({
    id: `stock-${stock.code}`,
    type: '候选股',
    title: `${stock.name}(${stock.code})`,
    meta: `${formatScore(stock.score)} 分 · ${stock.theme || stock.industry || '主题待确认'}`,
    description: stock.candidate_reason || (stock.headlines || []).slice(0, 2).join(' / ') || '来自事件、主题、资金、量价和基本面候选池。',
    tags: stock.matched_themes || (stock.theme ? [stock.theme] : []),
    route: { name: 'StockDetail', params: { code: stock.code } }
  }))
  return [...themeEvidence, ...stockEvidence].slice(0, 12)
}

function riskEvidence(): EvidenceItem[] {
  return topEvents.value.map((event) => ({
    id: `event-${event.event_id}`,
    type: event.location_name || event.region || event.country || '全球事件',
    title: event.title,
    meta: `严重度 ${formatScore(event.severity)} · ${formatTime(event.published_at)} · ${event.source || '多源'}`,
    description: event.summary || '该事件已进入全球事件池，可从地图点进影响链分析。',
    tags: [...(event.mapped_themes || []), ...(event.affected_assets || [])]
  }))
}

function coverageEvidence(): EvidenceItem[] {
  const envelopes = sourceEnvelopes.value.map((source) => ({
    id: `envelope-${source.id}`,
    type: source.state === 'fresh' ? '新鲜' : source.state,
    title: source.label,
    meta: `${source.record_count || 0} 条 · ${source.source_count || 0} 源 · 最新 ${formatTime(source.newest_item_at)}`,
    description: source.failed_datasets?.length
      ? `异常数据集：${source.failed_datasets.slice(0, 3).join('、')}`
      : `覆盖 ${Object.entries(source.category_counts || {}).map(([key, value]) => `${key}:${value}`).join(' / ') || '公共情报源'}`,
    tags: Object.keys(source.category_counts || {})
  }))
  const crawlers = crawlerStatuses.value.slice(0, 10).map((source) => ({
    id: `crawler-${source.name}`,
    type: source.ok ? '健康' : '预警',
    title: source.name,
    meta: `延迟 ${Math.round(Number(source.lag_minutes || 0))} 分钟 · 保存 ${source.saved || 0}`,
    description: source.message || `最近成功 ${formatTime(source.last_success_at)}，最近运行 ${formatTime(source.last_run_at)}。`,
    tags: [source.ok ? 'ok' : 'stale']
  }))
  return [...envelopes, ...crawlers].slice(0, 16)
}

function automationEvidence(): EvidenceItem[] {
  return crawlerStatuses.value.slice(0, 14).map((source) => ({
    id: `automation-${source.name}`,
    type: source.ok ? '任务正常' : '任务预警',
    title: source.name,
    meta: `抓取 ${source.fetched || 0} · 入库 ${source.saved || 0} · 失败 ${source.failed || 0}`,
    description: `最近运行 ${formatTime(source.last_run_at)}，最近成功 ${formatTime(source.last_success_at)}，延迟 ${Math.round(Number(source.lag_minutes || 0))} 分钟。`,
    tags: [source.ok ? 'ok' : 'warning']
  }))
}

function openEvidence(item: EvidenceItem) {
  if (item.route) {
    router.push(item.route)
    return
  }
  if (metricKey.value === 'risk' && item.id.startsWith('event-')) {
    const eventId = item.id.replace('event-', '')
    router.push({ name: 'MarketIntelligenceHome', query: { event_id: eventId, hours: String(hours.value) } })
    return
  }
}

function openMetric(key: MetricKey) {
  router.push({ name: 'MarketIntelligenceMetricDetail', params: { metric: key }, query: { hours: String(hours.value) } })
}

function goBack() {
  router.push({ name: 'MarketIntelligenceHome', query: { hours: String(hours.value) } })
}

async function loadData() {
  loading.value = true
  try {
    const [latestResponse, methodologyResponse] = await Promise.all([
      marketIntelligenceApi.getLatest(hours.value),
      marketIntelligenceApi.getMethodology()
    ])
    dashboard.value = latestResponse.data
    methodology.value = methodologyResponse.data
  } catch (error) {
    console.error('加载指标解析失败:', error)
    ElMessage.error('加载指标解析失败')
  } finally {
    loading.value = false
  }
}

function eventPriorityScore(event: GlobalEvent) {
  return (
    Number(event.severity || 0) * 0.42 +
    Number(event.influence_score || event.source_impact_score || 0) * 0.24 +
    Number(event.focus_score || 0) * 0.18 +
    Number(event.event_count_at_location || 0) * 3 +
    (event.mapped_themes?.length || 0) * 2
  )
}

function average(values: number[]) {
  const clean = values.filter((value) => Number.isFinite(value))
  if (!clean.length) return 0
  return clean.reduce((sum, value) => sum + value, 0) / clean.length
}

function minutesSince(value?: string | null) {
  if (!value) return null
  const time = new Date(value).getTime()
  if (!Number.isFinite(time)) return null
  return Math.max(0, (Date.now() - time) / 60000)
}

function scoreToProgress(value?: number) {
  const score = Number(value || 0)
  if (!Number.isFinite(score)) return 0
  return Math.max(0, Math.min(100, score))
}

function formatScore(value?: number) {
  return Number(value || 0).toFixed(1)
}

function formatTime(value?: string | null) {
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

watch(() => route.params.metric, () => {
  if (!metricTabs.some((item) => item.key === String(route.params.metric || ''))) {
    openMetric('temperature')
  }
})

onMounted(() => {
  loadData()
  refreshTimer = window.setInterval(() => {
    loadData()
  }, 60000)
})

onBeforeUnmount(() => {
  if (refreshTimer) window.clearInterval(refreshTimer)
})
</script>

<style scoped lang="scss">
.metric-detail {
  min-height: 100%;
  padding: 0;
  color: #dce7f7;
  background:
    radial-gradient(circle at 16% 14%, rgba(48, 94, 166, 0.18), transparent 30%),
    linear-gradient(180deg, #0c1320 0%, #101722 100%);
}

.detail-header {
  display: grid;
  grid-template-columns: auto minmax(0, 1fr) 210px;
  gap: 16px;
  align-items: center;
  padding: 20px 22px;
  margin-bottom: 14px;
  border: 1px solid rgba(131, 160, 202, 0.18);
  border-radius: 8px;
  background:
    linear-gradient(90deg, rgba(20, 38, 64, 0.96), rgba(12, 20, 34, 0.96) 58%, rgba(16, 35, 44, 0.92));
  box-shadow: 0 18px 48px rgba(0, 0, 0, 0.24);
}

.back-button {
  color: #bdd4ff;
}

.header-copy {
  min-width: 0;

  .eyebrow {
    margin: 0 0 5px;
    color: #6db8ff;
    font-size: 12px;
    font-weight: 700;
  }

  h1 {
    margin: 0;
    color: #f6f9ff;
    font-size: 28px;
    font-weight: 780;
    letter-spacing: 0;
  }

  p:last-child {
    margin: 7px 0 0;
    color: #92a0b8;
    line-height: 1.55;
  }
}

.header-reading {
  position: relative;
  overflow: hidden;
  min-height: 112px;
  padding: 14px;
  border: 1px solid rgba(148, 163, 184, 0.2);
  border-radius: 8px;
  background: rgba(8, 14, 24, 0.62);

  &::before {
    content: "";
    position: absolute;
    inset: 0 auto 0 0;
    width: 3px;
    background: #37d4b5;
  }

  &.risk::before {
    background: #ff7186;
  }

  &.coverage::before {
    background: #7aa7ff;
  }

  &.automation::before {
    background: #f5b24c;
  }

  span,
  small {
    display: block;
    color: #92a0b8;
  }

  strong {
    display: block;
    margin: 7px 0 3px;
    color: #f6f9ff;
    font-size: 32px;
    line-height: 1;
  }

  small {
    line-height: 1.45;
  }
}

.loading-shell {
  padding: 20px;
  border-radius: 8px;
  background: rgba(12, 20, 33, 0.9);
}

.metric-tabs {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 14px;

  button {
    display: inline-flex;
    align-items: center;
    gap: 7px;
    min-height: 38px;
    padding: 0 14px;
    border: 1px solid rgba(110, 150, 208, 0.24);
    border-radius: 8px;
    background: rgba(12, 20, 33, 0.86);
    color: #a9b8d0;
    cursor: pointer;

    &.active,
    &:hover {
      border-color: rgba(96, 165, 250, 0.72);
      background: rgba(37, 99, 235, 0.18);
      color: #f4f8ff;
    }
  }
}

.panel {
  min-width: 0;
  padding: 15px;
  border: 1px solid rgba(148, 163, 184, 0.18);
  border-radius: 8px;
  background: rgba(12, 20, 33, 0.9);
  box-shadow: 0 16px 38px rgba(0, 0, 0, 0.22);
}

.section-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  min-height: 32px;
  margin-bottom: 13px;
  color: #f4f8ff;
  font-weight: 720;

  span {
    display: inline-flex;
    align-items: center;
    gap: 7px;
    min-width: 0;
  }
}

.overview-grid,
.content-grid {
  display: grid;
  gap: 14px;
}

.overview-grid {
  grid-template-columns: minmax(320px, 0.42fr) minmax(0, 0.58fr);
}

.content-grid {
  grid-template-columns: minmax(0, 1fr) minmax(320px, 0.44fr);
  margin-top: 14px;
}

.reading-panel {
  display: grid;
}

.meter {
  display: flex;
  justify-content: center;
  padding: 4px 0 10px;
}

.meter-value {
  color: #f6f9ff;
  font-size: 24px;
  font-weight: 760;
}

.metric-summary {
  margin: 0;
  color: #b9c5d8;
  line-height: 1.7;
}

.freshness-row {
  display: grid;
  gap: 7px;
  margin-top: 12px;

  span {
    padding: 7px 9px;
    border: 1px solid rgba(110, 150, 208, 0.18);
    border-radius: 8px;
    background: rgba(57, 116, 216, 0.1);
    color: #9fafc6;
    font-size: 12px;
  }
}

.formula-box {
  padding: 13px;
  border: 1px solid rgba(55, 212, 181, 0.24);
  border-radius: 8px;
  background: rgba(27, 130, 109, 0.1);
  color: #d7fff2;
  line-height: 1.75;
  font-weight: 650;
}

.normalization {
  margin-top: 10px;
  color: #9fafc6;
  line-height: 1.7;
}

.input-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 9px;
  margin-top: 12px;
}

.input-item {
  min-height: 68px;
  padding: 10px;
  border: 1px solid rgba(148, 163, 184, 0.14);
  border-radius: 8px;
  background: rgba(8, 14, 24, 0.58);

  span {
    display: block;
    color: #7f8da6;
    font-size: 12px;
  }

  strong {
    display: block;
    margin-top: 8px;
    overflow-wrap: anywhere;
    color: #f4f8ff;
    font-size: 18px;
  }
}

.breakdown-list {
  display: grid;
  gap: 10px;
}

.breakdown-row {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 160px;
  gap: 14px;
  align-items: center;
  padding: 12px;
  border: 1px solid rgba(148, 163, 184, 0.14);
  border-radius: 8px;
  background: rgba(8, 14, 24, 0.58);
}

.breakdown-main {
  strong {
    display: block;
    color: #f4f8ff;
  }

  span {
    display: block;
    margin-top: 5px;
    color: #9fafc6;
    line-height: 1.55;
    font-size: 12px;
  }
}

.breakdown-score {
  b {
    display: block;
    margin-bottom: 6px;
    color: #f6f9ff;
    text-align: right;
  }
}

.action-list {
  display: grid;
  gap: 10px;
}

.action-item {
  padding: 12px;
  border: 1px solid rgba(110, 150, 208, 0.18);
  border-radius: 8px;
  background: rgba(57, 116, 216, 0.1);

  strong {
    display: block;
    color: #f4f8ff;
  }

  span {
    display: block;
    margin-top: 6px;
    color: #aebbd0;
    line-height: 1.65;
    font-size: 12px;
  }
}

.evidence-panel,
.schedule-panel {
  margin-top: 14px;
}

.evidence-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 10px;
}

.evidence-card {
  display: grid;
  gap: 7px;
  min-height: 150px;
  padding: 12px;
  text-align: left;
  border: 1px solid rgba(148, 163, 184, 0.16);
  border-radius: 8px;
  background:
    linear-gradient(180deg, rgba(16, 28, 46, 0.78), rgba(8, 14, 24, 0.76));
  color: inherit;
  cursor: pointer;

  &:hover {
    border-color: rgba(96, 165, 250, 0.72);
    background: rgba(37, 99, 235, 0.16);
  }

  strong {
    color: #f4f8ff;
    line-height: 1.45;
  }
}

.evidence-type {
  width: fit-content;
  padding: 3px 7px;
  border: 1px solid rgba(96, 165, 250, 0.38);
  border-radius: 6px;
  color: #9fc7ff;
  font-size: 11px;
}

.evidence-meta {
  color: #8796af;
  font-size: 12px;
}

.evidence-desc {
  color: #aab8cc;
  line-height: 1.55;
  font-size: 12px;
}

.evidence-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 5px;
  align-self: end;
}

.schedule-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 10px;
}

.schedule-item {
  padding: 12px;
  border: 1px solid rgba(245, 178, 76, 0.2);
  border-radius: 8px;
  background: rgba(245, 178, 76, 0.08);

  strong {
    display: block;
    color: #ffd38a;
  }

  span {
    display: block;
    margin-top: 7px;
    color: #f4f8ff;
    font-weight: 680;
  }

  small {
    display: block;
    margin-top: 6px;
    color: #aebbd0;
    line-height: 1.55;
  }
}

@media (max-width: 1200px) {
  .detail-header,
  .overview-grid,
  .content-grid {
    grid-template-columns: 1fr;
  }

  .header-reading {
    width: 100%;
  }

  .evidence-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (max-width: 760px) {
  .detail-header {
    padding: 16px;
  }

  .header-copy h1 {
    font-size: 23px;
  }

  .input-grid,
  .schedule-grid,
  .evidence-grid {
    grid-template-columns: 1fr;
  }

  .breakdown-row {
    grid-template-columns: 1fr;
  }

  .breakdown-score b {
    text-align: left;
  }
}
</style>
