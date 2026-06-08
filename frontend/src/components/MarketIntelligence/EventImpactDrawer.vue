<template>
  <el-drawer
    :model-value="modelValue"
    size="460px"
    title="事件影响链"
    append-to-body
    @update:model-value="emit('update:modelValue', $event)"
  >
    <template v-if="event">
      <div class="event-title">{{ event.title }}</div>
      <div class="event-meta">
        <el-tag :type="severityTag(event.severity)">严重度 {{ Math.round(event.severity || 0) }}</el-tag>
        <el-tag v-if="event.intel_lens || event.source_category" type="success" effect="plain">
          {{ event.intel_lens || event.source_category }}
        </el-tag>
        <span>{{ event.location_name || event.country || '全球' }}</span>
        <span>{{ formatTime(event.published_at) }}</span>
      </div>
      <p class="event-summary">{{ event.summary || '暂无摘要' }}</p>

      <div class="section-title analysis-title">
        <span>AI 影响面分析</span>
        <el-button size="small" type="primary" plain :loading="isPending" :disabled="isPending" @click="emit('analyze')">
          {{ hasReadyAnalysis ? '重新分析' : isPending ? '分析中' : '开始分析' }}
        </el-button>
      </div>
      <div v-if="isPending" class="analysis-box loading">
        已加入队列，正在分析当前事件的资产变量、传导渠道、A股主题、个股映射和风险反证...
      </div>
      <div v-else-if="hasReadyAnalysis" class="analysis-box">
        <div class="analysis-meta">
          <el-tag size="small" effect="plain">{{ analysis.model || 'DashScope' }}</el-tag>
          <span>{{ formatTime(analysis.updated_at) }}</span>
          <el-tag v-if="analysis.fallback_used" size="small" type="warning" effect="plain">fallback</el-tag>
        </div>
        <div class="markdown-body" v-html="analysisHtml"></div>
      </div>
      <div v-else-if="analysis?.status === 'error'" class="analysis-box empty">
        当前事件分析失败，请稍后重新分析。
      </div>
      <div v-else class="analysis-box empty">
        当前事件尚未分析。点击“开始分析”后，将只基于这个事件加入队列生成影响链。
      </div>

      <div class="section-title">传导路径</div>
      <div v-if="chain?.steps?.length" class="step-list">
        <div v-for="(step, index) in chain.steps" :key="step.label" class="step-item">
          <div class="step-index">{{ index + 1 }}</div>
          <div>
            <div class="step-label">{{ step.label }}</div>
            <div class="step-value">{{ step.value || '-' }}</div>
          </div>
        </div>
      </div>

      <div class="section-title">映射主题</div>
      <div class="tag-list">
        <el-tag v-for="theme in event.mapped_themes || []" :key="theme" effect="plain">
          {{ theme }}
        </el-tag>
      </div>

      <div class="section-title">影响变量</div>
      <div class="tag-list">
        <el-tag v-for="asset in event.affected_assets || []" :key="asset" type="warning" effect="plain">
          {{ asset }}
        </el-tag>
      </div>

      <a v-if="event.url" class="source-link" :href="event.url" target="_blank" rel="noreferrer">
        查看原始来源
      </a>
    </template>
    <el-empty v-else description="暂无事件" />
  </el-drawer>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { marked } from 'marked'
import type { EventImpactAnalysis, EventImpactChain, GlobalEvent } from '@/api/marketIntelligence'

const props = defineProps<{
  modelValue: boolean
  event?: GlobalEvent | null
  chain?: EventImpactChain | null
  analysis?: EventImpactAnalysis | null
  analyzing?: boolean
}>()

const emit = defineEmits<{
  'update:modelValue': [value: boolean]
  analyze: []
}>()

const isPending = computed(() => props.analyzing || ['queued', 'running'].includes(props.analysis?.status || ''))
const hasReadyAnalysis = computed(() =>
  ['ready', 'partial'].includes(props.analysis?.status || '') && Boolean(props.analysis?.analysis_markdown)
)

const analysisHtml = computed(() => {
  const markdown = props.analysis?.analysis_markdown || ''
  if (!markdown) return ''
  try {
    return marked(markdown)
  } catch {
    return `<pre>${markdown}</pre>`
  }
})

const severityTag = (severity?: number) => {
  const value = Number(severity || 0)
  if (value >= 72) return 'danger'
  if (value >= 55) return 'warning'
  return 'info'
}

const formatTime = (value?: string) => {
  if (!value) return '-'
  return new Date(value).toLocaleString('zh-CN', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit'
  })
}
</script>

<style scoped lang="scss">
.event-title {
  font-size: 18px;
  font-weight: 700;
  line-height: 1.5;
  color: #182033;
}

.event-meta,
.tag-list {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
}

.event-meta {
  margin-top: 10px;
  color: #6b7280;
  font-size: 12px;
}

.event-summary {
  margin: 16px 0 0;
  line-height: 1.7;
  color: #3f4858;
}

.section-title {
  margin: 22px 0 10px;
  font-weight: 700;
  color: #182033;
}

.analysis-title {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.analysis-box {
  padding: 12px;
  border: 1px solid #dbe4f0;
  border-radius: 8px;
  background: #f8fafc;
  color: #334155;
  line-height: 1.7;

  &.loading {
    color: #1f6feb;
  }

  &.empty {
    color: #64748b;
  }
}

.analysis-meta {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 10px;
  color: #64748b;
  font-size: 12px;
}

.markdown-body {
  font-size: 13px;

  :deep(h1),
  :deep(h2),
  :deep(h3) {
    margin: 12px 0 8px;
    color: #182033;
  }

  :deep(p),
  :deep(li) {
    line-height: 1.75;
  }
}

.step-list {
  display: grid;
  gap: 12px;
}

.step-item {
  display: grid;
  grid-template-columns: 28px 1fr;
  gap: 10px;
  padding: 12px;
  border: 1px solid #e5e7eb;
  border-radius: 8px;
  background: #f8fafc;
}

.step-index {
  width: 28px;
  height: 28px;
  border-radius: 50%;
  display: grid;
  place-items: center;
  background: #1f6feb;
  color: #fff;
  font-weight: 700;
}

.step-label {
  font-weight: 650;
  color: #182033;
}

.step-value {
  margin-top: 4px;
  color: #556070;
  line-height: 1.6;
}

.source-link {
  display: inline-flex;
  margin-top: 24px;
  color: #1f6feb;
  text-decoration: none;
}
</style>
