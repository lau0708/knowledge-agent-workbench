import { defineStore } from 'pinia'

export interface ChatMessage {
  id: string
  role: 'user' | 'assistant'
  content: string
  detail?: Record<string, unknown>
}

export interface ChatSession {
  id: string
  title: string
  messages: ChatMessage[]
}

function createId(): string {
  return `ui-${Date.now()}-${Math.random().toString(16).slice(2, 8)}`
}

export const useChatStore = defineStore('chat', {
  state: () => ({
    sessions: [] as ChatSession[],
    currentSessionId: '',
  }),

  getters: {
    currentSession(state): ChatSession | undefined {
      return state.sessions.find((session) => session.id === state.currentSessionId)
    },
  },

  actions: {
    createSession(question = '新会话') {
      const session: ChatSession = {
        id: createId(),
        title: question.slice(0, 24) || '新会话',
        messages: [],
      }
      this.sessions.unshift(session)
      this.currentSessionId = session.id
      return session
    },

    ensureSession() {
      return this.currentSession || this.createSession()
    },

    selectSession(sessionId: string) {
      this.currentSessionId = sessionId
    },

    addMessage(sessionId: string, message: ChatMessage) {
      const session = this.sessions.find((item) => item.id === sessionId)
      if (!session) return
      session.messages.push(message)
      if (session.messages.length === 1 && message.role === 'user') {
        session.title = message.content.slice(0, 24)
      }
    },

    clearCurrent() {
      const session = this.currentSession
      if (session) session.messages = []
    },
  },
})
