<template>
  <div v-loading="loading">
    <el-card shadow="never">
      <div class="toolbar">
        <el-input
          v-model="sessionFilter"
          placeholder="按 session_id 筛选"
          clearable
          class="filter-input"
          @keydown.enter="loadOperations"
        />
        <el-button @click="loadOperations">刷新</el-button>
      </div>
    </el-card>

    <el-card shadow="never" class="table-card">
      <el-table :data="operations" empty-text="暂无待确认操作">
        <el-table-column prop="operation_id" label="操作 ID" min-width="150" />
        <el-table-column prop="session_id" label="会话" min-width="150" />
        <el-table-column prop="tool_name" label="工具" min-width="160" />
        <el-table-column prop="arguments" label="参数" min-width="220">
          <template #default="{ row }">
            <code class="args">{{ JSON.stringify(row.arguments) }}</code>
          </template>
        </el-table-column>
        <el-table-column prop="status" label="状态" width="130">
          <template #default="{ row }">
            <el-tag :type="statusTag(row.status)" effect="light">{{ row.status }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="260" fixed="right">
          <template #default="{ row }">
            <template v-if="row.status === 'pending'">
              <el-button size="small" type="primary" @click="openModify(row)">修改</el-button>
              <el-button size="small" type="success" @click="approve(row.operation_id)">批准</el-button>
              <el-button size="small" type="danger" @click="reject(row.operation_id)">拒绝</el-button>
            </template>
            <span v-else>已处理</span>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-dialog v-model="modifyVisible" title="修改待确认参数" width="640px">
      <el-input
        v-model="modifyArgumentsText"
        type="textarea"
        :rows="10"
        placeholder='请输入 JSON，例如：{"document_id": 2}'
      />
      <template #footer>
        <el-button @click="modifyVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="saveModify">保存修改</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  approveOperation,
  fetchPendingOperations,
  modifyOperation,
  rejectOperation,
} from '@/api/hitl'
import type { PendingOperation } from '@/types/api'

const loading = ref(false)
const saving = ref(false)
const sessionFilter = ref('')
const operations = ref<PendingOperation[]>([])

const modifyVisible = ref(false)
const modifyOperationId = ref('')
const modifyArgumentsText = ref('{}')

async function loadOperations() {
  loading.value = true

  try {
    operations.value = await fetchPendingOperations(sessionFilter.value || undefined)
  } catch (error) {
    ElMessage.error('审批列表加载失败')
  } finally {
    loading.value = false
  }
}

function openModify(operation: PendingOperation) {
  modifyOperationId.value = operation.operation_id
  modifyArgumentsText.value = JSON.stringify(operation.arguments, null, 2)
  modifyVisible.value = true
}

async function saveModify() {
  let parsed: Record<string, unknown>
  try {
    parsed = JSON.parse(modifyArgumentsText.value)
  } catch {
    ElMessage.error('参数必须是合法 JSON')
    return
  }

  saving.value = true
  try {
    await modifyOperation(modifyOperationId.value, parsed)
    ElMessage.success('参数已修改')
    modifyVisible.value = false
    await loadOperations()
  } catch (error) {
    ElMessage.error('参数修改失败')
  } finally {
    saving.value = false
  }
}

async function approve(operationId: string) {
  try {
    await approveOperation(operationId)
    ElMessage.success('操作已批准')
    await loadOperations()
  } catch (error) {
    ElMessage.error('操作批准失败')
  }
}

async function reject(operationId: string) {
  let reason: string | undefined
  try {
    const result = await ElMessageBox.prompt('请输入拒绝原因', '拒绝操作', {
      confirmButtonText: '拒绝',
      cancelButtonText: '取消',
      inputPattern: /\S+/,
      inputErrorMessage: '拒绝原因不能为空',
    })
    reason = result.value
  } catch {
    return
  }

  try {
    await rejectOperation(operationId, reason)
    ElMessage.success('操作已拒绝')
    await loadOperations()
  } catch (error) {
    ElMessage.error('操作拒绝失败')
  }
}

function statusTag(status: string): 'success' | 'danger' | 'warning' | 'info' {
  if (status === 'pending') return 'warning'
  if (status === 'executed' || status === 'approved') return 'success'
  if (status === 'failed' || status === 'rejected' || status === 'expired') return 'danger'
  return 'info'
}

onMounted(loadOperations)
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

.args {
  font-size: 12px;
  color: #475569;
}
</style>
