<template>
  <div class="event-map">
    <div class="wm-map-toolbar">
      <div class="wm-toolbar-group">
        <button
          v-for="view in viewPresets"
          :key="view.id"
          class="wm-chip"
          :class="{ active: activeView === view.id }"
          type="button"
          @click="setMapView(view.id)"
        >
          {{ view.label }}
        </button>
      </div>
      <div class="wm-toolbar-group">
        <button
          v-for="basemap in basemaps"
          :key="basemap.id"
          class="wm-chip basemap"
          :class="{ active: activeBasemap === basemap.id }"
          type="button"
          :title="basemap.detail"
          @click="setBasemap(basemap.id)"
        >
          {{ basemap.label }}
        </button>
        <button class="wm-chip focus" type="button" @click="fitEvents">聚焦事件</button>
      </div>
    </div>
    <div ref="mapContainer" class="map-canvas"></div>
    <div v-if="fallbackMode" class="fallback-map">
      <svg class="fallback-world" viewBox="0 0 1000 520" aria-hidden="true">
        <path
          v-for="line in fallbackGridLines"
          :key="line"
          :d="line"
          class="fallback-grid-line"
        />
        <path
          v-for="land in fallbackLandPaths"
          :key="land"
          :d="land"
          class="fallback-land"
        />
      </svg>
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
        <em>{{ event.location_name || event.country || event.region || '事件' }}</em>
      </button>
    </div>
    <div v-if="selectedEvent" class="selected-map-card">
      <div class="selected-card-top">
        <span :class="['severity-pill', selectedEvent.severity >= 72 ? 'high' : selectedEvent.severity >= 55 ? 'medium' : 'low']">
          {{ Math.round(selectedEvent.severity || 0) }}
        </span>
        <strong>{{ selectedEvent.location_name || selectedEvent.country || selectedEvent.region || '全球事件' }}</strong>
      </div>
      <p>{{ selectedEvent.title }}</p>
      <div class="selected-card-tags">
        <span v-for="tag in selectedEvent.mapped_themes?.slice(0, 3)" :key="tag">{{ tag }}</span>
      </div>
    </div>
    <div class="map-legend">
      <span><i class="dot high"></i>高严重度</span>
      <span><i class="dot medium"></i>中等扰动</span>
      <span><i class="dot low"></i>观察</span>
      <span class="wm-source">World Monitor map kit</span>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import maplibregl from 'maplibre-gl'
import { MapboxOverlay } from '@deck.gl/mapbox'
import { PathLayer, ScatterplotLayer, TextLayer } from '@deck.gl/layers'
import 'maplibre-gl/dist/maplibre-gl.css'
import type { GlobalEvent } from '@/api/marketIntelligence'
import {
  WORLD_MONITOR_BASEMAPS,
  WORLD_MONITOR_LAYER_ZOOM_THRESHOLDS,
  WORLD_MONITOR_VIEW_PRESETS,
  escapeMapHtml,
  getWorldMonitorBasemap,
  getWorldMonitorViewPreset,
  interpolateGreatCircle,
  localizeMapLabels,
  type WorldMonitorBasemapId,
  type WorldMonitorViewId
} from '@/utils/worldMonitorMapKit'

const props = defineProps<{
  events: GlobalEvent[]
  selectedEventId?: string
}>()

const emit = defineEmits<{
  select: [event: GlobalEvent]
}>()

const mapContainer = ref<HTMLDivElement>()
const fallbackMode = ref(false)
const activeBasemap = ref<WorldMonitorBasemapId>(
  (localStorage.getItem('market-intelligence-basemap') as WorldMonitorBasemapId | null) || 'carto-vector'
)
const activeView = ref<WorldMonitorViewId>('global')
let map: maplibregl.Map | null = null
let overlay: MapboxOverlay | null = null
let basemapReady = false
let basemapWatchdog: number | undefined

const basemaps = WORLD_MONITOR_BASEMAPS
const viewPresets = WORLD_MONITOR_VIEW_PRESETS

const landPolygons = [
  [[-168, 70], [-145, 72], [-126, 60], [-124, 48], [-112, 33], [-97, 24], [-82, 27], [-72, 42], [-54, 50], [-52, 61], [-72, 70], [-104, 74], [-138, 72], [-168, 70]],
  [[-88, 22], [-76, 19], [-68, 10], [-62, 8], [-72, 3], [-84, 9], [-88, 22]],
  [[-82, 10], [-68, 8], [-52, -5], [-36, -20], [-45, -38], [-55, -55], [-70, -52], [-78, -28], [-82, 10]],
  [[-54, 76], [-20, 73], [-20, 61], [-42, 58], [-60, 66], [-54, 76]],
  [[-12, 36], [5, 49], [30, 56], [55, 55], [82, 58], [112, 54], [145, 47], [160, 35], [146, 22], [122, 18], [106, 6], [78, 7], [58, 20], [38, 31], [18, 42], [-4, 40], [-12, 36]],
  [[-18, 36], [8, 36], [32, 30], [50, 12], [43, -32], [22, -35], [2, -29], [-15, -6], [-18, 36]],
  [[42, 31], [58, 28], [57, 16], [48, 12], [38, 18], [42, 31]],
  [[68, 24], [88, 23], [94, 8], [78, 6], [68, 24]],
  [[102, 23], [124, 20], [126, 2], [108, -5], [100, 8], [102, 23]],
  [[112, -11], [154, -11], [154, -38], [132, -44], [112, -32], [112, -11]],
  [[166, -34], [179, -38], [174, -46], [162, -44], [166, -34]]
]

const projectPoint = ([lon, lat]: [number, number]) => [
  ((lon + 180) / 360) * 1000,
  ((84 - lat) / 164) * 520
]

const fallbackLandPaths = landPolygons.map((polygon) => {
  const points = polygon.map((point) => projectPoint(point as [number, number]))
  return `${points.map(([x, y], index) => `${index === 0 ? 'M' : 'L'}${x.toFixed(1)} ${y.toFixed(1)}`).join(' ')} Z`
})

const fallbackGridLines = [
  ...[-120, -60, 0, 60, 120].map((lon) => {
    const [x1, y1] = projectPoint([lon, -62])
    const [x2, y2] = projectPoint([lon, 76])
    return `M${x1.toFixed(1)} ${y1.toFixed(1)} L${x2.toFixed(1)} ${y2.toFixed(1)}`
  }),
  ...[-40, 0, 40].map((lat) => {
    const [x1, y1] = projectPoint([-180, lat])
    const [x2, y2] = projectPoint([180, lat])
    return `M${x1.toFixed(1)} ${y1.toFixed(1)} L${x2.toFixed(1)} ${y2.toFixed(1)}`
  })
]

const positionedEvents = computed(() =>
  props.events.slice(0, 36).map((event) => ({
    ...event,
    left: `${Math.max(3, Math.min(97, ((Number(event.lon || 0) + 180) / 360) * 100))}%`,
    top: `${Math.max(6, Math.min(94, ((90 - Number(event.lat || 0)) / 180) * 100))}%`
  }))
)

const selectedEvent = computed(() =>
  props.events.find((event) => event.event_id === props.selectedEventId) || null
)

const eventColor = (event: GlobalEvent) => {
  const severity = Number(event.severity || 0)
  if (severity >= 72) return [217, 75, 95, 230]
  if (severity >= 55) return [240, 163, 58, 220]
  return [58, 124, 220, 210]
}

const eventPosition = (event: GlobalEvent): [number, number] => [
  Number(event.lon || 0),
  Number(event.lat || 0)
]

const validEvents = computed(() =>
  props.events.filter((event) => {
    const [lon, lat] = eventPosition(event)
    return Number.isFinite(lon) && Number.isFinite(lat) && Math.abs(lon) <= 180 && Math.abs(lat) <= 90
  })
)

const labelEvents = computed(() => {
  const zoom = map?.getZoom() || 0
  const limit = zoom >= WORLD_MONITOR_LAYER_ZOOM_THRESHOLDS.denseLabels ? 80 : 32
  return validEvents.value
    .slice()
    .sort((a, b) => Number(b.severity || 0) - Number(a.severity || 0))
    .slice(0, limit)
})

const eventRoutes = computed(() =>
  validEvents.value.slice(0, 24).map((event) => ({
    ...event,
    path: interpolateGreatCircle(eventPosition(event), [116.4, 39.9], 28)
  }))
)

const buildLayers = () => [
  new PathLayer<GlobalEvent & { path: [number, number][] }>({
    id: 'wm-event-transmission-paths',
    data: eventRoutes.value,
    getPath: (event) => event.path,
    getColor: (event) => {
      const color = eventColor(event)
      return [color[0], color[1], color[2], 118]
    },
    getWidth: (event) => Math.max(1, Number(event.severity || 0) / 24),
    widthMinPixels: 1,
    widthMaxPixels: 5,
    jointRounded: true,
    capRounded: true,
    pickable: false
  }),
  new ScatterplotLayer<GlobalEvent>({
    id: 'wm-event-halos',
    data: validEvents.value,
    getPosition: eventPosition,
    getRadius: (event) => Math.max(70000, Number(event.severity || 0) * 2200),
    radiusMinPixels: 11,
    radiusMaxPixels: 42,
    getFillColor: (event) => {
      const color = eventColor(event)
      return [color[0], color[1], color[2], event.event_id === props.selectedEventId ? 88 : 34]
    },
    stroked: false,
    filled: true,
    pickable: false
  }),
  new ScatterplotLayer<GlobalEvent>({
    id: 'wm-global-events',
    data: validEvents.value,
    getPosition: eventPosition,
    getRadius: (event) => Math.max(42000, Number(event.severity || 0) * 1400),
    radiusMinPixels: 5,
    radiusMaxPixels: 28,
    getFillColor: (event) => eventColor(event) as [number, number, number, number],
    getLineColor: (event) => event.event_id === props.selectedEventId ? [255, 255, 255, 245] : [225, 238, 255, 180],
    getLineWidth: (event) => (event.event_id === props.selectedEventId ? 3 : 1),
    lineWidthMinPixels: 1,
    lineWidthMaxPixels: 4,
    stroked: true,
    filled: true,
    pickable: true,
    onClick: (info) => {
      if (info.object) emit('select', info.object)
      return true
    }
  }),
  new TextLayer<GlobalEvent>({
    id: 'wm-global-event-labels',
    data: labelEvents.value,
    getPosition: eventPosition,
    getText: (event) => event.location_name || event.country || event.region || event.title.slice(0, 8),
    characterSet: 'auto',
    fontFamily: 'system-ui, -apple-system, BlinkMacSystemFont, "PingFang SC", "Microsoft YaHei", sans-serif',
    getSize: (event) => (event.event_id === props.selectedEventId ? 14 : 11),
    getColor: (event) => (event.event_id === props.selectedEventId ? [255, 255, 255, 245] : [197, 211, 231, 210]),
    getAngle: 0,
    getTextAnchor: 'start',
    getAlignmentBaseline: 'center',
    getPixelOffset: [12, -12],
    background: true,
    getBackgroundColor: (event) =>
      event.event_id === props.selectedEventId ? [24, 37, 58, 230] : [8, 14, 24, 160],
    backgroundPadding: [4, 2],
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

const initializeDeckOverlay = () => {
  if (!map || overlay) return

  try {
    overlay = new MapboxOverlay({
      interleaved: true,
      layers: buildLayers(),
      getTooltip: buildTooltip,
      pickingRadius: 10,
      onError: (error: Error) => {
        console.warn('World Monitor deck 图层渲染告警:', error.message)
      }
    })
    map.addControl(overlay as unknown as maplibregl.IControl)
  } catch (error) {
    console.warn('World Monitor deck 图层初始化失败，保留底图继续渲染:', error)
    overlay = null
  }
}

const buildTooltip = (info: { object?: GlobalEvent } | null) => {
  const event = info?.object
  if (!event) return null
  const severity = Math.round(Number(event.severity || 0))
  const tags = [...(event.mapped_themes || []), ...(event.affected_assets || [])].slice(0, 5)
  return {
    html: `
      <div class="wm-map-tooltip">
        <div class="wm-map-tooltip-top">
          <span>严重度 ${severity}</span>
          <strong>${escapeMapHtml(event.location_name || event.country || event.region || '全球事件')}</strong>
        </div>
        <h4>${escapeMapHtml(event.title)}</h4>
        ${event.summary ? `<p>${escapeMapHtml(event.summary)}</p>` : ''}
        ${tags.length ? `<div class="wm-map-tooltip-tags">${tags.map((tag) => `<em>${escapeMapHtml(tag)}</em>`).join('')}</div>` : ''}
      </div>
    `
  }
}

const clearBasemapWatchdog = () => {
  if (basemapWatchdog) {
    window.clearTimeout(basemapWatchdog)
    basemapWatchdog = undefined
  }
}

const markBasemapReady = () => {
  if (!map || basemapReady) return
  basemapReady = true
  clearBasemapWatchdog()
  const basemap = getWorldMonitorBasemap(activeBasemap.value)
  if (basemap.localizable) localizeMapLabels(map)
  fallbackMode.value = false
  window.requestAnimationFrame(() => {
    if (!map) return
    try {
      map.resize()
    } catch (error) {
      console.warn('World Monitor 地图 resize 告警:', error)
    }
  })
  syncLayers()
}

const scheduleBasemapFallback = () => {
  clearBasemapWatchdog()
  basemapWatchdog = window.setTimeout(() => {
    if (basemapReady || !map || activeBasemap.value === 'gaode-cn') return
    console.warn('World Monitor 矢量底图加载较慢，切换中文详图兜底')
    setBasemap('gaode-cn')
  }, 14000)
}

const setBasemap = (id: WorldMonitorBasemapId) => {
  activeBasemap.value = id
  localStorage.setItem('market-intelligence-basemap', id)
  const basemap = getWorldMonitorBasemap(id)
  basemapReady = false
  if (!map) return
  try {
    map.setStyle(basemap.style)
    scheduleBasemapFallback()
    map.once('style.load', markBasemapReady)
    map.once('idle', markBasemapReady)
  } catch (error) {
    console.warn('切换底图失败，使用中文详图兜底:', error)
    if (id !== 'gaode-cn') setBasemap('gaode-cn')
  }
}

const setMapView = (id: WorldMonitorViewId) => {
  activeView.value = id
  const preset = getWorldMonitorViewPreset(id)
  map?.jumpTo({
    center: preset.center,
    zoom: preset.zoom
  })
  map?.resize()
  syncLayers()
}

const fitEvents = () => {
  if (!map || !validEvents.value.length) return
  const bounds = new maplibregl.LngLatBounds()
  validEvents.value.forEach((event) => bounds.extend(eventPosition(event)))
  if (bounds.isEmpty()) return
  map.fitBounds(bounds, {
    padding: { top: 86, right: 74, bottom: 54, left: 74 },
    maxZoom: 3.8,
    essential: true
  })
}

onMounted(async () => {
  await nextTick()
  if (!mapContainer.value) return

  const initialBasemap = getWorldMonitorBasemap(activeBasemap.value)
  const initialView = getWorldMonitorViewPreset(activeView.value)
  try {
    basemapReady = false
    map = new maplibregl.Map({
      container: mapContainer.value,
      style: initialBasemap.style,
      center: initialView.center,
      zoom: initialView.zoom,
      minZoom: 0.9,
      maxZoom: 6,
      renderWorldCopies: false,
      attributionControl: false,
      interactive: true,
      dragRotate: false,
      pitchWithRotate: false,
      canvasContextAttributes: { powerPreference: 'high-performance' }
    })
    fallbackMode.value = false
  } catch (error) {
    console.warn('全球事件地图加载失败，使用降级渲染:', error)
    fallbackMode.value = true
    return
  }

  scheduleBasemapFallback()
  map.on('error', (error) => {
    console.warn('World Monitor 地图资源加载告警:', error)
  })
  try {
    map.addControl(new maplibregl.NavigationControl({ showCompass: false }), 'top-right')
  } catch (error) {
    console.warn('World Monitor 地图控件初始化失败，保留主地图继续渲染:', error)
  }
  map.once('load', () => {
    markBasemapReady()
    initializeDeckOverlay()
  })
  map.on('idle', markBasemapReady)
  map.on('zoomend', syncLayers)
})

onBeforeUnmount(() => {
  if (overlay && map) {
    try {
      map.removeControl(overlay)
    } catch (error) {
      console.debug('移除地图覆盖层失败:', error)
    }
  }
  clearBasemapWatchdog()
  map?.remove()
  overlay = null
  map = null
})

watch(
  () => [props.events, props.selectedEventId],
  () => syncLayers(),
  { deep: true }
)

watch(
  () => props.selectedEventId,
  (eventId) => {
    if (!eventId || !map) return
    const event = props.events.find((item) => item.event_id === eventId)
    if (!event) return
    const lon = Number(event.lon || 0)
    const lat = Number(event.lat || 0)
    if (!Number.isFinite(lon) || !Number.isFinite(lat)) return
    map.flyTo({
      center: [lon, lat],
      zoom: Math.max(map.getZoom(), 2.15),
      essential: true
    })
  }
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

.wm-map-toolbar {
  position: absolute;
  z-index: 4;
  top: 12px;
  left: 12px;
  right: 54px;
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 10px;
  pointer-events: none;
}

.wm-toolbar-group {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 6px;
  padding: 6px;
  border: 1px solid rgba(128, 159, 204, 0.22);
  border-radius: 8px;
  background: rgba(6, 12, 22, 0.72);
  box-shadow: 0 16px 34px rgba(0, 0, 0, 0.2);
  backdrop-filter: blur(10px);
  pointer-events: auto;
}

.wm-chip {
  height: 26px;
  padding: 0 9px;
  border: 1px solid rgba(133, 164, 213, 0.22);
  border-radius: 7px;
  background: rgba(17, 31, 52, 0.72);
  color: #cbd8ec;
  font-size: 11px;
  line-height: 24px;
  white-space: nowrap;
  cursor: pointer;
  transition: border-color 0.18s ease, background 0.18s ease, color 0.18s ease;

  &:hover,
  &.active {
    border-color: rgba(96, 165, 250, 0.74);
    background: rgba(37, 99, 235, 0.28);
    color: #fff;
  }

  &.basemap {
    color: #d5f3ff;
  }

  &.focus {
    border-color: rgba(45, 212, 191, 0.45);
    color: #b8fff3;
  }
}

.fallback-map {
  z-index: 1;
  background:
    radial-gradient(circle at 30% 35%, rgba(57, 116, 216, 0.18), transparent 28%),
    #0b1320;
}

.fallback-world {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
}

.fallback-grid-line {
  fill: none;
  stroke: rgba(91, 124, 169, 0.28);
  stroke-width: 1;
}

.fallback-land {
  fill: rgba(33, 74, 112, 0.64);
  stroke: rgba(116, 163, 219, 0.45);
  stroke-width: 1.2;
}

.fallback-point {
  z-index: 2;
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

  em {
    position: absolute;
    left: 24px;
    top: -5px;
    max-width: 120px;
    padding: 3px 6px;
    border: 1px solid rgba(130, 167, 218, 0.32);
    border-radius: 6px;
    background: rgba(8, 14, 24, 0.72);
    color: #d8e7ff;
    font-size: 11px;
    font-style: normal;
    line-height: 1.2;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    pointer-events: none;
  }
}

.selected-map-card {
  position: absolute;
  z-index: 4;
  right: 14px;
  bottom: 54px;
  width: min(310px, calc(100% - 28px));
  padding: 12px;
  border: 1px solid rgba(141, 177, 226, 0.24);
  border-radius: 8px;
  background: rgba(8, 14, 24, 0.8);
  color: #eaf2ff;
  box-shadow: 0 18px 44px rgba(0, 0, 0, 0.26);
  backdrop-filter: blur(12px);

  p {
    margin: 8px 0 0;
    color: #c6d4e8;
    font-size: 12px;
    line-height: 1.45;
  }
}

.selected-card-top {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;

  strong {
    overflow: hidden;
    color: #fff;
    font-size: 13px;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
}

.severity-pill {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 34px;
  height: 20px;
  border-radius: 6px;
  color: #fff;
  font-size: 11px;
  font-weight: 760;

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

.selected-card-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 5px;
  margin-top: 10px;

  span {
    padding: 3px 6px;
    border: 1px solid rgba(64, 190, 159, 0.28);
    border-radius: 6px;
    background: rgba(31, 191, 143, 0.12);
    color: #b8fff0;
    font-size: 11px;
  }
}

.map-legend {
  position: absolute;
  z-index: 4;
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

.wm-source {
  color: #8fa1bb;
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

:global(.wm-map-tooltip) {
  max-width: 320px;
  padding: 10px;
  border: 1px solid rgba(125, 164, 220, 0.28);
  border-radius: 8px;
  background: rgba(7, 12, 21, 0.94);
  color: #dce8fb;
  box-shadow: 0 14px 36px rgba(0, 0, 0, 0.34);
}

:global(.wm-map-tooltip-top) {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 6px;
}

:global(.wm-map-tooltip-top span) {
  padding: 2px 6px;
  border-radius: 5px;
  background: rgba(217, 75, 95, 0.18);
  color: #ffb8c2;
  font-size: 11px;
}

:global(.wm-map-tooltip h4) {
  margin: 0;
  color: #fff;
  font-size: 13px;
  line-height: 1.35;
}

:global(.wm-map-tooltip p) {
  margin: 6px 0 0;
  color: #aebed3;
  font-size: 12px;
  line-height: 1.4;
}

:global(.wm-map-tooltip-tags) {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  margin-top: 8px;
}

:global(.wm-map-tooltip-tags em) {
  padding: 2px 5px;
  border-radius: 5px;
  background: rgba(57, 116, 216, 0.2);
  color: #bdd4ff;
  font-size: 11px;
  font-style: normal;
}

@media (max-width: 760px) {
  .wm-map-toolbar {
    right: 10px;
    flex-direction: column;
  }

  .selected-map-card {
    display: none;
  }
}
</style>
