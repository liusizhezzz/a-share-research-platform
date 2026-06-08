<template>
  <div class="market-intelligence">
    <div class="page-header">
      <div>
        <h1>全球事件与A股映射</h1>
        <p>滚动抓取新闻、评论、研报、全球事件、行情和资金，生成可交易验证的市场情报。</p>
      </div>
      <div class="header-actions">
        <el-select v-model="hours" class="hours-select" @change="loadLatest">
          <el-option :value="12" label="近12小时" />
          <el-option :value="36" label="近36小时" />
          <el-option :value="72" label="近72小时" />
          <el-option :value="168" label="近7天" />
        </el-select>
        <el-select v-model="reportType" class="type-select">
          <el-option value="pre_market" label="开盘前报告" />
          <el-option value="intraday" label="盘中快报" />
          <el-option value="closing" label="收盘复盘" />
          <el-option value="event_flash" label="突发事件卡片" />
        </el-select>
        <el-button @click="loadLatest" :loading="loading">
          <el-icon><Refresh /></el-icon>
          刷新
        </el-button>
        <el-button @click="showMethodology">
          <el-icon><DataAnalysis /></el-icon>
          方法论
        </el-button>
        <el-button type="primary" @click="generateReport" :loading="generating">
          <el-icon><Document /></el-icon>
          生成报告
        </el-button>
      </div>
    </div>

    <el-alert
      v-if="dashboard?.has_high_severity_event"
      class="event-alert"
      type="error"
      show-icon
      :closable="false"
      title="出现高严重度全球事件，已置顶事件影响链和相关主题/个股信号"
    />
    <el-alert
      v-else-if="staleSources.length"
      class="event-alert"
      type="warning"
      show-icon
      :closable="false"
      :title="`数据源预警：${staleSources.map((item) => item.name).join('、')} 超过15分钟未成功抓取`"
    />

    <el-empty v-if="!loading && !dashboard" description="暂无市场情报数据">
      <el-button type="primary" @click="generateReport" :loading="generating">立即生成</el-button>
    </el-empty>

    <template v-if="dashboard">
      <div class="kpi-grid">
        <div class="kpi-panel clickable" @click="openMetricDetail('temperature')">
          <div class="kpi-label"><el-icon><TrendCharts /></el-icon>市场温度</div>
          <div class="kpi-value">{{ formatScore(marketTemperature) }}</div>
          <div class="kpi-sub">主题均分 / 资金量价等待确认</div>
        </div>
        <div class="kpi-panel clickable" @click="openMetricDetail('risk')">
          <div class="kpi-label"><el-icon><WarningFilled /></el-icon>全球风险</div>
          <div class="kpi-value danger">{{ formatScore(globalRisk) }}</div>
          <div class="kpi-sub">{{ dashboard.global_events.length }} 个事件</div>
        </div>
        <div class="kpi-panel clickable" @click="openMetricDetail('coverage')">
          <div class="kpi-label"><el-icon><Connection /></el-icon>数据覆盖</div>
          <div class="kpi-value">{{ dashboard.source_coverage.score }}%</div>
          <div class="kpi-sub">{{ dashboard.source_coverage.label }}</div>
        </div>
        <div class="kpi-panel clickable" @click="openMetricDetail('automation')">
          <div class="kpi-label"><el-icon><Timer /></el-icon>自动化</div>
          <div class="kpi-value">5min</div>
          <div class="kpi-sub">最近抓取 {{ formatTime(dashboard.last_ingested_at) }}</div>
        </div>
      </div>

      <div class="summary-panel">
        <div>
          <div class="summary-title">核心结论</div>
          <div class="summary-text">{{ dashboard.summary }}</div>
        </div>
        <div class="meta-pills">
          <span>报告 {{ formatTime(dashboard.last_report_generated_at) }}</span>
          <span>源 {{ dashboard.source_coverage.ok_count }}/{{ dashboard.source_coverage.total }}</span>
          <span>{{ dashboard.has_high_severity_event ? '高风险置顶' : '常规监控' }}</span>
        </div>
      </div>

      <section v-if="dashboard.event_clusters?.length" class="panel cluster-panel">
        <div class="panel-header">
          <span><el-icon><Tickets /></el-icon>事件新闻簇</span>
          <el-tag effect="plain">{{ dashboard.event_clusters.length }} clusters</el-tag>
        </div>
        <div class="cluster-grid">
          <button
            v-for="cluster in dashboard.event_clusters.slice(0, 8)"
            :key="cluster.cluster_id"
            class="cluster-card"
            :class="{ active: cluster.cluster_id === selectedClusterId }"
            @click="filterCluster(cluster)"
          >
            <span class="cluster-title">{{ cluster.title }}</span>
            <span class="cluster-meta">
              {{ cluster.document_count || 0 }} 条 · {{ (cluster.sources || []).slice(0, 3).join(' / ') || '多源' }}
            </span>
            <span v-if="cluster.linked_event_title" class="cluster-link">
              映射事件：{{ cluster.linked_event_location || '全球' }} · {{ cluster.linked_event_title }}
            </span>
            <span class="cluster-tags">
              <el-tag v-for="theme in (cluster.themes || []).slice(0, 3)" :key="theme" size="small" effect="plain">
                {{ theme }}
              </el-tag>
            </span>
          </button>
        </div>
      </section>

      <section v-if="dashboard.source_envelopes?.length" class="panel source-panel">
        <div class="panel-header">
          <span><el-icon><Connection /></el-icon>情报源新鲜度</span>
          <el-tag effect="plain">WorldMonitor envelope</el-tag>
        </div>
        <SourceEnvelopePanel :sources="dashboard.source_envelopes" />
      </section>

      <section v-if="dashboard.corridor_strip?.length" class="panel corridor-panel">
        <div class="panel-header">
          <span><el-icon><Position /></el-icon>关键通道风险条</span>
          <el-tag effect="plain">海峡 / 运河 / 供应链</el-tag>
        </div>
        <ChokepointStrip :corridors="dashboard.corridor_strip" />
      </section>

      <div class="main-grid">
        <section class="panel map-panel">
          <div class="panel-header">
            <span><el-icon><MapLocation /></el-icon>全球事件地图</span>
            <el-tag :type="dashboard.has_high_severity_event ? 'danger' : 'info'" effect="plain">
              {{ dashboard.global_events.length }} events
            </el-tag>
          </div>
          <LayerControlRail
            v-if="dashboard.map_layers?.length"
            :layers="dashboard.map_layers"
            :selected-ids="selectedLayerIds"
            @update:selected-ids="selectedLayerIds = $event"
          />
          <GlobalEventMap
            :events="visibleEvents"
            :selected-event-id="selectedEventId"
            @select="selectEvent"
          />
        </section>

        <section class="panel impact-panel">
          <div class="panel-header">
            <span><el-icon><Share /></el-icon>事件影响链</span>
            <div class="panel-actions">
              <el-button
                text
                size="small"
                :disabled="!selectedEvent"
                :loading="eventAnalyzing"
                @click="analyzeSelectedEvent(true)"
              >
                分析影响面
              </el-button>
              <el-button text size="small" :disabled="!selectedEvent" @click="drawerVisible = true">详情</el-button>
            </div>
          </div>
          <div v-if="selectedEvent" class="selected-event">
            <div class="event-top">
              <el-tag :type="selectedEvent.severity >= 72 ? 'danger' : 'warning'">
                严重度 {{ Math.round(selectedEvent.severity || 0) }}
              </el-tag>
              <span>{{ selectedEvent.location_name || selectedEvent.region }}</span>
            </div>
            <h2>{{ selectedEvent.title }}</h2>
            <p>{{ selectedEvent.summary }}</p>
            <div v-if="eventAnalyzing" class="analysis-status">已加入队列，正在分析：事件、资产变量、传导渠道、A股主题和个股映射...</div>
            <div v-else-if="currentEventAnalysis?.status === 'ready' || currentEventAnalysis?.status === 'partial'" class="analysis-status ready">
              AI 影响分析已生成 · {{ currentEventAnalysis.model || 'DashScope' }}
            </div>
          </div>
          <TransmissionSankeyChart :chain="selectedChain" />
          <EventTimelineFeed
            v-if="dashboard.event_feed?.length"
            class="event-feed-panel"
            :items="dashboard.event_feed"
            :selected-event-id="selectedEventId"
            @select="selectEventById($event, { openDrawer: true, analyze: true })"
          />
        </section>
      </div>

      <div class="analysis-grid">
        <section class="panel treemap-panel">
          <div class="panel-header">
            <span><el-icon><DataAnalysis /></el-icon>A股主题热力图</span>
            <el-tag v-if="selectedTheme" effect="plain">{{ selectedTheme.name }}</el-tag>
          </div>
          <ThemeTreemapChart :nodes="dashboard.theme_heatmap_nodes" @select="selectedTheme = $event" />
        </section>

        <section class="panel radar-panel">
          <div class="panel-header">
            <span><el-icon><Bell /></el-icon>风险雷达</span>
          </div>
          <RiskRadarChart
            :events="dashboard.global_events"
            :themes="dashboard.theme_heatmap_nodes"
            :coverage="dashboard.source_coverage"
          />
          <div class="risk-list">
            <div v-for="warning in dashboard.risk_warnings" :key="warning" class="risk-item">
              {{ warning }}
            </div>
          </div>
        </section>
      </div>

      <div class="analysis-grid bottom">
        <section class="panel">
          <div class="panel-header">
            <span><el-icon><Grid /></el-icon>行业信号矩阵</span>
          </div>
          <IndustryHeatmapChart :cells="dashboard.industry_matrix" />
        </section>
      </div>

      <section class="panel stock-panel">
        <div class="panel-header">
          <span><el-icon><Tickets /></el-icon>个股机会表</span>
          <el-tag v-if="selectedStock" effect="plain">{{ selectedStock.name }}({{ selectedStock.code }})</el-tag>
        </div>
        <StockOpportunityTable
          :stocks="dashboard.stock_opportunities"
          @select="handleStockSelect"
        />
      </section>

      <section class="panel report-panel">
        <div class="panel-header">
          <span><el-icon><Document /></el-icon>AI 投研报告</span>
        </div>
        <pre>{{ dashboard.markdown_report || '暂无报告正文' }}</pre>
      </section>

      <EventImpactDrawer
        v-model="drawerVisible"
        :event="selectedEvent"
        :chain="selectedChain"
        :analysis="currentEventAnalysis"
        :analyzing="eventAnalyzing"
        @analyze="analyzeSelectedEvent(true)"
      />

      <el-drawer v-model="methodologyVisible" title="评分方法论" size="520px" append-to-body>
        <div v-if="methodology" class="methodology">
          <h3>模型路由</h3>
          <pre>{{ stringify(methodology.llm_policy) }}</pre>
          <h3>公式与归一化</h3>
          <pre>{{ stringify(methodology.formulas || methodology) }}</pre>
        </div>
        <el-skeleton v-else :rows="8" animated />
      </el-drawer>
    </template>
  </div>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import {
  Bell,
  Connection,
  DataAnalysis,
  Document,
  Grid,
  MapLocation,
  Position,
  Refresh,
  Share,
  Tickets,
  Timer,
  TrendCharts,
  WarningFilled
} from '@element-plus/icons-vue'
import {
  marketIntelligenceApi,
  type EventCluster,
  type EventImpactAnalysis,
  type EventImpactChain,
  type GlobalEvent,
  type MarketIntelligenceDashboard,
  type StockOpportunity,
  type ThemeHeatmapNode
} from '@/api/marketIntelligence'
import EventImpactDrawer from '@/components/MarketIntelligence/EventImpactDrawer.vue'
import ChokepointStrip from '@/components/MarketIntelligence/ChokepointStrip.vue'
import EventTimelineFeed from '@/components/MarketIntelligence/EventTimelineFeed.vue'
import GlobalEventMap from '@/components/MarketIntelligence/GlobalEventMap.vue'
import IndustryHeatmapChart from '@/components/MarketIntelligence/IndustryHeatmapChart.vue'
import LayerControlRail from '@/components/MarketIntelligence/LayerControlRail.vue'
import RiskRadarChart from '@/components/MarketIntelligence/RiskRadarChart.vue'
import SourceEnvelopePanel from '@/components/MarketIntelligence/SourceEnvelopePanel.vue'
import StockOpportunityTable from '@/components/MarketIntelligence/StockOpportunityTable.vue'
import ThemeTreemapChart from '@/components/MarketIntelligence/ThemeTreemapChart.vue'
import TransmissionSankeyChart from '@/components/MarketIntelligence/TransmissionSankeyChart.vue'

const router = useRouter()
const loading = ref(false)
const generating = ref(false)
const hours = ref(168)
const reportType = ref('pre_market')
const dashboard = ref<MarketIntelligenceDashboard | null>(null)
const selectedEventId = ref<string>()
const selectedClusterId = ref<string>()
const selectedTheme = ref<ThemeHeatmapNode | null>(null)
const selectedStock = ref<StockOpportunity | null>(null)
const selectedLayerIds = ref<string[]>([])
const drawerVisible = ref(false)
const methodologyVisible = ref(false)
const methodology = ref<Record<string, any> | null>(null)
const eventAnalyses = ref<Record<string, EventImpactAnalysis>>({})
const analyzingEventIds = ref<string[]>([])
let refreshTimer: number | undefined
const analysisPollTimers: Record<string, number> = {}

const staleSources = computed(() =>
  (dashboard.value?.crawler_statuses || []).filter((source) => !source.ok && Number(source.lag_minutes || 0) > 15)
)

const selectedEvent = computed(() => {
  const events = dashboard.value?.global_events || []
  if (!selectedEventId.value) return null
  return events.find((event) => event.event_id === selectedEventId.value) || null
})

const normalizeEventText = (value?: string | null) =>
  String(value || '')
    .replace(/\s+/g, '')
    .replace(/[^\u4e00-\u9fa5A-Za-z0-9]/g, '')
    .toLowerCase()

const isChainForEvent = (chain: EventImpactChain, event: GlobalEvent) => {
  if (chain.event_id !== event.event_id) return false
  const eventTitle = normalizeEventText(event.title)
  const chainTitle = normalizeEventText(chain.event_title)
  const firstStep = normalizeEventText(chain.steps?.[0]?.value)
  if (!eventTitle) return true
  return (
    Boolean(chainTitle && (chainTitle.includes(eventTitle) || eventTitle.includes(chainTitle))) ||
    Boolean(firstStep && (firstStep.includes(eventTitle) || eventTitle.includes(firstStep)))
  )
}

const selectedChain = computed(() => {
  const chains = dashboard.value?.event_impact_chains || []
  const event = selectedEvent.value
  const eventId = event?.event_id
  const exact = chains.find((chain) => chain.event_id === eventId)
  if (event && exact && isChainForEvent(exact, event)) return exact
  return event ? buildLocalImpactChain(event) : null
})

const currentEventAnalysis = computed(() => {
  const eventId = selectedEventId.value
  if (!eventId) return null
  const analysis = eventAnalyses.value[eventId]
  return analysis?.event_id === eventId ? analysis : null
})

const eventAnalyzing = computed(() => {
  const eventId = selectedEventId.value
  if (!eventId) return false
  return analyzingEventIds.value.includes(eventId) || ['queued', 'running'].includes(currentEventAnalysis.value?.status || '')
})

const marketTemperature = computed(() => {
  const themes = dashboard.value?.theme_heatmap_nodes || []
  if (!themes.length) return 0
  return themes.reduce((sum, theme) => sum + Number(theme.score || 0), 0) / themes.length
})

const globalRisk = computed(() => {
  const events = dashboard.value?.global_events || []
  return Math.max(0, ...events.map((event) => Number(event.severity || 0)))
})

const visibleEvents = computed(() => {
  const events = dashboard.value?.global_events || []
  if (!selectedLayerIds.value.length) return events
  const filtered = events.filter((event) =>
    (event.map_layers || []).some((layerId) => selectedLayerIds.value.includes(layerId))
  )
  return filtered.length ? filtered : events
})

const loadLatest = async () => {
  loading.value = true
  try {
    const response = await marketIntelligenceApi.getLatest(hours.value)
    dashboard.value = response.data
    ensureLayerSelection()
    ensureSelection()
    await fetchSelectedEventAnalysis()
  } catch (error) {
    console.error('加载市场情报失败:', error)
  } finally {
    loading.value = false
  }
}

const generateReport = async () => {
  generating.value = true
  try {
    const response = await marketIntelligenceApi.generate(reportType.value, true)
    dashboard.value = response.data.dashboard
    ensureLayerSelection()
    ensureSelection()
    ElMessage.success('市场情报报告已生成')
  } catch (error) {
    console.error('生成市场情报报告失败:', error)
  } finally {
    generating.value = false
  }
}

const ensureSelection = () => {
  const events = dashboard.value?.global_events || []
  if (!events.length) {
    selectedEventId.value = undefined
    return
  }
  if (!events.some((event) => event.event_id === selectedEventId.value)) {
    selectedEventId.value = events[0].event_id
  }
}

const ensureLayerSelection = () => {
  const layers = dashboard.value?.map_layers || []
  if (!layers.length) {
    selectedLayerIds.value = []
    return
  }
  const validIds = new Set(layers.map((layer) => layer.id))
  const stillValid = selectedLayerIds.value.filter((id) => validIds.has(id))
  if (stillValid.length) {
    selectedLayerIds.value = stillValid
    return
  }
  const activeIds = layers.filter((layer) => layer.active).map((layer) => layer.id)
  selectedLayerIds.value = activeIds.length ? activeIds : layers.map((layer) => layer.id)
}

const selectEvent = (event: GlobalEvent) => {
  selectEventById(event.event_id, { openDrawer: true, analyze: true })
}

const handleStockSelect = (stock: StockOpportunity) => {
  selectedStock.value = stock
  router.push({ name: 'StockDetail', params: { code: stock.code } })
}

const openMetricDetail = (metric: 'temperature' | 'risk' | 'coverage' | 'automation') => {
  router.push({
    name: 'MarketIntelligenceMetricDetail',
    params: { metric },
    query: { hours: String(hours.value) }
  })
}

const filterCluster = (cluster: EventCluster) => {
  selectedClusterId.value = cluster.cluster_id
  const event = resolveClusterEvent(cluster)
  if (event) {
    selectEventById(event.event_id, { openDrawer: true, analyze: true })
    return
  }
  selectedEventId.value = undefined
  drawerVisible.value = false
  ElMessage.info('该事件簇暂无可定位地图事件，已保留在事件簇列表中')
}

const setEventAnalysis = (eventId: string, analysis: EventImpactAnalysis) => {
  if (!eventId || analysis.event_id !== eventId) {
    console.warn('忽略事件分析串台结果:', { expected: eventId, actual: analysis.event_id })
    return
  }
  eventAnalyses.value = {
    ...eventAnalyses.value,
    [eventId]: analysis
  }
  if (['ready', 'partial', 'error'].includes(analysis.status || '')) {
    clearEventAnalysisPoll(eventId)
  }
}

const clearEventAnalysisPoll = (eventId: string) => {
  const timer = analysisPollTimers[eventId]
  if (timer) {
    window.clearTimeout(timer)
    delete analysisPollTimers[eventId]
  }
}

const scheduleEventAnalysisPoll = (eventId: string, attempts = 30) => {
  if (!eventId || attempts <= 0 || analysisPollTimers[eventId]) return
  analysisPollTimers[eventId] = window.setTimeout(async () => {
    delete analysisPollTimers[eventId]
    await fetchSelectedEventAnalysis(eventId)
    const status = eventAnalyses.value[eventId]?.status
    if (['queued', 'running'].includes(status || '')) {
      scheduleEventAnalysisPoll(eventId, attempts - 1)
    }
  }, 3000)
}

const setEventAnalysisStatus = (eventId: string, status: EventImpactAnalysis['status']) => {
  const event = (dashboard.value?.global_events || []).find((item) => item.event_id === eventId)
  setEventAnalysis(eventId, {
    ...(eventAnalyses.value[eventId] || {}),
    event_id: eventId,
    event_title: event?.title,
    status,
    updated_at: new Date().toISOString()
  })
}

const beginEventAnalysis = (eventId: string) => {
  if (!analyzingEventIds.value.includes(eventId)) {
    analyzingEventIds.value = [...analyzingEventIds.value, eventId]
  }
  setEventAnalysisStatus(eventId, 'running')
  scheduleEventAnalysisPoll(eventId)
}

const finishEventAnalysis = (eventId: string) => {
  analyzingEventIds.value = analyzingEventIds.value.filter((id) => id !== eventId)
}

const analyzeEvent = async (eventId: string, force = false) => {
  if (!eventId) return
  beginEventAnalysis(eventId)
  try {
    const response = await marketIntelligenceApi.analyzeEvent(eventId, force)
    if (response.data?.event_id !== eventId) {
      console.warn('事件分析结果 event_id 不匹配，已丢弃:', { expected: eventId, actual: response.data?.event_id })
      return
    }
    setEventAnalysis(eventId, response.data)
    if (['queued', 'running'].includes(response.data.status || '')) {
      scheduleEventAnalysisPoll(eventId)
    }
    if (selectedEventId.value === eventId) drawerVisible.value = true
  } catch (error) {
    console.error('事件影响分析失败:', error)
    setEventAnalysisStatus(eventId, 'error')
    if (selectedEventId.value === eventId) ElMessage.error('事件影响分析失败')
  } finally {
    finishEventAnalysis(eventId)
  }
}

const analyzeSelectedEvent = async (force = false) => {
  const eventId = selectedEvent.value?.event_id
  if (!eventId) return
  await analyzeEvent(eventId, force)
}

const fetchSelectedEventAnalysis = async (eventId = selectedEvent.value?.event_id) => {
  if (!eventId) {
    return
  }
  try {
    const response = await marketIntelligenceApi.getEventAnalysis(eventId)
    if (response.data?.status === 'not_started') {
      return
    }
    if (response.data?.event_id === eventId) {
      setEventAnalysis(eventId, response.data)
      if (['queued', 'running'].includes(response.data.status || '')) {
        scheduleEventAnalysisPoll(eventId)
      }
    }
  } catch {
    // 未分析或临时错误时不展示其他事件的旧分析。
  }
}

const forceAnalysisNeeded = (analysis?: EventImpactAnalysis | null) =>
  !analysis || !['ready', 'partial', 'queued', 'running'].includes(analysis.status || '')

const selectEventById = (
  eventId: string,
  options: { openDrawer?: boolean; analyze?: boolean } = {}
) => {
  const event = (dashboard.value?.global_events || []).find((item) => item.event_id === eventId)
  if (!event) {
    ElMessage.warning('该事件不在当前时间窗口内，请刷新或扩大时间范围')
    return
  }
  selectedEventId.value = eventId
  if (options.openDrawer) drawerVisible.value = true
  if (options.analyze) {
    const existing = eventAnalyses.value[eventId]
    if (forceAnalysisNeeded(existing)) {
      setEventAnalysisStatus(eventId, 'queued')
    }
    if (forceAnalysisNeeded(existing)) {
      void analyzeEvent(eventId, false)
    } else {
      void fetchSelectedEventAnalysis(eventId)
    }
  } else {
    void fetchSelectedEventAnalysis(eventId)
  }
}

const tokenizeForEventMatch = (value?: string | null) =>
  new Set(
    String(value || '')
      .match(/[\u4e00-\u9fa5A-Za-z0-9]{2,}/g)
      ?.map((token) => token.toLowerCase())
      .filter((token) => !['公司', '今日', '市场', '新闻', '评论', '风险', '影响', 'public', 'html', 'link', 'metadata', 'http', 'https', 'www'].includes(token)) || []
  )

const scoreClusterEvent = (cluster: EventCluster, event: GlobalEvent) => {
  const clusterThemes = new Set(cluster.themes || [])
  const eventThemes = new Set(event.mapped_themes || [])
  const clusterSymbols = new Set(cluster.symbols || [])
  const eventSymbols = new Set(event.mapped_stocks || [])
  const clusterText = `${cluster.title || ''} ${cluster.summary || ''}`
  const eventText = `${event.title || ''} ${event.summary || ''} ${event.location_name || ''} ${event.region || ''} ${event.country || ''}`
  const clusterTokens = tokenizeForEventMatch(clusterText)
  const eventTokens = tokenizeForEventMatch(eventText)
  let score = 0
  clusterThemes.forEach((theme) => {
    if (eventThemes.has(theme)) score += 12
  })
  clusterSymbols.forEach((symbol) => {
    if (eventSymbols.has(symbol)) score += 18
  })
  clusterTokens.forEach((token) => {
    if (eventTokens.has(token)) score += 5
  })
  const hasTitleMatch = Boolean(cluster.title && event.title && (cluster.title.includes(event.title) || event.title.includes(cluster.title)))
  const tokenOverlapCount = Array.from(clusterTokens).filter((token) => eventTokens.has(token)).length
  const documentTypes = cluster.document_types || []
  const isCommentOnly = Boolean(documentTypes.length) && documentTypes.every((type) => type === 'social_comment')
  if (isCommentOnly && !hasTitleMatch && tokenOverlapCount < 2) {
    return 0
  }
  if (!hasTitleMatch && tokenOverlapCount < 2) {
    return 0
  }
  if (hasTitleMatch) {
    score += 30
  }
  if (cluster.last_published_at && event.published_at) {
    const gapHours = Math.abs(new Date(cluster.last_published_at).getTime() - new Date(event.published_at).getTime()) / 3600000
    score += Math.max(0, 10 - gapHours)
  }
  score += Math.min(8, Number(event.severity || 0) / 12)
  return score
}

const resolveClusterEvent = (cluster: EventCluster) => {
  const events = dashboard.value?.global_events || []
  const linkedIds = [
    cluster.linked_event_id,
    ...(cluster.event_ids || [])
  ].filter(Boolean) as string[]
  for (const eventId of linkedIds) {
    const linked = events.find((event) => event.event_id === eventId)
    if (linked) return linked
  }
  let bestEvent: GlobalEvent | null = null
  let bestScore = 0
  for (const event of events) {
    const score = scoreClusterEvent(cluster, event)
    if (score > bestScore) {
      bestScore = score
      bestEvent = event
    }
  }
  return bestScore >= 38 ? bestEvent : null
}

const buildLocalImpactChain = (event: GlobalEvent) => ({
  event_id: event.event_id,
  event_title: event.title,
  severity: event.severity,
  location_name: event.location_name || event.region || event.country,
  steps: [
    { label: '事件', value: event.summary || event.title },
    { label: '资产/变量', value: (event.affected_assets || []).slice(0, 4).join('、') || '等待资产响应确认' },
    { label: '传导渠道', value: (event.transmission_channels || []).slice(0, 4).join('、') || '等待传导渠道确认' },
    { label: 'A股主题', value: (event.mapped_themes || []).slice(0, 5).join('、') || '等待主题映射' },
    { label: '候选股票', value: (event.mapped_stocks || []).slice(0, 6).join('、') || '等待资金/量价确认' }
  ],
  mapped_themes: event.mapped_themes || [],
  mapped_stocks: []
})

const showMethodology = async () => {
  methodologyVisible.value = true
  if (methodology.value) return
  try {
    const response = await marketIntelligenceApi.getMethodology()
    methodology.value = response.data
  } catch (error) {
    console.error('加载方法论失败:', error)
    ElMessage.error('加载方法论失败')
  }
}

const stringify = (value?: Record<string, any>) => {
  if (!value) return '{}'
  try {
    return JSON.stringify(value, null, 2)
  } catch {
    return String(value)
  }
}

const formatTime = (value?: string | null) => {
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

const formatScore = (value?: number) => Number(value || 0).toFixed(1)

onMounted(() => {
  loadLatest()
  refreshTimer = window.setInterval(() => {
    loadLatest()
  }, 60000)
})

onBeforeUnmount(() => {
  if (refreshTimer) window.clearInterval(refreshTimer)
  Object.keys(analysisPollTimers).forEach(clearEventAnalysisPoll)
})
</script>

<style scoped lang="scss">
.market-intelligence {
  min-height: 100%;
  padding: 0;
  color: #dce7f7;
  background:
    linear-gradient(180deg, #0c1320 0%, #0d1521 48%, #101722 100%);
}

.page-header {
  display: grid;
  grid-template-columns: 1fr;
  align-items: start;
  gap: 16px;
  padding: 20px 22px;
  margin-bottom: 16px;
  border: 1px solid rgba(131, 160, 202, 0.18);
  border-radius: 8px;
  background:
    linear-gradient(90deg, rgba(20, 38, 64, 0.96), rgba(12, 20, 34, 0.96) 58%, rgba(16, 35, 44, 0.92));
  box-shadow: 0 18px 48px rgba(0, 0, 0, 0.24);

  > div:first-child {
    min-width: 0;
  }

  h1 {
    margin: 0;
    font-size: 28px;
    font-weight: 780;
    letter-spacing: 0;
    color: #f6f9ff;
    line-height: 1.22;
    word-break: keep-all;
    overflow-wrap: normal;
  }

  p {
    max-width: 760px;
    margin: 7px 0 0;
    color: #92a0b8;
    line-height: 1.55;
  }
}

.header-actions {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
  justify-content: flex-start;
  width: 100%;
  min-width: 0;
}

.hours-select {
  width: 124px;
}

.type-select {
  width: 138px;
}

.event-alert {
  margin-bottom: 14px;
}

.kpi-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 12px;
  margin-bottom: 14px;
}

.kpi-panel,
.summary-panel,
.panel {
  border: 1px solid rgba(148, 163, 184, 0.18);
  border-radius: 8px;
  background: rgba(12, 20, 33, 0.9);
  box-shadow: 0 16px 38px rgba(0, 0, 0, 0.22);
}

.kpi-panel {
  position: relative;
  overflow: hidden;
  padding: 15px;

  &::before {
    content: "";
    position: absolute;
    inset: 0 auto 0 0;
    width: 3px;
    background: #37d4b5;
  }

  &:nth-child(2)::before {
    background: #f16375;
  }

  &:nth-child(3)::before {
    background: #7aa7ff;
  }

  &:nth-child(4)::before {
    background: #f5b24c;
  }
}

.clickable {
  cursor: pointer;
  transition:
    border-color 0.2s ease,
    transform 0.2s ease;

  &:hover {
    border-color: rgba(120, 170, 255, 0.46);
    transform: translateY(-1px);
  }
}

.kpi-label,
.panel-header span {
  display: inline-flex;
  align-items: center;
  gap: 7px;
}

.kpi-label {
  color: #92a0b8;
  font-size: 13px;
}

.kpi-value {
  margin-top: 8px;
  font-size: 30px;
  font-weight: 760;
  color: #f4f8ff;

  &.danger {
    color: #ff7186;
  }
}

.kpi-sub {
  margin-top: 4px;
  color: #7d8aa3;
  font-size: 12px;
  line-height: 1.45;
}

.summary-panel {
  display: grid;
  grid-template-columns: 1fr auto;
  gap: 14px;
  align-items: center;
  padding: 16px;
  margin-bottom: 14px;
  background:
    linear-gradient(90deg, rgba(15, 30, 50, 0.94), rgba(12, 20, 33, 0.92));
}

.summary-title {
  font-weight: 720;
  color: #f4f8ff;
}

.summary-text {
  margin-top: 6px;
  color: #b9c5d8;
  line-height: 1.7;
}

.meta-pills {
  display: flex;
  flex-direction: column;
  gap: 8px;

  span {
    padding: 6px 9px;
    border-radius: 8px;
    border: 1px solid rgba(110, 150, 208, 0.18);
    background: rgba(57, 116, 216, 0.12);
    color: #a9b8d0;
    font-size: 12px;
    text-align: right;
  }
}

.main-grid,
.analysis-grid {
  display: grid;
  gap: 14px;
}

.source-panel,
.corridor-panel,
.cluster-panel {
  margin-bottom: 14px;
}

.cluster-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 10px;
}

.cluster-card {
  display: grid;
  gap: 7px;
  min-height: 104px;
  padding: 12px;
  text-align: left;
  border: 1px solid rgba(148, 163, 184, 0.16);
  border-radius: 8px;
  background:
    linear-gradient(180deg, rgba(16, 28, 46, 0.78), rgba(8, 14, 24, 0.76));
  color: inherit;
  cursor: pointer;

  &:hover {
    border-color: rgba(57, 116, 216, 0.55);
    background: rgba(57, 116, 216, 0.12);
  }

  &.active {
    border-color: rgba(96, 165, 250, 0.72);
    background: rgba(37, 99, 235, 0.18);
    box-shadow: inset 0 0 0 1px rgba(96, 165, 250, 0.2);
  }
}

.cluster-title {
  color: #f4f8ff;
  font-weight: 680;
  line-height: 1.45;
}

.cluster-meta {
  color: #8796af;
  font-size: 12px;
}

.cluster-link {
  overflow: hidden;
  color: #9fc7ff;
  font-size: 11px;
  line-height: 1.35;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.cluster-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 5px;
}

.main-grid {
  grid-template-columns: 1fr;
  margin-top: 14px;
}

.analysis-grid {
  grid-template-columns: minmax(0, 1.35fr) minmax(320px, 0.65fr);
  margin-top: 14px;

  &.bottom {
    grid-template-columns: 1fr;
  }
}

.panel {
  min-width: 0;
  padding: 15px;
}

.panel-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  min-height: 32px;
  margin-bottom: 13px;
  font-weight: 720;
  color: #f4f8ff;
  letter-spacing: 0;

  span {
    min-width: 0;
  }
}

.panel-actions {
  display: flex;
  align-items: center;
  gap: 4px;
}

.map-panel {
  min-height: 720px;
  padding: 12px;
  background:
    linear-gradient(180deg, rgba(11, 20, 34, 0.96), rgba(6, 12, 22, 0.98));
}

.impact-panel {
  min-height: 460px;
}

.stock-panel {
  margin-top: 14px;
}

.selected-event {
  padding: 12px;
  margin-bottom: 10px;
  border: 1px solid rgba(148, 163, 184, 0.16);
  border-radius: 8px;
  background:
    linear-gradient(180deg, rgba(20, 34, 55, 0.78), rgba(8, 14, 24, 0.7));

  h2 {
    margin: 10px 0 6px;
    font-size: 16px;
    line-height: 1.45;
    color: #f4f8ff;
  }

  p {
    margin: 0;
    color: #aab8cc;
    line-height: 1.6;
  }
}

.analysis-status {
  margin-top: 10px;
  padding: 8px 10px;
  border-radius: 8px;
  background: rgba(57, 116, 216, 0.14);
  color: #bdd4ff;
  font-size: 12px;
  line-height: 1.55;

  &.ready {
    background: rgba(31, 191, 143, 0.12);
    color: #8de0c6;
  }
}

.event-feed-panel {
  margin-top: 10px;
}

.event-top {
  display: flex;
  align-items: center;
  gap: 8px;
  color: #92a0b8;
  font-size: 12px;
}

.risk-list {
  display: grid;
  gap: 8px;
  margin-top: 8px;
}

.risk-item {
  padding: 9px 10px;
  border: 1px solid rgba(240, 163, 58, 0.18);
  border-radius: 8px;
  background: rgba(240, 163, 58, 0.08);
  color: #efc782;
  line-height: 1.55;
  font-size: 12px;
}

.report-panel {
  margin-top: 14px;

  pre {
    max-height: 420px;
    margin: 0;
    overflow: auto;
    color: #cbd6e7;
    white-space: pre-wrap;
    line-height: 1.7;
    font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
    font-size: 13px;
  }
}

.methodology {
  color: #1f2937;

  h3 {
    margin: 8px 0 10px;
    font-size: 15px;
  }

  pre {
    max-height: 320px;
    overflow: auto;
    padding: 12px;
    border-radius: 8px;
    background: #f7f9fc;
    white-space: pre-wrap;
    line-height: 1.6;
    font-size: 12px;
  }
}

:deep(.el-table) {
  --el-table-bg-color: transparent;
  --el-table-tr-bg-color: transparent;
  --el-table-header-bg-color: rgba(17, 24, 39, 0.96);
  --el-table-text-color: #cbd6e7;
  --el-table-header-text-color: #9fb0c8;
  --el-table-border-color: rgba(148, 163, 184, 0.16);
  border-radius: 8px;
}

:deep(.el-table th.el-table__cell) {
  background: rgba(14, 24, 39, 0.98);
}

:deep(.el-table tr:hover > td.el-table__cell) {
  background: rgba(57, 116, 216, 0.12);
}

:deep(.el-input__wrapper),
:deep(.el-select__wrapper) {
  background: rgba(15, 23, 36, 0.88);
  box-shadow: 0 0 0 1px rgba(148, 163, 184, 0.26) inset;
}

:deep(.el-button:not(.el-button--primary):not(.is-text)) {
  border-color: rgba(128, 159, 204, 0.28);
  background: rgba(13, 24, 40, 0.88);
  color: #d5e3f7;
}

:deep(.el-button:not(.el-button--primary):not(.is-text):hover) {
  border-color: rgba(96, 165, 250, 0.62);
  background: rgba(37, 99, 235, 0.22);
  color: #ffffff;
}

:deep(.el-button.is-text) {
  color: #9fc7ff;
}

:deep(.el-tag) {
  border-radius: 6px;
}

@media (max-width: 1180px) {
  .kpi-grid,
  .main-grid,
  .analysis-grid,
  .analysis-grid.bottom,
  .cluster-grid {
    grid-template-columns: 1fr;
  }

  .map-panel,
  .impact-panel {
    min-height: auto;
  }
}

@media (max-width: 760px) {
  .market-intelligence {
    padding: 0;
  }

  .page-header,
  .summary-panel {
    grid-template-columns: 1fr;
    display: grid;
  }

  .header-actions {
    justify-content: stretch;

    .el-button,
    .hours-select,
    .type-select {
      width: 100%;
    }
  }

  .kpi-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .meta-pills span {
    text-align: left;
  }
}
</style>
