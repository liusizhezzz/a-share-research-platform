<template>
  <div class="chart-shell">
    <v-chart v-if="cells.length" class="chart" :option="option" autoresize />
    <el-empty v-else description="暂无行业矩阵" :image-size="72" />
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import VChart from 'vue-echarts'
import { use } from 'echarts/core'
import { CanvasRenderer } from 'echarts/renderers'
import { HeatmapChart } from 'echarts/charts'
import { GridComponent, TooltipComponent, VisualMapComponent } from 'echarts/components'
import type { IndustryMatrixCell } from '@/api/marketIntelligence'

use([CanvasRenderer, HeatmapChart, GridComponent, TooltipComponent, VisualMapComponent])

const props = defineProps<{
  cells: IndustryMatrixCell[]
}>()

const themes = computed(() => Array.from(new Set(props.cells.map((cell) => cell.theme))))
const dimensions = computed(() => Array.from(new Set(props.cells.map((cell) => cell.dimension))))

const option = computed(() => ({
  tooltip: {
    formatter: (params: { data: [number, number, number] }) => {
      const [x, y, value] = params.data
      return `${themes.value[y]}<br/>${dimensions.value[x]}: ${value}`
    }
  },
  grid: { left: 86, right: 18, top: 16, bottom: 40 },
  xAxis: {
    type: 'category',
    data: dimensions.value,
    axisLabel: { color: '#8090aa', interval: 0 }
  },
  yAxis: {
    type: 'category',
    data: themes.value,
    axisLabel: { color: '#8090aa' }
  },
  visualMap: {
    min: 0,
    max: 100,
    show: false,
    inRange: {
      color: ['#16243a', '#216aa6', '#21a985', '#f0a33a', '#d94b5f']
    }
  },
  series: [
    {
      type: 'heatmap',
      data: props.cells.map((cell) => [
        dimensions.value.indexOf(cell.dimension),
        themes.value.indexOf(cell.theme),
        Number(cell.value || 0)
      ]),
      label: {
        show: true,
        color: '#eef4ff',
        formatter: (params: { data: [number, number, number] }) => Math.round(params.data[2]).toString()
      },
      itemStyle: {
        borderColor: '#111827',
        borderWidth: 1
      }
    }
  ]
}))
</script>

<style scoped lang="scss">
.chart-shell {
  min-height: 300px;
}

.chart {
  width: 100%;
  height: 300px;
}
</style>

