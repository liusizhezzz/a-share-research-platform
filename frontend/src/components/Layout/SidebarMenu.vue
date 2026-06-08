<template>
  <el-menu
    :default-active="activeMenu"
    :collapse="appStore.sidebarCollapsed"
    :unique-opened="true"
    router
    class="sidebar-menu"
    :class="{ 'sidebar-menu--research': isResearchWorkspace }"
  >
    <el-menu-item index="/dashboard">
      <el-icon><Odometer /></el-icon>
      <template #title>仪表板</template>
    </el-menu-item>

    <div v-show="!appStore.sidebarCollapsed" class="menu-section-label">重点投研</div>

    <el-menu-item index="/market-intelligence" class="priority-menu-item">
      <el-icon><DataAnalysis /></el-icon>
      <template #title>市场情报</template>
    </el-menu-item>

    <el-menu-item index="/investment-daily" class="priority-menu-item">
      <el-icon><Document /></el-icon>
      <template #title>投资日报</template>
    </el-menu-item>

    <div v-show="!appStore.sidebarCollapsed" class="menu-section-label">常用工具</div>

    <el-menu-item index="/learning">
      <el-icon><Reading /></el-icon>
      <template #title>学习中心</template>
    </el-menu-item>

    <el-sub-menu index="/analysis">
      <template #title>
        <el-icon><TrendCharts /></el-icon>
        <span>股票分析</span>
      </template>
      <el-menu-item index="/analysis/single">单股分析</el-menu-item>
      <el-menu-item index="/analysis/batch">批量分析</el-menu-item>
      <!-- 新增：将分析报告作为股票分析的子菜单 -->
      <el-menu-item index="/reports">分析报告</el-menu-item>
    </el-sub-menu>

    <el-menu-item index="/tasks">
      <el-icon><List /></el-icon>
      <template #title>任务中心</template>
    </el-menu-item>

    <el-menu-item index="/screening">
      <el-icon><Search /></el-icon>
      <template #title>股票筛选</template>
    </el-menu-item>

    <el-menu-item index="/favorites">
      <el-icon><Star /></el-icon>
      <template #title>我的自选股</template>
    </el-menu-item>

    <el-menu-item index="/paper">
      <el-icon><CreditCard /></el-icon>
      <template #title>模拟交易</template>
    </el-menu-item>


    <!-- 分析报告已移至“股票分析”子菜单，保留注释便于追踪 -->
    <!--
    <el-menu-item index="/reports">
      <el-icon><Document /></el-icon>
      <template #title>分析报告</template>
    </el-menu-item>
    -->

    <el-sub-menu index="/settings">
      <template #title>
        <el-icon><Setting /></el-icon>
        <span>设置</span>
      </template>

      <!-- 个人设置 -->
      <el-sub-menu index="/settings-personal">
        <template #title>个人设置</template>
        <el-menu-item index="/settings">通用设置</el-menu-item>
        <el-menu-item index="/settings?tab=appearance">外观设置</el-menu-item>
        <el-menu-item index="/settings?tab=analysis">分析偏好</el-menu-item>
        <el-menu-item index="/settings?tab=notifications">通知设置</el-menu-item>
        <el-menu-item index="/settings?tab=security">安全设置</el-menu-item>
      </el-sub-menu>

      <!-- 系统配置 -->
      <el-sub-menu index="/settings-config">
        <template #title>系统配置</template>
        <el-menu-item index="/settings/config">配置管理</el-menu-item>
        <el-menu-item index="/settings/cache">缓存管理</el-menu-item>
      </el-sub-menu>

      <!-- 系统管理 -->
      <el-sub-menu index="/settings-admin">
        <template #title>系统管理</template>
        <el-menu-item index="/settings/database">数据库管理</el-menu-item>
        <el-menu-item index="/settings/logs">操作日志</el-menu-item>
        <el-menu-item index="/settings/system-logs">系统日志</el-menu-item>
        <el-menu-item index="/settings/sync">多数据源同步</el-menu-item>
        <el-menu-item index="/settings/scheduler">定时任务</el-menu-item>
        <el-menu-item index="/settings/usage">使用统计</el-menu-item>
      </el-sub-menu>
    </el-sub-menu>

    <el-menu-item index="/about">
      <el-icon><InfoFilled /></el-icon>
      <template #title>关于</template>
    </el-menu-item>
  </el-menu>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import { useAppStore } from '@/stores/app'
import {
  Odometer,
  Reading,
  TrendCharts,
  Search,
  Star,
  List,
  DataAnalysis,
  Document,
  Setting,
  InfoFilled,
  CreditCard
} from '@element-plus/icons-vue'

const route = useRoute()
const appStore = useAppStore()

const activeMenu = computed(() => route.path)
const isResearchWorkspace = computed(() =>
  route.path.startsWith('/market-intelligence') || route.path.startsWith('/investment-daily')
)
</script>

<style lang="scss" scoped>
.sidebar-menu {
  border: none;
  height: 100%;

  :deep(.el-menu-item),
  :deep(.el-sub-menu__title) {
    height: 48px;
    line-height: 48px;
  }

  :deep(.el-menu-item.is-active) {
    background-color: var(--el-color-primary-light-9);
    color: var(--el-color-primary);
  }

  .menu-section-label {
    padding: 12px 18px 6px;
    color: var(--el-text-color-placeholder);
    font-size: 12px;
    font-weight: 650;
    letter-spacing: 0;
  }

  :deep(.priority-menu-item) {
    margin: 4px 10px;
    border: 1px solid var(--el-border-color-lighter);
    border-radius: 8px;
    background: linear-gradient(90deg, var(--el-color-primary-light-9), transparent 82%);
    font-weight: 650;

    &.is-active {
      border-color: var(--el-color-primary-light-5);
      background: var(--el-color-primary-light-8);
    }
  }
}

.sidebar-menu--research {
  --el-menu-bg-color: transparent;
  --el-menu-text-color: #aebdd2;
  --el-menu-hover-bg-color: rgba(67, 119, 198, 0.16);
  --el-menu-active-color: #ffffff;
  background: transparent;

  :deep(.el-menu-item),
  :deep(.el-sub-menu__title) {
    height: 42px;
    line-height: 42px;
    margin: 2px 8px;
    border-radius: 8px;
    color: #aebdd2;
  }

  :deep(.el-menu-item:hover),
  :deep(.el-sub-menu__title:hover) {
    background: rgba(67, 119, 198, 0.16);
    color: #e7f0ff;
  }

  :deep(.el-menu-item.is-active) {
    background: rgba(61, 130, 246, 0.2);
    color: #ffffff;
    box-shadow: inset 3px 0 0 #60a5fa;
  }

  .menu-section-label {
    color: #607087;
    font-size: 11px;
    text-transform: uppercase;
  }

  :deep(.priority-menu-item) {
    position: relative;
    margin: 5px 10px;
    border-color: rgba(105, 147, 207, 0.26);
    background:
      linear-gradient(90deg, rgba(59, 130, 246, 0.2), rgba(20, 184, 166, 0.08) 74%);
    color: #dceaff;
    font-weight: 720;
  }

  :deep(.priority-menu-item)::after {
    content: "";
    position: absolute;
    top: 10px;
    right: 10px;
    width: 6px;
    height: 6px;
    border-radius: 50%;
    background: #37d4b5;
    box-shadow: 0 0 12px rgba(55, 212, 181, 0.72);
  }

  :deep(.priority-menu-item.is-active) {
    border-color: rgba(96, 165, 250, 0.62);
    background:
      linear-gradient(90deg, rgba(59, 130, 246, 0.34), rgba(20, 184, 166, 0.12) 78%);
    box-shadow:
      inset 3px 0 0 #37d4b5,
      0 12px 26px rgba(5, 12, 22, 0.22);
  }
}
</style>
