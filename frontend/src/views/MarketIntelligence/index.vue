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
        <div class="kpi-panel">
          <div class="kpi-label"><el-icon><TrendCharts /></el-icon>市场温度</div>
          <div class="kpi-value">{{ formatScore(marketTemperature) }}</div>
          <div class="kpi-sub">主题均分 / 资金量价等待确认</div>
        </div>
        <div class="kpi-panel">
          <div class="kpi-label"><el-icon><WarningFilled /></el-icon>全球风险</div>
          <div class="kpi-value danger">{{ formatScore(globalRisk) }}</div>
          <div class="kpi-sub">{{ dashboard.global_events.length }} 个事件</div>
        </div>
        <div class="kpi-panel">
          <div class="kpi-label"><el-icon><Connection /></el-icon>数据覆盖</div>
          <div class="kpi-value">{{ dashboard.source_coverage.score }}%</div>
          <div class="kpi-sub">{{ dashboard.source_coverage.label }}</div>
        </div>
        <div class="kpi-panel">
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
            <el-button text size="small" :disabled="!selectedEvent" @click="drawerVisible = true">详情</el-button>
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
          </div>
          <TransmissionSankeyChart :chain="selectedChain" />
          <EventTimelineFeed
            v-if="dashboard.event_feed?.length"
            class="event-feed-panel"
            :items="dashboard.event_feed"
            :selected-event-id="selectedEventId"
            @select="selectedEventId = $event"
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

        <section class="panel">
          <div class="panel-header">
            <span><el-icon><Tickets /></el-icon>个股机会表</span>
            <el-tag v-if="selectedStock" effect="plain">{{ selectedStock.name }}({{ selectedStock.code }})</el-tag>
          </div>
          <StockOpportunityTable
            :stocks="dashboard.stock_opportunities"
            @select="handleStockSelect"
          />
        </section>
      </div>

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
      />
    </template>
  </div>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
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

const loading = ref(false)
const generating = ref(false)
const hours = ref(36)
const reportType = ref('pre_market')
const dashboard = ref<MarketIntelligenceDashboard | null>(null)
const selectedEventId = ref<string>()
const selectedTheme = ref<ThemeHeatmapNode | null>(null)
const selectedStock = ref<StockOpportunity | null>(null)
const selectedLayerIds = ref<string[]>([])
const drawerVisible = ref(false)
let refreshTimer: number | undefined

const staleSources = computed(() =>
  (dashboard.value?.crawler_statuses || []).filter((source) => !source.ok && Number(source.lag_minutes || 0) > 15)
)

const selectedEvent = computed(() => {
  const events = dashboard.value?.global_events || []
  return events.find((event) => event.event_id === selectedEventId.value) || events[0] || null
})

const selectedChain = computed(() => {
  const chains = dashboard.value?.event_impact_chains || []
  const eventId = selectedEvent.value?.event_id
  return chains.find((chain) => chain.event_id === eventId) || chains[0] || null
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
  selectedEventId.value = event.event_id
}

const handleStockSelect = (stock: StockOpportunity) => {
  selectedStock.value = stock
  ElMessage.info(`${stock.name}(${stock.code}) 已选中，可结合右侧证据和报告验证`)
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
})
</script>

<style scoped lang="scss">
.market-intelligence {
  min-height: 100%;
  padding: 22px;
  color: #dce7f7;
  background:
    linear-gradient(180deg, #101724 0%, #0f1724 42%, #111827 100%);
}

.page-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 16px;
  margin-bottom: 16px;

  h1 {
    margin: 0;
    font-size: 26px;
    font-weight: 750;
    letter-spacing: 0;
  }

  p {
    margin: 7px 0 0;
    color: #92a0b8;
    line-height: 1.55;
  }
}

.header-actions {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
  justify-content: flex-end;
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
  background: rgba(15, 23, 36, 0.86);
  box-shadow: 0 12px 34px rgba(0, 0, 0, 0.2);
}

.kpi-panel {
  padding: 15px;
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
  font-size: 28px;
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
.corridor-panel {
  margin-bottom: 14px;
}

.main-grid {
  grid-template-columns: minmax(0, 1.6fr) minmax(340px, 0.9fr);
}

.analysis-grid {
  grid-template-columns: minmax(0, 1.35fr) minmax(320px, 0.65fr);
  margin-top: 14px;

  &.bottom {
    grid-template-columns: minmax(320px, 0.75fr) minmax(0, 1.25fr);
  }
}

.panel {
  min-width: 0;
  padding: 14px;
}

.panel-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  min-height: 32px;
  margin-bottom: 12px;
  font-weight: 720;
  color: #f4f8ff;
}

.map-panel {
  min-height: 500px;
}

.impact-panel {
  min-height: 500px;
}

.selected-event {
  padding: 12px;
  margin-bottom: 10px;
  border: 1px solid rgba(148, 163, 184, 0.16);
  border-radius: 8px;
  background: rgba(2, 6, 23, 0.3);

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

:deep(.el-table) {
  --el-table-bg-color: transparent;
  --el-table-tr-bg-color: transparent;
  --el-table-header-bg-color: rgba(17, 24, 39, 0.96);
  --el-table-text-color: #cbd6e7;
  --el-table-header-text-color: #9fb0c8;
  --el-table-border-color: rgba(148, 163, 184, 0.16);
  border-radius: 8px;
}

:deep(.el-input__wrapper),
:deep(.el-select__wrapper) {
  background: rgba(15, 23, 36, 0.88);
  box-shadow: 0 0 0 1px rgba(148, 163, 184, 0.26) inset;
}

@media (max-width: 1180px) {
  .kpi-grid,
  .main-grid,
  .analysis-grid,
  .analysis-grid.bottom {
    grid-template-columns: 1fr;
  }

  .map-panel,
  .impact-panel {
    min-height: auto;
  }
}

@media (max-width: 760px) {
  .market-intelligence {
    padding: 14px;
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
