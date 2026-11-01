import { http } from './http'
import type {
  DocumentSummary,
  HealthResponse,
  PendingOperation,
  TraceRecord,
} from '@/types/api'

export async function fetchHealth(): Promise<HealthResponse> {
  const response = await http.get<HealthResponse>('/health')
  return response.data
}

export async function fetchDocuments(): Promise<DocumentSummary[]> {
  const response = await http.get<DocumentSummary[]>('/documents')
  return response.data
}

export async function fetchTraces(): Promise<TraceRecord[]> {
  const response = await http.get<TraceRecord[]>('/agent/traces')
  return response.data
}

export async function fetchConfirmations(): Promise<PendingOperation[]> {
  const response = await http.get<PendingOperation[]>('/agent/confirmations')
  return response.data
}
