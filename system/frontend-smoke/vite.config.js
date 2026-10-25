import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

// 烟测工程配置：只做「能装、能构建、能渲染 el-table」一件事，不含业务代码。
export default defineConfig({
  plugins: [vue()],
  // 相对 base：构建产物可被后端静态挂载到任意路径，也可直接用 file:// 打开
  base: './',
  server: {
    fs: {
      // ?raw 需要读取仓库根下的 poc/kbgovernance/gap_intents_best.csv
      allow: ['../..'],
    },
  },
})
