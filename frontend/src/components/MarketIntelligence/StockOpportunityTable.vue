<template>
  <el-table :data="stocks" size="small" class="stock-table" @row-click="handleRowClick">
    <el-table-column prop="code" label="代码" width="92" fixed />
    <el-table-column prop="name" label="名称" min-width="118">
      <template #default="{ row }">
        <div class="stock-name">{{ row.name }}</div>
        <div class="stock-sub">{{ row.industry || row.theme || '待映射' }}</div>
      </template>
    </el-table-column>
    <el-table-column prop="score" label="综合分" width="88" sortable>
      <template #default="{ row }">
        <el-tag :type="scoreTag(row.score)" effect="plain">{{ formatNumber(row.score) }}</el-tag>
      </template>
    </el-table-column>
    <el-table-column prop="prediction_horizon" label="预测期" width="112">
      <template #default="{ row }">{{ row.prediction_horizon || '1-3交易日' }}</template>
    </el-table-column>
    <el-table-column prop="signal_strength" label="确认" width="82" sortable>
      <template #default="{ row }">{{ formatNumber(row.signal_strength) }}</template>
    </el-table-column>
    <el-table-column prop="price_in_penalty" label="Price-in" width="90" sortable>
      <template #default="{ row }">{{ formatNumber(row.price_in_penalty) }}</template>
    </el-table-column>
    <el-table-column prop="confidence" label="置信" width="78">
      <template #default="{ row }">{{ formatNumber((row.confidence || 0) * 100) }}%</template>
    </el-table-column>
    <el-table-column prop="pct_chg" label="涨跌幅" width="86">
      <template #default="{ row }">
        <span :class="priceClass(row.pct_chg)">{{ formatPct(row.pct_chg) }}</span>
      </template>
    </el-table-column>
    <el-table-column prop="theme" label="主题" width="104" />
    <el-table-column label="证据" min-width="220">
      <template #default="{ row }">
        <div class="evidence-line">
          新闻 {{ row.news_count || 0 }} / 评论 {{ row.comment_count || 0 }} /
          公告 {{ row.announcement_count || 0 }} / 研报 {{ row.research_count || 0 }} /
          量化 {{ row.quant_count || 0 }}
        </div>
        <div class="headline">{{ row.headlines?.[0] || '暂无代表线索' }}</div>
      </template>
    </el-table-column>
  </el-table>
</template>

<script setup lang="ts">
import type { StockOpportunity } from '@/api/marketIntelligence'

defineProps<{
  stocks: StockOpportunity[]
}>()

const emit = defineEmits<{
  select: [stock: StockOpportunity]
}>()

const handleRowClick = (row: StockOpportunity) => {
  emit('select', row)
}

const formatNumber = (value?: number) => Number(value || 0).toFixed(1)

const formatPct = (value?: number) => {
  const num = Number(value || 0)
  return `${num > 0 ? '+' : ''}${num.toFixed(2)}%`
}

const priceClass = (value?: number) => {
  const num = Number(value || 0)
  return num > 0 ? 'price-up' : num < 0 ? 'price-down' : ''
}

const scoreTag = (value?: number) => {
  const score = Number(value || 0)
  if (score >= 75) return 'success'
  if (score >= 55) return 'warning'
  return 'info'
}
</script>

<style scoped lang="scss">
.stock-table {
  width: 100%;
}

.stock-name {
  font-weight: 650;
  color: #dce7f7;
}

.stock-sub,
.headline {
  margin-top: 3px;
  color: #8090aa;
  font-size: 12px;
  line-height: 1.45;
}

.evidence-line {
  color: #c3cee2;
  line-height: 1.45;
}

.price-up {
  color: #e85d75;
  font-weight: 650;
}

.price-down {
  color: #20b486;
  font-weight: 650;
}
</style>
