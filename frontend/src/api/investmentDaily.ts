import { ApiClient } from './request'

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
}

export interface DailyNewsItem {
  title: string
  summary?: string
  content?: string
  source?: string
  url?: string
  publish_time?: string
  sentiment?: string
  importance?: string
  category?: string
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
  }
  directions: InvestmentDirection[]
  stocks: InvestmentStock[]
  market_news: DailyNewsItem[]
  international_news: DailyNewsItem[]
  social_comments: Array<DailyNewsItem & { content: string; symbol?: string }>
  sources: SourceStatus[]
  risk_warnings: string[]
  markdown?: string
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
  }
}
