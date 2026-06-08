/**
 * World Monitor inspired map utilities.
 *
 * Portions of this structure are adapted from:
 * https://github.com/koala73/worldmonitor
 *
 * World Monitor is licensed under AGPL-3.0. This local adaptation keeps the
 * same attribution in docs/THIRD_PARTY_NOTICES.md and is intentionally small:
 * provider selection, view presets, label localization, and great-circle paths.
 */

import type maplibregl from 'maplibre-gl'

export type WorldMonitorBasemapId = 'carto-vector' | 'openfreemap-dark' | 'gaode-cn' | 'carto-raster'
export type WorldMonitorViewId = 'global' | 'mena' | 'europe' | 'asia' | 'america' | 'africa' | 'latam'

export interface WorldMonitorBasemap {
  id: WorldMonitorBasemapId
  label: string
  detail: string
  style: string | maplibregl.StyleSpecification
  localizable: boolean
}

export interface WorldMonitorViewPreset {
  id: WorldMonitorViewId
  label: string
  center: [number, number]
  zoom: number
}

const cartoRasterStyle: maplibregl.StyleSpecification = {
  version: 8,
  sources: {
    cartoDark: {
      type: 'raster',
      tiles: [
        'https://a.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}.png',
        'https://b.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}.png',
        'https://c.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}.png',
        'https://d.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}.png'
      ],
      tileSize: 256,
      attribution: 'CARTO, OpenStreetMap contributors'
    }
  },
  layers: [
    {
      id: 'carto-dark-raster',
      type: 'raster',
      source: 'cartoDark',
      minzoom: 0,
      maxzoom: 10,
      paint: {
        'raster-opacity': 0.95
      }
    }
  ]
}

const gaodeChineseStyle: maplibregl.StyleSpecification = {
  version: 8,
  sources: {
    gaode: {
      type: 'raster',
      tiles: [
        'https://webrd01.is.autonavi.com/appmaptile?lang=zh_cn&size=1&scale=1&style=7&x={x}&y={y}&z={z}',
        'https://webrd02.is.autonavi.com/appmaptile?lang=zh_cn&size=1&scale=1&style=7&x={x}&y={y}&z={z}',
        'https://webrd03.is.autonavi.com/appmaptile?lang=zh_cn&size=1&scale=1&style=7&x={x}&y={y}&z={z}',
        'https://webrd04.is.autonavi.com/appmaptile?lang=zh_cn&size=1&scale=1&style=7&x={x}&y={y}&z={z}'
      ],
      tileSize: 256,
      attribution: 'AutoNavi'
    }
  },
  layers: [
    {
      id: 'gaode-cn-detail',
      type: 'raster',
      source: 'gaode',
      minzoom: 0,
      maxzoom: 12,
      paint: {
        'raster-opacity': 0.9,
        'raster-brightness-min': 0.08,
        'raster-brightness-max': 0.76,
        'raster-saturation': -0.55,
        'raster-contrast': 0.12
      }
    }
  ]
}

export const WORLD_MONITOR_BASEMAPS: WorldMonitorBasemap[] = [
  {
    id: 'carto-vector',
    label: 'CARTO Dark',
    detail: 'World Monitor 同款矢量暗色',
    style: 'https://basemaps.cartocdn.com/gl/dark-matter-gl-style/style.json',
    localizable: true
  },
  {
    id: 'openfreemap-dark',
    label: 'OpenFreeMap',
    detail: 'World Monitor 默认开源底图',
    style: 'https://tiles.openfreemap.org/styles/dark',
    localizable: true
  },
  {
    id: 'gaode-cn',
    label: '中文详图',
    detail: '国内网络兜底，中文边界标注',
    style: gaodeChineseStyle,
    localizable: false
  },
  {
    id: 'carto-raster',
    label: 'CARTO 快速',
    detail: '低依赖快速底图',
    style: cartoRasterStyle,
    localizable: false
  }
]

export const WORLD_MONITOR_VIEW_PRESETS: WorldMonitorViewPreset[] = [
  { id: 'global', label: '全球', center: [18, 22], zoom: 1.45 },
  { id: 'mena', label: '中东', center: [48, 29], zoom: 3.25 },
  { id: 'europe', label: '欧洲', center: [18, 50], zoom: 3.05 },
  { id: 'asia', label: '亚洲', center: [103, 32], zoom: 2.85 },
  { id: 'america', label: '北美', center: [-96, 39], zoom: 2.95 },
  { id: 'africa', label: '非洲', center: [20, 4], zoom: 2.85 },
  { id: 'latam', label: '拉美', center: [-63, -15], zoom: 2.85 }
]

export const WORLD_MONITOR_LAYER_ZOOM_THRESHOLDS = {
  eventLabels: 2.1,
  denseLabels: 3.1,
  influenceArcs: 1.15
}

export const getWorldMonitorBasemap = (id?: string): WorldMonitorBasemap =>
  WORLD_MONITOR_BASEMAPS.find((item) => item.id === id) || WORLD_MONITOR_BASEMAPS[0]

export const getWorldMonitorViewPreset = (id?: string): WorldMonitorViewPreset =>
  WORLD_MONITOR_VIEW_PRESETS.find((item) => item.id === id) || WORLD_MONITOR_VIEW_PRESETS[0]

export const escapeMapHtml = (value: unknown): string =>
  String(value ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;')

export const getLocalizedNameExpression = () =>
  ['coalesce', ['get', 'name:zh'], ['get', 'name:en'], ['get', 'name']] as any

export const localizeMapLabels = (map: maplibregl.Map | null | undefined) => {
  const style = map?.getStyle?.()
  if (!map || !style?.layers) return

  const expression = getLocalizedNameExpression()
  for (const layer of style.layers) {
    if (layer.type !== 'symbol') continue

    try {
      const textField = map.getLayoutProperty(layer.id, 'text-field')
      const serialized = typeof textField === 'string' ? textField : JSON.stringify(textField)
      if (!serialized || !/name/.test(serialized)) continue
      map.setLayoutProperty(layer.id, 'text-field', expression)
    } catch {
      // Some provider layers are not mutable; skip them.
    }
  }
}

export const interpolateGreatCircle = (
  start: [number, number],
  end: [number, number],
  numPoints = 24
): [number, number][] => {
  const toRad = (degree: number) => degree * Math.PI / 180
  const toDeg = (radian: number) => radian * 180 / Math.PI
  const [lon1, lat1] = [toRad(start[0]), toRad(start[1])]
  const [lon2, lat2] = [toRad(end[0]), toRad(end[1])]
  const distance = 2 * Math.asin(Math.sqrt(
    Math.sin((lat2 - lat1) / 2) ** 2 +
    Math.cos(lat1) * Math.cos(lat2) * Math.sin((lon2 - lon1) / 2) ** 2
  ))

  if (distance < 1e-10) return [start, end]

  const points: [number, number][] = []
  for (let index = 0; index <= numPoints; index += 1) {
    const fraction = index / numPoints
    const a = Math.sin((1 - fraction) * distance) / Math.sin(distance)
    const b = Math.sin(fraction * distance) / Math.sin(distance)
    const x = a * Math.cos(lat1) * Math.cos(lon1) + b * Math.cos(lat2) * Math.cos(lon2)
    const y = a * Math.cos(lat1) * Math.sin(lon1) + b * Math.cos(lat2) * Math.sin(lon2)
    const z = a * Math.sin(lat1) + b * Math.sin(lat2)
    points.push([toDeg(Math.atan2(y, x)), toDeg(Math.atan2(z, Math.sqrt(x * x + y * y)))])
  }

  return points
}
