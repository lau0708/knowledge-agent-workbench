import { http } from './http'
import type { TraceAnalysis, TraceRecord } from '@/types/api'

export async function fetchTraceList(sessionId?: string): Promise<TraceRecord[]> {
  const response = await http.get<TraceRecord[]>('/agent/traces', {
    params: sessionId ? { session_id: sessionId } : undefined,
  })
  return response.data
}

export async function fetchTraceDetail(traceId: string): Promise<TraceRecord> {
  const response = await http.get<TraceRecord>(`/agent/traces/${traceId}`)
  return response.data
}

export async function fetchTraceAnalysis(traceId: string): Promise<TraceAnalysis> {
  const response = await http.get<TraceAnalysis>(
    `/agent/traces/${traceId}/analysis`,
  )
  return response.data
}
