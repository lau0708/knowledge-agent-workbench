<template>
  <div v-loading="loading">
    <el-alert
      v-if="errorMessage"
      :title="errorMessage"
      type="error"
      :closable="false"
      show-icon
    />

    <el-row :gutter="16">
      <el-col :xs="24" :sm="12" :lg="6">
        <el-card shadow="never">
          <div class="stat-label">系统状态</div>
          <div class="stat-value">
            <el-tag :type="health?.status === 'ok' ? 'success' : 'danger'">
              {{ health?.status === 'ok' ? '正常' : '异常' }}
            </el-tag>
          </div>
          <div class="stat-note">{{ health?.service || 'local-knowledge-base' }}</div>
        </el-card>
      </el-col>

      <el-col :xs="24" :sm="12" :lg="6">
        <el-card shadow="never">
          <div class="stat-label">文档总数</div>
          <div class="stat-value">{{ documents.length }}</div>
          <div class="stat-note">{{ chunkCount }} 个 Chunk</div>
        </el-card>
      </el-col>

      <el-col :xs="24" :sm="12" :lg="6">
        <el-card shadow="never">
          <div class="stat-label">Agent 执行</div>
          <div class="stat-value">{{ traces.length }}</div>
          <div class="stat-note">成功 {{ successTraceCount }} / 失败 {{ failedTraceCount }}</div>
        </el-card>
      </el-col>

      <el-col :xs="24" :sm="12" :lg="6">
        <el-card shadow="never">
          <div class="stat-label">待审批</div>
          <div class="stat-value">{{ pendingApprovalCount }}</div>
          <div class="stat-note">当前待确认操作</div>
        </el-card>
      </el-col>
    </el-row>

    <el-card shadow="never" class="trace-card">
      <template #header>
        <div class="card-header">
          <span>最近 Agent Trace</span>
          <el-button text type="primary" @click="router.push('/trace')">
            查看全部
          </el-button>
        </div>
      </template>

      <el-table :data="recentTraces" empty-text="暂无 Trace">
        <el-table-column prop="started_at" label="时间" min-width="180" />
        <el-table-column prop="session_id" label="会话" min-width="140" />
        <el-table-column prop="question" label="问题" min-width="220" show-overflow-tooltip />
        <el-table-column prop="status" label="状态" width="110">
          <template #default="{ row }">
            <el-tag :type="statusTag(row.status)" effect="light">
              {{ row.status }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="duration_ms" label="耗时(ms)" width="110" />
      </el-table>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import {
  fetchConfirmations,
  fetchDocuments,
  fetchHealth,
  fetchTraces,
} from '@/api/dashboard'
import type {
  DocumentSummary,
  HealthResponse,
  PendingOperation,
  TraceRecord,
} from '@/types/api'

const router = useRouter()
const loading = ref(false)
const errorMessage = ref('')
const health = ref<HealthResponse | null>(null)
const documents = ref<DocumentSummary[]>([])
const traces = ref<TraceRecord[]>([])
const confirmations = ref<PendingOperation[]>([])

const chunkCount = computed(() =>
  documents.value.reduce((total, document) => total + document.chunk_count, 0),
)

const successTraceCount = computed(
  () => traces.value.filter((trace) => trace.status === 'completed').length,
)

const failedTraceCount = computed(
  () => traces.value.filter((trace) => trace.status === 'failed').length,
)

const pendingApprovalCount = computed(
  () => confirmations.value.filter((operation) => operation.status === 'pending').length,
)

const recentTraces = computed(() => traces.value.slice(0, 10))

function statusTag(status: string): 'success' | 'danger' | 'warning' | 'info' {
  if (status === 'completed') return 'success'
  if (status === 'failed') return 'danger'
  if (status === 'waiting_confirmation') return 'warning'
  return 'info'
}

async function loadDashboard() {
  loading.value = true
  errorMessage.value = ''

  try {
    const [healthData, documentData, traceData, confirmationData] = await Promise.all([
      fetchHealth(),
      fetchDocuments(),
      fetchTraces(),
      fetchConfirmations(),
    ])

    health.value = healthData
    documents.value = documentData
    traces.value = traceData
    confirmations.value = confirmationData
  } catch (error) {
    errorMessage.value = 'Dashboard 数据加载失败，请确认后端服务已启动。'
  } finally {
    loading.value = false
  }
}

onMounted(loadDashboard)
</script>

<style scoped>
.stat-label {
  color: #64748b;
  font-size: 14px;
}

.stat-value {
  margin: 12px 0 4px;
  font-size: 32px;
  font-weight: 700;
  color: #111827;
}

.stat-note {
  color: #94a3b8;
  font-size: 12px;
}

.trace-card {
  margin-top: 16px;
}

.card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}
</style>
