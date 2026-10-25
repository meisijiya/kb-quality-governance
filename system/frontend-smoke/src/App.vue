<script setup>
// 烟测页：数据不写死在本工程里，构建时用 Vite 的 ?raw 直接读仓库真实产物
// poc/kbgovernance/gap_intents_best.csv，运行时解析成 el-table 的行数据。
import { computed } from 'vue'
import csvRaw from '../../../poc/kbgovernance/gap_intents_best.csv?raw'

// 只渲染这三列（业务意图 / 簇数 / 意图覆盖度），不渲染 is_true_gap 等评测依据列。
const COLUMNS = ['intent', 'n_clusters', 'min_cover_median']

function parseCsv(text) {
  const lines = text
    // 实测发现：poc/kbgovernance/gap_intents_best.csv 带 UTF-8 BOM，
    // 不去掉会让首列表头变成 "﻿intent"，按列名取列会整列取空。
    .replace(/^\uFEFF/, '')
    .replace(/\r\n/g, '\n')
    .split('\n')
    .filter((line) => line.trim() !== '')
  const header = lines[0].split(',').map((name) => name.trim())
  const idx = COLUMNS.map((name) => header.indexOf(name))
  return lines.slice(1).map((line) => {
    const cells = line.split(',')
    const row = {}
    COLUMNS.forEach((name, i) => {
      row[name] = cells[idx[i]]
    })
    return row
  })
}

const rows = computed(() => parseCsv(csvRaw))
const sourcePath = 'poc/kbgovernance/gap_intents_best.csv'
</script>

<template>
  <div class="smoke">
    <h1 class="title">前端烟测：Element Plus el-table</h1>
    <p class="meta">
      数据源：<code>{{ sourcePath }}</code>（构建时以 <code>?raw</code> 读入，运行时解析；
      共 {{ rows.length }} 行，取前 5 行）
    </p>
    <el-table :data="rows" class="table">
      <el-table-column prop="intent" label="业务意图" min-width="220" />
      <el-table-column prop="n_clusters" label="簇数" width="120" align="right" />
      <el-table-column prop="min_cover_median" label="意图覆盖度" width="150" align="right" />
    </el-table>
  </div>
</template>

<style scoped>
.smoke {
  max-width: 960px;
  margin: 0 auto;
  padding: 32px 24px;
  font-family: system-ui, -apple-system, 'Segoe UI', 'Microsoft YaHei', sans-serif;
  font-size: 14px;
  line-height: 1.6;
  color: #303133;
  background: #ffffff;
}

.title {
  font-size: 20px;
  font-weight: 600;
  margin: 0 0 8px;
}

.meta {
  margin: 0 0 20px;
  color: #606266;
}

code {
  font-family: ui-monospace, Consolas, monospace;
  background: #f5f7fa;
  padding: 1px 5px;
  border-radius: 3px;
}
</style>
