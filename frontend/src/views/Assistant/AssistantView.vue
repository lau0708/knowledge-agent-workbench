<template>
  <div class="assistant-page">
    <el-card shadow="never" class="session-panel">
      <template #header>
        <div class="panel-header">
          <span>历史会话</span>
          <el-button size="small" type="primary" @click="createNewSession">
            新建会话
          </el-button>
        </div>
      </template>

      <el-menu
        :default-active="chatStore.currentSessionId"
        class="session-menu"
        @select="chatStore.selectSession"
      >
        <el-menu-item
          v-for="session in chatStore.sessions"
          :key="session.id"
          :index="session.id"
        >
          <span class="session-title">{{ session.title }}</span>
        </el-menu-item>
      </el-menu>
    </el-card>

    <el-card shadow="never" class="chat-panel">
      <div class="chat-toolbar">
        <el-radio-group v-model="mode">
          <el-radio-button value="rag">RAG</el-radio-button>
          <el-radio-button value="agent">Agent</el-radio-button>
          <el-radio-button value="workflow">Workflow</el-radio-button>
          <el-radio-button value="langgraph">LangGraph</el-radio-button>
        </el-radio-group>
        <el-button text type="primary" @click="chatStore.clearCurrent()">
          清空当前会话
        </el-button>
      </div>

      <div ref="messageListRef" class="message-list">
        <div
          v-for="message in currentMessages"
          :key="message.id"
          class="message-row"
          :class="message.role"
        >
          <div class="message-bubble">{{ message.content }}</div>
          <el-button
            v-if="message.detail"
            text
            size="small"
            type="primary"
            @click="selectMessage(message)"
          >
            查看执行详情
          </el-button>
        </div>
        <el-empty v-if="currentMessages.length === 0" description="输入问题开始对话" />
      </div>

      <div class="chat-input">
        <el-input
          v-model="question"
          type="textarea"
          :rows="3"
          placeholder="例如：帮我查询知识库中关于 Embedding 的内容，并总结它的作用"
          @keydown.ctrl.enter.prevent="send"
          @keydown.meta.enter.prevent="send"
        />
        <div class="chat-actions">
          <div class="hint">Ctrl + Enter 发送</div>
          <el-button type="primary" :loading="sending" @click="send">发送</el-button>
        </div>
      </div>
    </el-card>

    <el-card shadow="never" class="detail-panel">
      <template #header>
        <span>执行详情</span>
      </template>

      <el-empty v-if="!selectedDetail" description="暂无执行详情" />

      <div v-else>
        <div v-if="selectedDetail.kind === 'rag'">
          <div class="detail-section">检索来源</div>
          <el-table :data="selectedDetail.response.context" max-height="220">
            <el-table-column prop="source" label="来源" min-width="140" show-overflow-tooltip />
            <el-table-column prop="score" label="分数" width="90" />
            <el-table-column prop="content" label="内容" min-width="200" show-overflow-tooltip />
          </el-table>

          <div class="detail-section">生成评估</div>
          <pre class="detail-pre">{{ JSON.stringify(selectedDetail.response.evaluation, null, 2) }}</pre>
        </div>

        <div v-else>
          <div class="detail-section">状态</div>
          <el-tag :type="statusTag(selectedDetail.state.status)" effect="light">
            {{ selectedDetail.state.status }}
          </el-tag>

          <div class="detail-section">工具调用</div>
          <el-timeline>
            <el-timeline-item
              v-for="(tool, index) in selectedDetail.state.tool_calls"
              :key="index"
              :timestamp="tool.status"
            >
              <div class="tool-name">{{ tool.name }}</div>
              <pre class="detail-pre">{{ JSON.stringify(tool.arguments, null, 2) }}</pre>
              <div v-if="tool.result" class="tool-result">{{ tool.result }}</div>
              <div v-if="tool.error" class="tool-error">{{ tool.error }}</div>
            </el-timeline-item>
          </el-timeline>

          <div class="detail-section">Workflow 轨迹</div>
          <el-timeline v-if="selectedDetail.state.workflow_trace.length">
            <el-timeline-item
              v-for="(event, index) in selectedDetail.state.workflow_trace"
              :key="index"
              :timestamp="String(event.event || '')"
            >
              {{ event.node }}
            </el-timeline-item>
          </el-timeline>
          <el-empty v-else description="暂无 Workflow 轨迹" :image-size="60" />
        </div>
      </div>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, ref } from 'vue'
import { ElMessage } from 'element-plus'
import {
  chatRag,
  runAgent,
  runLangGraph,
  runWorkflow,
} from '@/api/assistant'
import { useChatStore, type ChatMessage } from '@/stores/chat'
import type { AgentStateResponse, RagChatResponse } from '@/types/api'

type RunDetail =
  | { kind: 'rag'; response: RagChatResponse }
  | { kind: 'agent' | 'workflow' | 'langgraph'; state: AgentStateResponse }

const chatStore = useChatStore()
const question = ref('')
const mode = ref<'rag' | 'agent' | 'workflow' | 'langgraph'>('agent')
const sending = ref(false)
const selectedDetail = ref<RunDetail | null>(null)
const messageListRef = ref<HTMLElement | null>(null)

const currentMessages = computed(() => chatStore.currentSession?.messages || [])

function createNewSession() {
  chatStore.createSession()
  selectedDetail.value = null
}

function addMessage(message: ChatMessage) {
  chatStore.ensureSession()
  chatStore.addMessage(chatStore.currentSessionId, message)
}

function selectMessage(message: ChatMessage) {
  if (message.detail) {
    selectedDetail.value = message.detail as RunDetail
  }
}

async function scrollToBottom() {
  await nextTick()
  if (messageListRef.value) {
    messageListRef.value.scrollTop = messageListRef.value.scrollHeight
  }
}

async function send() {
  const text = question.value.trim()
  if (!text) return

  chatStore.ensureSession()
  const sessionId = chatStore.currentSessionId
  addMessage({ id: crypto.randomUUID(), role: 'user', content: text })
  question.value = ''
  sending.value = true

  try {
    if (mode.value === 'rag') {
      const response = await chatRag(text)
      addMessage({
        id: crypto.randomUUID(),
        role: 'assistant',
        content: response.answer,
        detail: { kind: 'rag', response },
      })
      selectedDetail.value = { kind: 'rag', response }
      return
    }

    const state =
      mode.value === 'agent'
        ? await runAgent(text, sessionId)
        : mode.value === 'workflow'
          ? await runWorkflow(text, sessionId)
          : await runLangGraph(text, sessionId)

    const detail: RunDetail = {
      kind: mode.value as 'agent' | 'workflow' | 'langgraph',
      state,
    }
    addMessage({
      id: crypto.randomUUID(),
      role: 'assistant',
      content: state.answer || state.error || state.status,
      detail,
    })
    selectedDetail.value = detail
  } catch (error) {
    addMessage({
      id: crypto.randomUUID(),
      role: 'assistant',
      content: '请求失败，请确认后端服务可用。',
    })
    ElMessage.error('请求失败，请确认后端服务可用。')
  } finally {
    sending.value = false
    await scrollToBottom()
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
.assistant-page {
  display: grid;
  grid-template-columns: 240px 1fr 380px;
  gap: 16px;
  min-height: 600px;
}

.session-panel,
.chat-panel,
.detail-panel {
  min-height: 600px;
}

.panel-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.session-menu {
  border-right: none;
}

.session-title {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.chat-panel {
  display: flex;
  flex-direction: column;
}

.chat-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 16px;
}

.message-list {
  flex: 1;
  min-height: 420px;
  max-height: 620px;
  overflow-y: auto;
  padding-right: 8px;
}

.message-row {
  margin-bottom: 16px;
}

.message-row.user {
  display: flex;
  justify-content: flex-end;
}

.message-row.assistant {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
}

.message-bubble {
  max-width: 80%;
  padding: 10px 14px;
  border-radius: 12px;
  white-space: pre-wrap;
}

.message-row.user .message-bubble {
  background: #2563eb;
  color: #ffffff;
}

.message-row.assistant .message-bubble {
  background: #ffffff;
  border: 1px solid #e5e7eb;
  color: #111827;
}

.chat-input {
  margin-top: 16px;
}

.chat-actions {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-top: 10px;
}

.hint {
  color: #94a3b8;
  font-size: 12px;
}

.detail-section {
  margin: 16px 0 8px;
  font-weight: 600;
  color: #111827;
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

.tool-name {
  font-weight: 600;
}

.tool-result {
  color: #16a34a;
}

.tool-error {
  color: #dc2626;
}
</style>
