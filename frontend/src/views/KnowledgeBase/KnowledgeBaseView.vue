<template>
  <div v-loading="loading">
    <el-alert
      v-if="errorMessage"
      :title="errorMessage"
      type="error"
      :closable="false"
      show-icon
    />

    <el-card shadow="never">
      <div class="toolbar">
        <div>
          <div class="toolbar-title">Markdown 文档管理</div>
          <div class="toolbar-note">上传后自动建立 SQLite 与 ChromaDB 双存储索引。</div>
        </div>

        <el-upload
          :show-file-list="false"
          :http-request="handleUpload"
          accept=".md,text/markdown"
        >
          <el-button type="primary">上传 Markdown</el-button>
        </el-upload>
      </div>

      <el-progress
        v-if="uploadProgress !== null"
        :percentage="uploadProgress"
        class="upload-progress"
      />
    </el-card>

    <el-card shadow="never" class="table-card">
      <el-table :data="documents" empty-text="暂无文档">
        <el-table-column prop="id" label="ID" width="80" />
        <el-table-column prop="source" label="来源" min-width="260" show-overflow-tooltip />
        <el-table-column prop="chunk_count" label="Chunk" width="100" />
        <el-table-column prop="updated_at" label="更新时间" min-width="180" />
        <el-table-column label="操作" width="230" fixed="right">
          <template #default="{ row }">
            <el-button size="small" @click="viewDetail(row.id)">详情</el-button>
            <el-button size="small" type="primary" @click="openUpdate(row.id)">更新</el-button>
            <el-button size="small" type="danger" @click="confirmDelete(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-dialog v-model="detailVisible" title="文档详情" width="720px">
      <div v-loading="detailLoading">
        <el-descriptions :column="2" border>
          <el-descriptions-item label="ID">{{ detail?.id }}</el-descriptions-item>
          <el-descriptions-item label="来源">{{ detail?.source }}</el-descriptions-item>
          <el-descriptions-item label="创建时间">{{ detail?.created_at }}</el-descriptions-item>
          <el-descriptions-item label="更新时间">{{ detail?.updated_at }}</el-descriptions-item>
        </el-descriptions>

        <el-table :data="detail?.chunks || []" class="chunk-table" max-height="360">
          <el-table-column prop="chunk_index" label="序号" width="80" />
          <el-table-column prop="chunk_id" label="Chunk ID" min-width="160" />
          <el-table-column prop="content" label="内容" min-width="280" show-overflow-tooltip />
        </el-table>
      </div>
    </el-dialog>

    <el-dialog v-model="updateVisible" title="更新文档" width="720px">
      <el-input
        v-model="updateContent"
        type="textarea"
        :rows="14"
        placeholder="请输入新的 Markdown 内容"
      />
      <template #footer>
        <el-button @click="updateVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="saveUpdate">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import type { UploadRequestOptions } from 'element-plus'
import {
  deleteDocument,
  fetchDocumentDetail,
  fetchDocuments,
  updateDocument,
  uploadDocument,
} from '@/api/knowledge'
import type { DocumentDetail, DocumentSummary } from '@/types/api'

const loading = ref(false)
const saving = ref(false)
const detailLoading = ref(false)
const errorMessage = ref('')
const uploadProgress = ref<number | null>(null)

const documents = ref<DocumentSummary[]>([])
const detail = ref<DocumentDetail | null>(null)
const detailVisible = ref(false)

const updatingId = ref<number | null>(null)
const updateVisible = ref(false)
const updateContent = ref('')

async function loadDocuments() {
  loading.value = true
  errorMessage.value = ''

  try {
    documents.value = await fetchDocuments()
  } catch (error) {
    errorMessage.value = '文档列表加载失败，请确认后端服务已启动。'
  } finally {
    loading.value = false
  }
}

async function handleUpload(options: UploadRequestOptions) {
  const file = options.file

  if (!(file instanceof File)) {
    ElMessage.error('上传文件无效')
    return
  }

  uploadProgress.value = 0

  try {
    await uploadDocument(file, (percent) => {
      uploadProgress.value = percent
    })
    ElMessage.success('文档上传成功')
    await loadDocuments()
  } catch (error) {
    ElMessage.error('文档上传失败，请确认文件是 Markdown 且未重名。')
  } finally {
    uploadProgress.value = null
  }
}

async function viewDetail(documentId: number) {
  detailVisible.value = true
  detailLoading.value = true
  detail.value = null

  try {
    detail.value = await fetchDocumentDetail(documentId)
  } catch (error) {
    ElMessage.error('文档详情加载失败')
  } finally {
    detailLoading.value = false
  }
}

async function openUpdate(documentId: number) {
  updatingId.value = documentId
  updateVisible.value = true
  updateContent.value = ''

  try {
    const current = await fetchDocumentDetail(documentId)
    updateContent.value = current.chunks.map((chunk) => chunk.content).join('\n\n')
  } catch (error) {
    ElMessage.error('文档内容加载失败')
  }
}

async function saveUpdate() {
  if (updatingId.value === null) return

  saving.value = true

  try {
    await updateDocument(updatingId.value, updateContent.value)
    ElMessage.success('文档更新成功')
    updateVisible.value = false
    await loadDocuments()
  } catch (error) {
    ElMessage.error('文档更新失败')
  } finally {
    saving.value = false
  }
}

async function confirmDelete(document: DocumentSummary) {
  try {
    await ElMessageBox.confirm(
      `确认删除文档 ${document.id}？该操作会同步删除 SQLite 和 ChromaDB 数据。`,
      '删除确认',
      {
        type: 'warning',
        confirmButtonText: '删除',
        cancelButtonText: '取消',
      },
    )
  } catch {
    return
  }

  try {
    await deleteDocument(document.id)
    ElMessage.success('文档删除成功')
    await loadDocuments()
  } catch (error) {
    ElMessage.error('文档删除失败')
  }
}

onMounted(loadDocuments)
</script>

<style scoped>
.toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.toolbar-title {
  font-size: 18px;
  font-weight: 600;
  color: #111827;
}

.toolbar-note {
  margin-top: 6px;
  color: #64748b;
  font-size: 13px;
}

.upload-progress {
  margin-top: 16px;
}

.table-card {
  margin-top: 16px;
}

.chunk-table {
  margin-top: 16px;
}
</style>
