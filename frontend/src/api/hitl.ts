import { http } from './http'
import type { PendingOperation } from '@/types/api'

export async function fetchPendingOperations(
  sessionId?: string,
): Promise<PendingOperation[]> {
  const response = await http.get<PendingOperation[]>('/agent/confirmations', {
    params: sessionId ? { session_id: sessionId } : undefined,
  })
  return response.data
}

export async function fetchPendingOperation(
  operationId: string,
): Promise<PendingOperation> {
  const response = await http.get<PendingOperation>(
    `/agent/confirmations/${operationId}`,
  )
  return response.data
}

export async function modifyOperation(
  operationId: string,
  argumentsValue: Record<string, unknown>,
): Promise<PendingOperation> {
  const response = await http.post<PendingOperation>(
    `/agent/confirmations/${operationId}/modify`,
    { arguments: argumentsValue },
  )
  return response.data
}

export async function approveOperation(
  operationId: string,
  argumentsValue?: Record<string, unknown>,
): Promise<Record<string, unknown>> {
  const response = await http.post<Record<string, unknown>>(
    `/agent/confirmations/${operationId}/approve`,
    argumentsValue ? { arguments: argumentsValue } : {},
  )
  return response.data
}

export async function rejectOperation(
  operationId: string,
  reason?: string,
): Promise<Record<string, unknown>> {
  const response = await http.post<Record<string, unknown>>(
    `/agent/confirmations/${operationId}/reject`,
    reason ? { reason } : {},
  )
  return response.data
}
