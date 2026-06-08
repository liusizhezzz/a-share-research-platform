<template>
  <div class="event-map">
    <div ref="mapContainer" class="map-canvas"></div>
    <div v-if="fallbackMode" class="fallback-map">
      <button
        v-for="event in positionedEvents"
        :key="event.event_id"
        class="fallback-point"
        :class="{ active: event.event_id === selectedEventId, high: event.severity >= 72 }"
        :style="{ left: event.left, top: event.top }"
        :title="event.title"
        @click="emit('select', event)"
      >
        <span></span>
      </button>
    </div>
    <div class="map-legend">
      <span><i class="dot high"></i>高严重度</span>
      <span><i class="dot medium"></i>中等扰动</span>
      <span><i class="dot low"></i>观察</span>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import maplibregl from 'maplibre-gl'
import { MapboxOverlay } from '@deck.gl/mapbox'
import { ArcLayer, ScatterplotLayer } from '@deck.gl/layers'
import 'maplibre-gl/dist/maplibre-gl.css'
import type { GlobalEvent } from '@/api/marketIntelligence'

const props = defineProps<{
  events: GlobalEvent[]
  selectedEventId?: string
}>()

const emit = defineEmits<{
  select: [event: GlobalEvent]
}>()

const mapContainer = ref<HTMLDivElement>()
const fallbackMode = ref(false)
let map: maplibregl.Map | null = null
let overlay: MapboxOverlay | null = null
const darkMatterStyle = 'https://basemaps.cartocdn.com/gl/dark-matter-gl-style/style.json'

const positionedEvents = computed(() =>
  props.events.slice(0, 36).map((event) => ({
    ...event,
    left: `${Math.max(3, Math.min(97, ((Number(event.lon || 0) + 180) / 360) * 100))}%`,
    top: `${Math.max(6, Math.min(94, ((90 - Number(event.lat || 0)) / 180) * 100))}%`
  }))
)

const eventColor = (event: GlobalEvent) => {
  const severity = Number(event.severity || 0)
  if (severity >= 72) return [217, 75, 95, 230]
  if (severity >= 55) return [240, 163, 58, 220]
  return [58, 124, 220, 210]
}

const buildLayers = () => [
  new ArcLayer<GlobalEvent>({
    id: 'event-to-a-share-arcs',
    data: props.events.slice(0, 18),
    getSourcePosition: (event) => [Number(event.lon || 0), Number(event.lat || 0)],
    getTargetPosition: () => [116.4, 39.9],
    getSourceColor: (event) => eventColor(event) as [number, number, number, number],
    getTargetColor: [31, 191, 143, 120],
    getWidth: (event) => Math.max(1, Number(event.severity || 0) / 24),
    greatCircle: true,
    pickable: false
  }),
  new ScatterplotLayer<GlobalEvent>({
    id: 'global-events',
    data: props.events,
    getPosition: (event) => [Number(event.lon || 0), Number(event.lat || 0)],
    getRadius: (event) => Math.max(42000, Number(event.severity || 0) * 1400),
    radiusMinPixels: 5,
    radiusMaxPixels: 22,
    getFillColor: (event) => eventColor(event) as [number, number, number, number],
    getLineColor: [255, 255, 255, 220],
    lineWidthMinPixels: 1,
    stroked: true,
    filled: true,
    pickable: true,
    onClick: (info) => {
      if (info.object) emit('select', info.object)
      return true
    }
  })
]

const syncLayers = () => {
  if (!overlay) return
  overlay.setProps({ layers: buildLayers() })
}

onMounted(async () => {
  await nextTick()
  if (!mapContainer.value) return

  try {
    map = new maplibregl.Map({
      container: mapContainer.value,
      style: darkMatterStyle,
      center: [42, 24],
      zoom: 1.15,
      attributionControl: false,
      dragRotate: false,
      pitchWithRotate: false
    })
    map.addControl(new maplibregl.NavigationControl({ showCompass: false }), 'top-right')
    overlay = new MapboxOverlay({ layers: buildLayers() })
    map.addControl(overlay)
  } catch (error) {
    console.warn('全球事件地图加载失败，使用降级渲染:', error)
    fallbackMode.value = true
  }
})

onBeforeUnmount(() => {
  if (overlay && map) {
    try {
      map.removeControl(overlay)
    } catch (error) {
      console.debug('移除地图覆盖层失败:', error)
    }
  }
  map?.remove()
  overlay = null
  map = null
})

watch(
  () => props.events,
  () => syncLayers(),
  { deep: true }
)
</script>

<style scoped lang="scss">
.event-map {
  position: relative;
  min-height: 430px;
  height: 100%;
  overflow: hidden;
  border-radius: 8px;
  background:
    linear-gradient(180deg, rgba(10, 18, 30, 0.85), rgba(10, 18, 30, 0.95)),
    #0b1320;
}

.map-canvas,
.fallback-map {
  position: absolute;
  inset: 0;
}

.fallback-map {
  background:
    linear-gradient(90deg, rgba(255, 255, 255, 0.04) 1px, transparent 1px),
    linear-gradient(0deg, rgba(255, 255, 255, 0.04) 1px, transparent 1px),
    radial-gradient(circle at 30% 35%, rgba(57, 116, 216, 0.18), transparent 28%),
    #0b1320;
  background-size: 48px 48px, 48px 48px, auto, auto;
}

.fallback-point {
  position: absolute;
  width: 22px;
  height: 22px;
  transform: translate(-50%, -50%);
  border: none;
  border-radius: 50%;
  background: rgba(57, 116, 216, 0.18);
  cursor: pointer;

  span {
    position: absolute;
    inset: 6px;
    border-radius: 50%;
    background: #3974d8;
    box-shadow: 0 0 0 4px rgba(57, 116, 216, 0.18);
  }

  &.high span {
    background: #d94b5f;
    box-shadow: 0 0 0 6px rgba(217, 75, 95, 0.2);
  }

  &.active {
    outline: 2px solid #fff;
    outline-offset: 3px;
  }
}

.map-legend {
  position: absolute;
  left: 16px;
  bottom: 14px;
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 12px;
  padding: 8px 10px;
  border: 1px solid rgba(255, 255, 255, 0.14);
  border-radius: 8px;
  background: rgba(8, 14, 24, 0.72);
  color: #d8e3f7;
  font-size: 12px;
  backdrop-filter: blur(8px);
}

.dot {
  display: inline-block;
  width: 8px;
  height: 8px;
  margin-right: 6px;
  border-radius: 50%;

  &.high {
    background: #d94b5f;
  }

  &.medium {
    background: #f0a33a;
  }

  &.low {
    background: #3974d8;
  }
}
</style>
