import { http } from './http'
import type { AgentStateResponse, RagChatResponse } from '@/types/api'

export async function chatRag(question: string): Promise<RagChatResponse> {
  const response = await http.post<RagChatResponse>('/chat', { question })
  return response.data
}

export async function runAgent(
  question: string,
  sessionId?: string,
): Promise<AgentStateResponse> {
  const response = await http.post<AgentStateResponse>('/agent/chat', {
    question,
    session_id: sessionId || null,
  })
  return response.data
}

export async function runWorkflow(
  question: string,
  sessionId?: string,
): Promise<AgentStateResponse> {
  const response = await http.post<AgentStateResponse>('/agent/workflow', {
    question,
    session_id: sessionId || null,
  })
  return response.data
}

export async function runLangGraph(
  question: string,
  sessionId?: string,
): Promise<AgentStateResponse> {
  const response = await http.post<AgentStateResponse>('/agent/langgraph', {
    question,
    session_id: sessionId || null,
  })
  return response.data
}
