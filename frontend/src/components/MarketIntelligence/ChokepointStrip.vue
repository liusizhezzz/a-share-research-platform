<template>
  <div class="corridor-strip">
    <button
      v-for="item in corridors"
      :key="item.id"
      class="corridor-chip"
      :class="item.status"
      type="button"
      :title="item.latest_event || item.name"
    >
      <span class="status-dot"></span>
      <span class="chip-body">
        <span class="chip-title">
          {{ item.name }}
          <em v-if="item.active_warnings">{{ item.active_warnings }}</em>
        </span>
        <span class="chip-meta">{{ Math.round(item.risk_score) }} / {{ item.exposure.join('、') }}</span>
      </span>
    </button>
  </div>
</template>

<script setup lang="ts">
import type { CorridorRisk } from '@/api/marketIntelligence'

defineProps<{
  corridors: CorridorRisk[]
}>()
</script>

<style scoped lang="scss">
.corridor-strip {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.corridor-chip {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  min-width: 138px;
  max-width: 220px;
  padding: 8px 10px;
  border: 1px solid rgba(148, 163, 184, 0.18);
  border-radius: 8px;
  background: rgba(15, 23, 42, 0.66);
  color: #dce7f7;
  text-align: left;

  &.critical {
    border-color: rgba(239, 91, 111, 0.62);
    background: rgba(239, 91, 111, 0.12);
  }

  &.high {
    border-color: rgba(242, 168, 74, 0.56);
    background: rgba(242, 168, 74, 0.1);
  }

  &.elevated {
    border-color: rgba(34, 199, 169, 0.42);
  }
}

.status-dot {
  width: 9px;
  height: 9px;
  border-radius: 50%;
  flex: 0 0 auto;
  background: #7bd88f;
}

.critical .status-dot {
  background: #ef5b6f;
}

.high .status-dot {
  background: #f2a84a;
}

.elevated .status-dot {
  background: #22c7a9;
}

.chip-body {
  min-width: 0;
  display: grid;
  gap: 2px;
}

.chip-title,
.chip-meta {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.chip-title {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  font-size: 12px;
  font-weight: 720;

  em {
    min-width: 17px;
    height: 17px;
    padding: 0 5px;
    border-radius: 9px;
    background: #ef5b6f;
    color: #fff;
    font-style: normal;
    font-size: 10px;
    line-height: 17px;
    text-align: center;
  }
}

.chip-meta {
  color: #8fa1bb;
  font-size: 11px;
}
</style>

