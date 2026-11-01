<template>
  <el-card shadow="never">
    <div class="workflow-toolbar">
      <el-radio-group v-model="engine">
        <el-radio-button value="handwritten">手写 Workflow</el-radio-button>
        <el-radio-button value="langgraph">LangGraph</el-radio-button>
      </el-radio-group>
      <el-input
        v-model="question"
        placeholder="输入需要知识库完成的任务"
        class="question-input"
        @keydown.enter="run"
      />
      <el-button type="primary" :loading="loading" @click="run">执行</el-button>
    </div>

    <el-empty v-if="!state && !loading" description="执行后可查看节点轨迹" />

    <div v-if="state" class="result-panel">
      <el-descriptions :column="3" border>
        <el-descriptions-item label="会话">{{ state.session_id }}</el-descriptions-item>
        <el-descriptions-item label="状态">
          <el-tag :type="statusTag(state.status)" effect="light">{{ state.status }}</el-tag>
        </el-descriptions-item>
        <el-descriptions-item label="工具调用次数">{{ state.tool_call_count }}</el-descriptions-item>
      </el-descriptions>

      <div class="section-title">最终答案</div>
      <el-alert
        :title="state.answer || state.error || '无答案'"
        :type="state.status === 'completed' ? 'success' : 'error'"
        :closable="false"
      />

      <div class="section-title">Workflow 节点轨迹</div>
      <el-timeline>
        <el-timeline-item
          v-for="(event, index) in state.workflow_trace"
          :key="index"
          :timestamp="String(event.event || '')"
        >
          <div class="node-name">{{ event.node }}</div>
          <div v-if="event.detail" class="node-detail">{{ event.detail }}</div>
        </el-timeline-item>
      </el-timeline>
    </div>
  </el-card>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { ElMessage } from 'element-plus'
import { runLangGraph, runWorkflow } from '@/api/assistant'
import type { AgentStateResponse } from '@/types/api'

const engine = ref<'handwritten' | 'langgraph'>('handwritten')
const question = ref('查找知识库中关于 RAG 的资料，如果检索结果不足就补充检索，最后整理一份总结。')
const loading = ref(false)
const state = ref<AgentStateResponse | null>(null)

async function run() {
  const text = question.value.trim()
  if (!text) return

  loading.value = true

  try {
    state.value =
      engine.value === 'handwritten'
        ? await runWorkflow(text)
        : await runLangGraph(text)
  } catch (error) {
    ElMessage.error('Workflow 执行失败，请确认后端服务可用。')
  } finally {
    loading.value = false
  }
}

function statusTag(status: string): 'success' | 'danger' | 'warning' | 'info' {
  if (status === 'completed') return 'success'
  if (status === 'failed') return 'danger'
  if (status === 'waiting_confirmation') return 'warning'
  return 'info'
}
</script>

<style scoped>
.workflow-toolbar {
  display: flex;
  gap: 12px;
  align-items: center;
}

.question-input {
  max-width: 620px;
}

.result-panel {
  margin-top: 24px;
}

.section-title {
  margin: 20px 0 10px;
  font-size: 16px;
  font-weight: 600;
  color: #111827;
}

.node-name {
  font-weight: 600;
  color: #111827;
}

.node-detail {
  margin-top: 4px;
  color: #64748b;
  white-space: pre-wrap;
}
</style>
