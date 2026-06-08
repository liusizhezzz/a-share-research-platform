<template>
  <div class="chart-shell">
    <v-chart v-if="chain" class="chart" :option="option" autoresize />
    <el-empty v-else description="选择一个事件查看传导链" :image-size="72" />
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import VChart from 'vue-echarts'
import { use } from 'echarts/core'
import { CanvasRenderer } from 'echarts/renderers'
import { SankeyChart } from 'echarts/charts'
import { TooltipComponent } from 'echarts/components'
import type { EventImpactChain } from '@/api/marketIntelligence'

use([CanvasRenderer, SankeyChart, TooltipComponent])

const props = defineProps<{
  chain?: EventImpactChain | null
}>()

const option = computed(() => {
  const steps = props.chain?.steps || []
  const nodes = steps.map((step, index) => ({
    name: `${index + 1}. ${step.label}`,
    itemStyle: {
      color: index === 0 ? '#d94b5f' : index === steps.length - 1 ? '#1fbf8f' : '#3974d8'
    }
  }))
  const links = steps.slice(0, -1).map((step, index) => ({
    source: `${index + 1}. ${step.label}`,
    target: `${index + 2}. ${steps[index + 1].label}`,
    value: Math.max(1, 6 - index),
    lineStyle: { color: index === 0 ? '#d94b5f' : '#3974d8' }
  }))

  return {
    tooltip: {
      formatter: (params: { dataType?: string; data?: { name?: string } }) => {
        if (params.dataType !== 'node') return ''
        const index = nodes.findIndex((node) => node.name === params.data?.name)
        return steps[index]?.value || params.data?.name || ''
      }
    },
    series: [
      {
        type: 'sankey',
        left: 8,
        right: 8,
        top: 8,
        bottom: 8,
        nodeGap: 14,
        nodeWidth: 16,
        draggable: false,
        emphasis: { focus: 'adjacency' },
        label: {
          color: '#d8e3f7',
          fontSize: 12,
          overflow: 'truncate',
          width: 120
        },
        lineStyle: {
          opacity: 0.32,
          curveness: 0.55
        },
        data: nodes,
        links
      }
    ]
  }
})
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

