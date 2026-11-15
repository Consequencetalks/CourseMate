<script setup lang="ts">
import { onMounted, ref } from "vue";
import { useRoute } from "vue-router";
import { getHealth } from "./api/client";

const route = useRoute();
const apiStatus = ref("checking");

onMounted(async () => {
  try {
    const health = await getHealth();
    apiStatus.value = health.status;
  } catch (error) {
    apiStatus.value = error instanceof Error ? error.message : "unavailable";
  }
});
</script>

<template>
  <el-container class="app-shell">
    <el-header class="app-header">
      <div class="brand">CourseMate</div>
      <el-menu mode="horizontal" router :ellipsis="false" :default-active="route.path">
        <el-menu-item index="/documents">Documents</el-menu-item>
        <el-menu-item index="/chat">Chat</el-menu-item>
        <el-menu-item index="/quiz">Quiz</el-menu-item>
      </el-menu>
      <div class="api-status">API: {{ apiStatus }}</div>
    </el-header>
    <el-main>
      <router-view />
    </el-main>
  </el-container>
</template>
