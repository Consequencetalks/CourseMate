<script setup lang="ts">
import { useRoute } from "vue-router";

const route = useRoute();
</script>

<template>
  <el-container class="app-shell">
    <el-header class="app-header">
      <div class="header-bar">
        <div class="brand">CourseMate</div>
        <el-menu mode="horizontal" router :ellipsis="false" :default-active="route.path">
          <el-menu-item index="/documents">Documents</el-menu-item>
          <el-menu-item index="/chat">Chat</el-menu-item>
          <el-menu-item index="/quiz">Quiz</el-menu-item>
        </el-menu>
      </div>
    </el-header>
    <el-main>
      <router-view />
    </el-main>
  </el-container>
</template>
