<template>
  <div class="layer-rail">
    <button
      v-for="layer in layers"
      :key="layer.id"
      class="layer-chip"
      :class="{ selected: selectedIds.includes(layer.id), inactive: !layer.active }"
      type="button"
      @click="toggle(layer.id)"
    >
      <span class="layer-dot" :style="{ backgroundColor: layer.color }"></span>
      <span class="layer-main">
        <span class="layer-name">{{ layer.label }}</span>
        <span class="layer-meta">{{ layer.event_count }} 事件 / {{ Math.round(layer.max_severity || 0) }}</span>
      </span>
    </button>
  </div>
</template>

<script setup lang="ts">
import type { MapLayerDefinition } from '@/api/marketIntelligence'

const props = defineProps<{
  layers: MapLayerDefinition[]
  selectedIds: string[]
}>()

const emit = defineEmits<{
  'update:selectedIds': [ids: string[]]
}>()

const toggle = (id: string) => {
  const current = new Set(props.selectedIds)
  if (current.has(id)) {
    current.delete(id)
  } else {
    current.add(id)
  }
  emit('update:selectedIds', Array.from(current))
}
</script>

<style scoped lang="scss">
.layer-rail {
  display: flex;
  gap: 8px;
  overflow-x: auto;
  padding: 2px 0 10px;
}

.layer-chip {
  flex: 0 0 auto;
  display: inline-flex;
  align-items: center;
  gap: 8px;
  min-width: 132px;
  max-width: 180px;
  padding: 8px 10px;
  border: 1px solid rgba(148, 163, 184, 0.2);
  border-radius: 8px;
  background: rgba(17, 24, 39, 0.68);
  color: #dce7f7;
  text-align: left;
  cursor: pointer;
  transition: border-color 0.18s ease, background 0.18s ease, opacity 0.18s ease;

  &.selected {
    border-color: rgba(96, 165, 250, 0.72);
    background: rgba(37, 99, 235, 0.18);
  }

  &.inactive {
    opacity: 0.54;
  }
}

.layer-dot {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  flex: 0 0 auto;
  box-shadow: 0 0 0 4px rgba(255, 255, 255, 0.06);
}

.layer-main {
  min-width: 0;
  display: grid;
  gap: 2px;
}

.layer-name,
.layer-meta {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.layer-name {
  font-size: 12px;
  font-weight: 720;
}

.layer-meta {
  color: #8fa1bb;
  font-size: 11px;
}
</style>

