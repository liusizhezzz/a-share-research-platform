<template>
  <div class="source-envelope-grid">
    <div
      v-for="source in sources"
      :key="source.id"
      class="source-envelope"
      :class="source.state"
    >
      <div class="source-top">
        <span>{{ source.label }}</span>
        <i>{{ stateLabel(source.state) }}</i>
      </div>
      <div class="source-count">{{ source.record_count }}</div>
      <div class="source-meta">
        {{ ageLabel(source.age_minutes) }} / 阈值 {{ source.max_content_age_min }}m
      </div>
      <div v-if="source.source_count !== undefined" class="source-meta">
        {{ source.source_count }} 个源
      </div>
      <div v-if="topCategories(source).length" class="source-categories">
        <span v-for="item in topCategories(source)" :key="item[0]">
          {{ item[0] }} {{ item[1] }}
        </span>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import type { SourceEnvelope } from '@/api/marketIntelligence'

defineProps<{
  sources: SourceEnvelope[]
}>()

const stateLabel = (state: string) => {
  if (state === 'fresh') return '新鲜'
  if (state === 'stale') return '滞后'
  if (state === 'empty') return '空'
  return state
}

const ageLabel = (minutes?: number | null) => {
  if (minutes === null || minutes === undefined) return '无时间'
  if (minutes < 60) return `${minutes}m`
  return `${Math.floor(minutes / 60)}h${minutes % 60}m`
}

const topCategories = (source: SourceEnvelope) =>
  Object.entries(source.category_counts || {})
    .sort((a, b) => Number(b[1]) - Number(a[1]))
    .slice(0, 3)
</script>

<style scoped lang="scss">
.source-envelope-grid {
  display: grid;
  grid-template-columns: repeat(6, minmax(0, 1fr));
  gap: 8px;
}

.source-envelope {
  min-width: 0;
  padding: 10px;
  border: 1px solid rgba(148, 163, 184, 0.16);
  border-radius: 8px;
  background: rgba(15, 23, 42, 0.58);

  &.fresh {
    border-color: rgba(34, 199, 169, 0.34);
  }

  &.stale {
    border-color: rgba(242, 168, 74, 0.48);
    background: rgba(242, 168, 74, 0.08);
  }

  &.empty {
    opacity: 0.72;
  }
}

.source-top {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  color: #dce7f7;
  font-size: 12px;
  font-weight: 700;

  span {
    min-width: 0;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  i {
    flex: 0 0 auto;
    color: #8fa1bb;
    font-style: normal;
    font-size: 11px;
  }
}

.source-count {
  margin-top: 7px;
  color: #f5f9ff;
  font-size: 22px;
  font-weight: 760;
}

.source-meta {
  margin-top: 3px;
  overflow: hidden;
  color: #8fa1bb;
  font-size: 11px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.source-categories {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  margin-top: 7px;

  span {
    max-width: 100%;
    padding: 2px 5px;
    overflow: hidden;
    border: 1px solid rgba(96, 165, 250, 0.22);
    border-radius: 6px;
    color: #a9c9ff;
    font-size: 10px;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
}

@media (max-width: 1180px) {
  .source-envelope-grid {
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }
}

@media (max-width: 760px) {
  .source-envelope-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}
</style>
