import { ApiClient } from './request'
import type { ScoreBreakdown } from './marketIntelligence'

export interface InvestmentDirection {
  name: string
  score: number
  heat: number
  sentiment_score: number
  keywords: string[]
  headlines: string[]
}

export interface InvestmentStock {
  code: string
  name: string
  score: number
  source: string
  reason: string
  industry: string
  price?: number
  pct_chg?: number
  amount?: number
  news_sentiment: number
  social_sentiment: number
  news_count: number
  comment_count: number
  headlines: string[]
  comments: string[]
  prediction_horizon?: string
  price_in_penalty?: number
  score_breakdown?: ScoreBreakdown
}

export interface DailyNewsItem {
  title: string
  summary?: string
  content?: string
  source?: string
  url?: string
  publish_time?: string
  published_at_quality?: 'source' | 'estimated_from_url_or_title' | 'ingest_fallback' | string
  first_seen_at?: string
  ingested_at?: string
  data_source?: string
  sentiment?: string
  importance?: string
  category?: string
}

export interface DailyEventCluster {
  cluster_id: string
  title: string
  summary?: string
  item_count?: number
  themes?: string[]
  symbols?: string[]
  sources?: string[]
  last_published_at?: string
  avg_sentiment?: number
  items?: DailyNewsItem[]
}

export interface SourceStatus {
  name: string
  ok: boolean
  count: number
  message: string
}

export interface InvestmentDailyReport {
  _id?: string
  report_date: string
  generated_at: string
  title: string
  status: string
  summary: string
  market_temperature: {
    score: number
    label: string
    news_count: number
    avg_candidate_pct_chg: number
    score_breakdown?: ScoreBreakdown
  }
  directions: InvestmentDirection[]
  stocks: InvestmentStock[]
  market_news: DailyNewsItem[]
  international_news: DailyNewsItem[]
  event_clusters?: DailyEventCluster[]
  social_comments: Array<DailyNewsItem & { content: string; symbol?: string }>
  sources: SourceStatus[]
  risk_warnings: string[]
  markdown?: string
  preanalysis?: {
    submitted_at?: string
    task_ids?: string[]
    mapping?: Array<{ code: string; name?: string; task_id: string; status: string }>
  }
}

export const investmentDailyApi = {
  async getLatest() {
    return ApiClient.get<InvestmentDailyReport | null>('/api/investment-daily/latest')
  },

  async getHistory(limit: number = 20) {
    return ApiClient.get<{ reports: InvestmentDailyReport[]; count: number }>(
      '/api/investment-daily/history',
      { limit }
    )
  },

  async generate(forceRefresh: boolean = true) {
    return ApiClient.post<InvestmentDailyReport>(
      '/api/investment-daily/generate',
      undefined,
      {
        params: { force_refresh: forceRefresh },
        timeout: 180000,
        loadingText: '正在生成投资日报...'
      }
    )
  },

  async preanalyze(reportId: string, limit = 8) {
    return ApiClient.post<{ status: string; task_ids: string[]; mapping: any[]; count: number }>(
      `/api/investment-daily/${reportId}/preanalyze`,
      undefined,
      {
        params: { limit },
        timeout: 120000,
        loadingText: '正在提交候选股预分析...'
      }
    )
  },

  async download(reportId: string, format: 'pdf' | 'markdown' | 'json' = 'pdf', filename?: string) {
    return ApiClient.download(
      `/api/investment-daily/${reportId}/download`,
      filename || `investment_daily.${format === 'markdown' ? 'md' : format}`,
      { params: { format } }
    )
  }
}
