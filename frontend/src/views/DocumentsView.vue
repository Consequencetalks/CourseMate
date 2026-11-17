<script setup lang="ts">
import { onMounted, ref } from "vue";
import { ElMessageBox, type UploadFile, type UploadInstance } from "element-plus";
import { deleteDocument, documentFileUrl, listDocuments, uploadDocument } from "../api/documents";
import type { DocumentOut } from "../types";

const uploadRef = ref<UploadInstance>();
const documents = ref<DocumentOut[]>([]);
const uploading = ref(false);
const message = ref("");
const warnings = ref<string[]>([]);
const error = ref("");

async function loadDocuments() {
  documents.value = await listDocuments();
}

onMounted(async () => {
  try {
    await loadDocuments();
  } catch (err) {
    error.value = err instanceof Error ? err.message : "Could not load documents.";
  }
});

async function onFile(uploadFile: UploadFile) {
  const file = uploadFile.raw;
  uploadRef.value?.clearFiles();
  if (!file || uploading.value) {
    return;
  }
  uploading.value = true;
  error.value = "";
  message.value = "";
  warnings.value = [];
  try {
    const created = await uploadDocument(file);
    message.value = `Imported ${created.filename} with ${created.chunk_count} chunks.`;
    warnings.value = created.warnings;
    await loadDocuments();
  } catch (err) {
    error.value = err instanceof Error ? err.message : "Upload failed.";
  } finally {
    uploading.value = false;
  }
}

function openDocument(id: string) {
  window.open(documentFileUrl(id), "_blank");
}

async function removeDocument(row: DocumentOut) {
  try {
    await ElMessageBox.confirm(`Delete ${row.filename}?`, "Delete document", {
      confirmButtonText: "Delete",
      cancelButtonText: "Cancel",
      type: "warning",
    });
  } catch {
    return;
  }
  error.value = "";
  try {
    await deleteDocument(row.id);
    await loadDocuments();
  } catch (err) {
    error.value = err instanceof Error ? err.message : "Delete failed.";
  }
}
</script>

<template>
  <section class="page documents-page">
    <h1>Documents</h1>
    <p>Upload one course PDF at a time. The file is indexed after text is extracted.</p>
    <el-upload
      ref="uploadRef"
      :auto-upload="false"
      :show-file-list="false"
      :disabled="uploading"
      accept="application/pdf,.pdf"
      :on-change="onFile"
    >
      <el-button type="primary" :loading="uploading" :disabled="uploading">Upload PDF</el-button>
    </el-upload>
    <el-alert v-if="message" class="notice" type="success" :title="message" show-icon :closable="false" />
    <el-alert
      v-for="warning in warnings"
      :key="warning"
      class="notice"
      type="warning"
      :title="warning"
      show-icon
      :closable="false"
    />
    <el-alert v-if="error" class="notice" type="error" :title="error" show-icon :closable="false" />
    <el-table :data="documents" class="document-table" empty-text="No documents yet.">
      <el-table-column prop="filename" label="File" />
      <el-table-column prop="page_count" label="Pages" width="90" />
      <el-table-column prop="chunk_count" label="Chunks" width="100" />
      <el-table-column label="Actions" width="180">
        <template #default="{ row }">
          <el-button link type="primary" @click="openDocument(row.id)">Open</el-button>
          <el-button link type="danger" @click="removeDocument(row)">Delete</el-button>
        </template>
      </el-table-column>
    </el-table>
  </section>
</template>
