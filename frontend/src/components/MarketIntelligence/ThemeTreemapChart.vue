<template>
  <div class="chart-shell">
    <v-chart v-if="nodes.length" class="chart" :option="option" autoresize @click="handleClick" />
    <el-empty v-else description="暂无主题信号" :image-size="72" />
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import VChart from 'vue-echarts'
import { use } from 'echarts/core'
import { CanvasRenderer } from 'echarts/renderers'
import { TreemapChart } from 'echarts/charts'
import { TooltipComponent } from 'echarts/components'
import type { ThemeHeatmapNode } from '@/api/marketIntelligence'

use([CanvasRenderer, TreemapChart, TooltipComponent])

const props = defineProps<{
  nodes: ThemeHeatmapNode[]
}>()

const emit = defineEmits<{
  select: [node: ThemeHeatmapNode]
}>()

const option = computed(() => ({
  tooltip: {
    formatter: (params: { data: ThemeHeatmapNode }) => {
      const data = params.data
      return `${data.name}<br/>综合分 ${data.score}<br/>新闻 ${data.news_count} 条 / 事件 ${data.event_count} 个<br/>风险 ${data.risk_score}`
    }
  },
  series: [
    {
      type: 'treemap',
      roam: false,
      nodeClick: false,
      breadcrumb: { show: false },
      left: 0,
      right: 0,
      top: 0,
      bottom: 0,
      itemStyle: {
        borderColor: '#172033',
        borderWidth: 2,
        gapWidth: 2
      },
      label: {
        color: '#eef4ff',
        fontSize: 13,
        formatter: (params: { data: ThemeHeatmapNode }) => `${params.data.name}\n${params.data.score}`
      },
      upperLabel: { show: false },
      levels: [
        {
          itemStyle: {
            borderColor: '#172033',
            borderWidth: 2,
            gapWidth: 2
          }
        }
      ],
      data: props.nodes.map((node) => ({
        ...node,
        itemStyle: {
          color:
            node.risk_score >= 72
              ? '#d94b5f'
              : node.sentiment_score >= 0.2
                ? '#1fbf8f'
                : node.score >= 70
                  ? '#f0a33a'
                  : '#3974d8'
        }
      }))
    }
  ]
}))

const handleClick = (params: { name?: string }) => {
  const node = props.nodes.find((item) => item.name === params.name)
  if (node) emit('select', node)
}
</script>

<style scoped lang="scss">
.chart-shell {
  min-height: 320px;
}

.chart {
  width: 100%;
  height: 320px;
}
</style>

