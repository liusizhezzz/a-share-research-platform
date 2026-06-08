import { ApiClient } from './request'

export interface SourceCoverage {
  score: number
  ok_count: number
  total: number
  label: string
}

export interface GlobalEvent {
  _id?: string
  event_id: string
  event_type: string
  title: string
  summary?: string
  source?: string
  url?: string
  published_at?: string
  lat: number
  lon: number
  country?: string
  region?: string
  location_name?: string
  severity: number
  confidence?: number
  affected_assets?: string[]
  transmission_channels?: string[]
  mapped_themes?: string[]
  mapped_stocks?: string[]
  map_layers?: string[]
}

export interface MapLayerDefinition {
  id: string
  label: string
  description?: string
  color: string
  active: boolean
  event_count: number
  max_severity: number
  theme_score?: number
  renderers?: string[]
}

export interface EventFeedItem {
  event_id: string
  title: string
  summary?: string
  source?: string
  published_at?: string
  severity: number
  severity_label: string
  location_name?: string
  layers?: string[]
  mapped_themes?: string[]
  affected_assets?: string[]
}

export interface CorridorRisk {
  id: string
  name: string
  region: string
  lat: number
  lon: number
  status: 'normal' | 'elevated' | 'high' | 'critical' | string
  risk_score: number
  event_count: number
  active_warnings: number
  exposure: string[]
  a_share_themes: string[]
  latest_event?: string
}

export interface SourceEnvelope {
  id: string
  label: string
  schema_version: number
  state: 'fresh' | 'stale' | 'empty' | string
  record_count: number
  newest_item_at?: string
  oldest_item_at?: string
  max_content_age_min: number
  age_minutes?: number | null
  failed_datasets?: string[]
  source_version?: string
}

export interface EventImpactStep {
  label: string
  value: string
}

export interface EventImpactChain {
  event_id: string
  event_title: string
  severity: number
  location_name?: string
  steps: EventImpactStep[]
  mapped_themes?: string[]
  mapped_stocks?: StockOpportunity[]
}

export interface ThemeHeatmapNode {
  name: string
  value: number
  score: number
  heat: number
  sentiment_score: number
  news_count: number
  event_count: number
  risk_score: number
  trend: string
  keywords?: string[]
  headlines?: string[]
}

export interface IndustryMatrixCell {
  theme: string
  dimension: string
  value: number
}

export interface StockOpportunity {
  code: string
  name: string
  industry?: string
  theme?: string
  score: number
  signal_strength?: number
  news_count?: number
  comment_count?: number
  research_count?: number
  announcement_count?: number
  quant_count?: number
  sentiment_score?: number
  funds_score?: number
  price_score?: number
  risk_score?: number
  pct_chg?: number
  amount?: number
  price?: number
  headlines?: string[]
  documents?: MarketDocument[]
}

export interface MarketDocument {
  doc_key?: string
  document_type?: string
  title: string
  content?: string
  summary?: string
  source?: string
  data_source?: string
  url?: string
  published_at?: string
  symbols?: string[]
  themes?: string[]
  sentiment?: string
  sentiment_score?: number
  influence_score?: number
}

export interface CrawlerStatus {
  name: string
  ok: boolean
  last_success_at?: string
  last_run_at?: string
  lag_minutes: number
  fetched?: number
  saved?: number
  failed?: number
  message?: string
}

export interface MarketIntelligenceDashboard {
  status: string
  summary: string
  last_ingested_at?: string | null
  last_report_generated_at?: string | null
  source_coverage: SourceCoverage
  has_high_severity_event: boolean
  global_events: GlobalEvent[]
  event_impact_chains: EventImpactChain[]
  map_layers?: MapLayerDefinition[]
  event_feed?: EventFeedItem[]
  corridor_strip?: CorridorRisk[]
  source_envelopes?: SourceEnvelope[]
  theme_heatmap_nodes: ThemeHeatmapNode[]
  industry_matrix: IndustryMatrixCell[]
  stock_opportunities: StockOpportunity[]
  risk_warnings: string[]
  crawler_statuses: CrawlerStatus[]
  markdown_report?: string
}

export interface MarketIntelligenceReport {
  _id?: string
  report_type: string
  report_date: string
  generated_at: string
  title: string
  status: string
  summary: string
  dashboard: MarketIntelligenceDashboard
  markdown_report: string
  version: number
}

export const marketIntelligenceApi = {
  getLatest(hours = 36) {
    return ApiClient.get<MarketIntelligenceDashboard>('/api/market-intelligence/latest', { hours })
  },

  generate(reportType = 'pre_market', forceRefresh = true) {
    return ApiClient.post<MarketIntelligenceReport>(
      '/api/market-intelligence/generate',
      undefined,
      {
        params: { report_type: reportType, force_refresh: forceRefresh },
        timeout: 240000,
        loadingText: '正在生成市场情报报告...'
      }
    )
  },

  getHistory(limit = 20) {
    return ApiClient.get<{ reports: MarketIntelligenceReport[]; count: number }>(
      '/api/market-intelligence/history',
      { limit }
    )
  },

  getGlobalEvents(hours = 36, severity = 'all') {
    return ApiClient.get<{ events: GlobalEvent[]; count: number }>(
      '/api/market-intelligence/global-events',
      { hours, severity }
    )
  },

  getGlobalEvent(eventId: string) {
    return ApiClient.get<GlobalEvent>(`/api/market-intelligence/global-events/${eventId}`)
  },

  getThemes() {
    return ApiClient.get<{ themes: ThemeHeatmapNode[]; count: number }>(
      '/api/market-intelligence/themes'
    )
  },

  getStock(code: string) {
    return ApiClient.get<StockOpportunity>(`/api/market-intelligence/stocks/${code}`)
  },

  getStockEvidence(code: string, hours = 36, companyName = '') {
    return ApiClient.get<{ code: string; hours: number; evidence_markdown: string }>(
      `/api/market-intelligence/stocks/${code}/evidence`,
      { hours, company_name: companyName }
    )
  },

  refreshStockEvidence(code: string, companyName = '') {
    return ApiClient.post<{ code: string; documents_seen: number; documents_saved: number; status: string }>(
      `/api/market-intelligence/stocks/${code}/refresh-evidence`,
      undefined,
      {
        params: { company_name: companyName },
        timeout: 120000,
        loadingText: '正在刷新个股新闻和舆情...'
      }
    )
  },

  getSourceStatus() {
    return ApiClient.get<{ sources: CrawlerStatus[]; count: number }>(
      '/api/market-intelligence/sources/status'
    )
  }
}
