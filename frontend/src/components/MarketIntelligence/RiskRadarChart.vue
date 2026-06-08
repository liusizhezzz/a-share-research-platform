<template>
  <div class="chart-shell">
    <v-chart class="chart" :option="option" autoresize />
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import VChart from 'vue-echarts'
import { use } from 'echarts/core'
import { CanvasRenderer } from 'echarts/renderers'
import { RadarChart } from 'echarts/charts'
import { LegendComponent, TooltipComponent } from 'echarts/components'
import type { GlobalEvent, SourceCoverage, ThemeHeatmapNode } from '@/api/marketIntelligence'

use([CanvasRenderer, RadarChart, LegendComponent, TooltipComponent])

const props = defineProps<{
  events: GlobalEvent[]
  themes: ThemeHeatmapNode[]
  coverage: SourceCoverage
}>()

const values = computed(() => {
  const maxEventRisk = Math.max(0, ...props.events.map((event) => Number(event.severity || 0)))
  const avgThemeRisk =
    props.themes.reduce((sum, theme) => sum + Number(theme.risk_score || 0), 0) /
    Math.max(props.themes.length, 1)
  const negativeSentiment = Math.max(
    0,
    ...props.themes.map((theme) => Math.max(0, -Number(theme.sentiment_score || 0)) * 100)
  )
  const dataFreshnessRisk = 100 - Number(props.coverage.score || 0)
  const crowdingRisk = Math.min(100, Math.max(0, ...props.themes.map((theme) => Number(theme.heat || 0))))
  return [
    Math.round(maxEventRisk),
    Math.round(avgThemeRisk),
    Math.round(negativeSentiment),
    Math.round(dataFreshnessRisk),
    Math.round(crowdingRisk)
  ]
})

const option = computed(() => ({
  tooltip: {},
  radar: {
    radius: '68%',
    indicator: [
      { name: '全球事件', max: 100 },
      { name: '主题风险', max: 100 },
      { name: '负面舆情', max: 100 },
      { name: '数据滞后', max: 100 },
      { name: '拥挤度', max: 100 }
    ],
    axisName: {
      color: '#8090aa'
    },
    splitLine: { lineStyle: { color: '#263247' } },
    splitArea: { areaStyle: { color: ['rgba(31, 41, 55, 0.32)', 'rgba(17, 24, 39, 0.22)'] } },
    axisLine: { lineStyle: { color: '#263247' } }
  },
  series: [
    {
      type: 'radar',
      data: [
        {
          name: '风险雷达',
          value: values.value,
          areaStyle: { color: 'rgba(217, 75, 95, 0.22)' },
          lineStyle: { color: '#d94b5f', width: 2 },
          itemStyle: { color: '#d94b5f' }
        }
      ]
    }
  ]
}))
</script>

<style scoped lang="scss">
.chart-shell {
  min-height: 260px;
}

.chart {
  width: 100%;
  height: 260px;
}
</style>

