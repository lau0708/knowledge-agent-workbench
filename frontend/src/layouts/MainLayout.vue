<template>
  <el-container class="app-shell">
    <el-aside width="220px" class="app-aside">
      <div class="brand">
        <div class="brand-title">Knowledge Agent</div>
        <div class="brand-subtitle">Local Knowledge Base</div>
      </div>

      <el-menu
        :default-active="activeMenu"
        router
        class="app-menu"
        background-color="#ffffff"
        text-color="#475569"
        active-text-color="#2563eb"
      >
        <el-menu-item index="/dashboard">
          <el-icon><DataBoard /></el-icon>
          <span>Dashboard</span>
        </el-menu-item>
        <el-menu-item index="/knowledge-base">
          <el-icon><FolderOpened /></el-icon>
          <span>Knowledge Base</span>
        </el-menu-item>
        <el-menu-item index="/assistant">
          <el-icon><ChatDotRound /></el-icon>
          <span>AI Assistant</span>
        </el-menu-item>
        <el-menu-item index="/workflow">
          <el-icon><Share /></el-icon>
          <span>Agent Workflow</span>
        </el-menu-item>
        <el-menu-item index="/approval">
          <el-icon><UserFilled /></el-icon>
          <span>Approval Center</span>
        </el-menu-item>
        <el-menu-item index="/trace">
          <el-icon><Monitor /></el-icon>
          <span>Trace Monitor</span>
        </el-menu-item>
      </el-menu>
    </el-aside>

    <el-container>
      <el-header class="app-header">
        <div class="page-title">{{ route.meta.title || 'Knowledge Agent' }}</div>
        <el-tag type="success" effect="light">在线</el-tag>
      </el-header>
      <el-main class="app-main">
        <RouterView />
      </el-main>
    </el-container>
  </el-container>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import {
  ChatDotRound,
  DataBoard,
  FolderOpened,
  Monitor,
  Share,
  UserFilled,
} from '@element-plus/icons-vue'

const route = useRoute()
const activeMenu = computed(() => route.path)
</script>

<style scoped>
.app-shell {
  height: 100%;
}

.app-aside {
  background: #ffffff;
  border-right: 1px solid #e5e7eb;
}

.brand {
  padding: 24px 20px 16px;
}

.brand-title {
  font-size: 20px;
  font-weight: 700;
  color: #111827;
}

.brand-subtitle {
  margin-top: 4px;
  font-size: 12px;
  color: #64748b;
}

.app-menu {
  border-right: none;
}

.app-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  background: #ffffff;
  border-bottom: 1px solid #e5e7eb;
}

.page-title {
  font-size: 18px;
  font-weight: 600;
  color: #111827;
}

.app-main {
  background: #f5f7fa;
  padding: 24px;
}
</style>
