<template>
  <div v-loading="loading">
    <el-card shadow="never">
      <div class="toolbar">
        <el-input
          v-model="sessionFilter"
          placeholder="按 session_id 筛选"
          clearable
          class="filter-input"
          @keydown.enter="loadTraces"
        />
        <el-button @click="loadTraces">刷新</el-button>
      </div>
    </el-card>

    <el-card shadow="never" class="table-card">
      <el-table :data="traces" empty-text="暂无 Trace">
        <el-table-column prop="trace_id" label="Trace ID" min-width="150" />
        <el-table-column prop="session_id" label="会话" min-width="150" />
        <el-table-column prop="question" label="问题" min-width="220" show-overflow-tooltip />
        <el-table-column prop="status" label="状态" width="130">
          <template #default="{ row }">
            <el-tag :type="statusTag(row.status)" effect="light">{{ row.status }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="duration_ms" label="耗时(ms)" width="110" />
        <el-table-column prop="messages_count" label="消息数" width="90" />
        <el-table-column label="操作" width="110" fixed="right">
          <template #default="{ row }">
            <el-button size="small" @click="openDetail(row.trace_id)">详情</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-drawer v-model="drawerVisible" title="Trace 详情" size="720px">
      <div v-loading="detailLoading">
        <el-descriptions :column="2" border>
          <el-descriptions-item label="Trace ID">{{ detail?.trace_id }}</el-descriptions-item>
          <el-descriptions-item label="状态">{{ detail?.status }}</el-descriptions-item>
          <el-descriptions-item label="会话">{{ detail?.session_id }}</el-descriptions-item>
          <el-descriptions-item label="耗时">{{ detail?.duration_ms }} ms</el-descriptions-item>
          <el-descriptions-item label="问题" :span="2">{{ detail?.question }}</el-descriptions-item>
          <el-descriptions-item label="答案" :span="2">{{ detail?.answer || '无' }}</el-descriptions-item>
          <el-descriptions-item v-if="detail?.error" label="错误" :span="2">
            <span class="error-text">{{ detail.error }}</span>
          </el-descriptions-item>
        </el-descriptions>

        <div class="section-title">工具调用</div>
        <el-timeline v-if="detail?.tool_calls.length">
          <el-timeline-item
            v-for="(tool, index) in detail.tool_calls"
            :key="index"
            :timestamp="String(tool.status || '')"
          >
            <div class="tool-name">{{ tool.name }}</div>
            <pre class="detail-pre">{{ JSON.stringify(tool, null, 2) }}</pre>
          </el-timeline-item>
        </el-timeline>
        <el-empty v-else description="无工具调用" :image-size="60" />

        <div class="section-title">Workflow 轨迹</div>
        <el-timeline v-if="detail?.workflow_trace.length">
          <el-timeline-item
            v-for="(event, index) in detail.workflow_trace"
            :key="index"
            :timestamp="String(event.event || '')"
          >
            {{ event.node }}
          </el-timeline-item>
        </el-timeline>
        <el-empty v-else description="无 Workflow 轨迹" :image-size="60" />

        <div class="section-title">失败分析</div>
        <pre class="detail-pre">{{ JSON.stringify(analysis, null, 2) }}</pre>
      </div>
    </el-drawer>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import {
  fetchTraceAnalysis,
  fetchTraceDetail,
  fetchTraceList,
} from '@/api/trace'
import type { TraceAnalysis, TraceRecord } from '@/types/api'

const loading = ref(false)
const detailLoading = ref(false)
const sessionFilter = ref('')
const traces = ref<TraceRecord[]>([])

const drawerVisible = ref(false)
const detail = ref<TraceRecord | null>(null)
const analysis = ref<TraceAnalysis | null>(null)

async function loadTraces() {
  loading.value = true
  try {
    traces.value = await fetchTraceList(sessionFilter.value || undefined)
  } catch (error) {
    ElMessage.error('Trace 列表加载失败')
  } finally {
    loading.value = false
  }
}

async function openDetail(traceId: string) {
  drawerVisible.value = true
  detailLoading.value = true
  detail.value = null
  analysis.value = null

  try {
    const [traceData, analysisData] = await Promise.all([
      fetchTraceDetail(traceId),
      fetchTraceAnalysis(traceId),
    ])
    detail.value = traceData
    analysis.value = analysisData
  } catch (error) {
    ElMessage.error('Trace 详情加载失败')
  } finally {
    detailLoading.value = false
  }
}

function statusTag(status: string): 'success' | 'danger' | 'warning' | 'info' {
  if (status === 'completed') return 'success'
  if (status === 'failed') return 'danger'
  if (status === 'waiting_confirmation') return 'warning'
  return 'info'
}

onMounted(loadTraces)
</script>

<style scoped>
.toolbar {
  display: flex;
  gap: 12px;
}

.filter-input {
  max-width: 320px;
}

.table-card {
  margin-top: 16px;
}

.section-title {
  margin: 24px 0 10px;
  font-size: 16px;
  font-weight: 600;
  color: #111827;
}

.tool-name {
  font-weight: 600;
}

.detail-pre {
  margin: 8px 0;
  padding: 10px;
  background: #f8fafc;
  border: 1px solid #e5e7eb;
  border-radius: 6px;
  white-space: pre-wrap;
  word-break: break-all;
}

.error-text {
  color: #dc2626;
}
</style>
