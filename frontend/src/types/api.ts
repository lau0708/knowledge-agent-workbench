export interface HealthResponse {
  status: string
  service: string
}

export interface DocumentSummary {
  id: number
  source: string
  created_at: string
  updated_at: string
  chunk_count: number
}

export interface DocumentChunk {
  chunk_id: string
  chunk_index: number
  content: string
}

export interface DocumentDetail {
  id: number
  source: string
  created_at: string
  updated_at: string
  chunks: DocumentChunk[]
}

export interface DeleteDocumentResponse {
  deleted: boolean
  id: number
  source: string
}

export interface TraceRecord {
  trace_id: string
  session_id: string
  question: string
  status: string
  started_at: string
  updated_at: string
  duration_ms: number | null
  messages_count: number
  tool_calls: Array<{
    name?: string
    arguments?: Record<string, unknown>
    status?: string
    result?: string | null
    error?: string | null
    tool_call_id?: string | null
    [key: string]: unknown
  }>
  workflow_trace: Array<{
    node?: string
    event?: string
    detail?: string | null
    [key: string]: unknown
  }>
  answer: string | null
  error: string | null
  pending_operation_id: string | null
}

export interface PendingOperation {
  operation_id: string
  session_id: string
  tool_name: string
  arguments: Record<string, unknown>
  tool_call_id: string | null
  status: string
  result: string | null
  error: string | null
  created_at: string
  updated_at: string
  expires_at: string | null
}

export interface RagChatResponse {
  question: string
  context: Array<{
    source: string
    content: string
    score: number
  }>
  answer: string
  evaluation: Record<string, unknown> | null
}

export interface AgentStateResponse {
  session_id: string
  user_input: string
  status: string
  messages: Array<Record<string, unknown>>
  tool_calls: Array<{
    name: string
    arguments: Record<string, unknown>
    status: string
    result: string | null
    error: string | null
    tool_call_id: string | null
  }>
  tool_results: Array<Record<string, unknown>>
  tool_call_count: number
  workflow_trace: Array<Record<string, unknown>>
  pending_operation_id: string | null
  error: string | null
  answer: string | null
  created_at: string
  updated_at: string
}

export interface TraceAnalysis {
  status: string
  failure_stage: string
  error_type: string | null
  has_error: boolean
  [key: string]: unknown
}
