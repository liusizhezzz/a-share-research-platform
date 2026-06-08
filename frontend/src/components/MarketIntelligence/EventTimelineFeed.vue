<template>
  <div class="event-feed">
    <button
      v-for="item in items"
      :key="item.event_id"
      type="button"
      class="feed-item"
      :class="{ active: item.event_id === selectedEventId, high: item.severity >= 72 }"
      @click="emit('select', item.event_id)"
    >
      <span class="feed-time">{{ formatTime(item.published_at) }}</span>
      <span class="feed-body">
        <span class="feed-title">{{ item.title }}</span>
        <span class="feed-meta">
          {{ item.location_name || '全球' }} · {{ item.intel_lens || item.source_category || item.source || '未知来源' }} · 严重度 {{ Math.round(item.severity || 0) }}
        </span>
      </span>
    </button>
  </div>
</template>

<script setup lang="ts">
import type { EventFeedItem } from '@/api/marketIntelligence'

defineProps<{
  items: EventFeedItem[]
  selectedEventId?: string
}>()

const emit = defineEmits<{
  select: [eventId: string]
}>()

const formatTime = (value?: string) => {
  if (!value) return '--:--'
  try {
    return new Date(value).toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })
  } catch {
    return '--:--'
  }
}
</script>

<style scoped lang="scss">
.event-feed {
  display: grid;
  gap: 8px;
  max-height: 292px;
  overflow: auto;
  padding-right: 2px;
}

.feed-item {
  display: grid;
  grid-template-columns: 44px 1fr;
  gap: 8px;
  width: 100%;
  padding: 9px;
  border: 1px solid rgba(148, 163, 184, 0.14);
  border-radius: 8px;
  background: rgba(2, 6, 23, 0.24);
  color: #dce7f7;
  text-align: left;
  cursor: pointer;

  &.active {
    border-color: rgba(96, 165, 250, 0.62);
    background: rgba(37, 99, 235, 0.14);
  }

  &.high {
    border-left: 3px solid #ef5b6f;
  }
}

.feed-time {
  color: #8fa1bb;
  font-size: 11px;
  line-height: 1.4;
}

.feed-body {
  min-width: 0;
  display: grid;
  gap: 4px;
}

.feed-title {
  overflow: hidden;
  color: #edf5ff;
  font-size: 12px;
  font-weight: 680;
  line-height: 1.45;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
}

.feed-meta {
  overflow: hidden;
  color: #8fa1bb;
  font-size: 11px;
  text-overflow: ellipsis;
  white-space: nowrap;
}
</style>
