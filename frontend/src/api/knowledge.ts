import { http } from './http'
import type {
  DeleteDocumentResponse,
  DocumentDetail,
  DocumentSummary,
} from '@/types/api'

export async function fetchDocuments(): Promise<DocumentSummary[]> {
  const response = await http.get<DocumentSummary[]>('/documents')
  return response.data
}

export async function fetchDocumentDetail(documentId: number): Promise<DocumentDetail> {
  const response = await http.get<DocumentDetail>(`/documents/${documentId}`)
  return response.data
}

export async function uploadDocument(
  file: File,
  onProgress?: (percent: number) => void,
): Promise<DocumentDetail> {
  const formData = new FormData()
  formData.append('file', file)

  const response = await http.post<DocumentDetail>('/documents', formData, {
    headers: {
      'Content-Type': 'multipart/form-data',
    },
    onUploadProgress: (event) => {
      if (!onProgress || event.total === 0) return
      onProgress(Math.round((event.loaded * 100) / (event.total || 1)))
    },
  })

  return response.data
}

export async function updateDocument(
  documentId: number,
  content: string,
): Promise<DocumentDetail> {
  const response = await http.put<DocumentDetail>(`/documents/${documentId}`, {
    content,
  })
  return response.data
}

export async function deleteDocument(
  documentId: number,
): Promise<DeleteDocumentResponse> {
  const response = await http.delete<DeleteDocumentResponse>(`/documents/${documentId}`)
  return response.data
}
