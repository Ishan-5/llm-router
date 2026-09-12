import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: { port: 5173 },
  build: {
    rollupOptions: {
      output: {
        manualChunks(id) {
          if (id.includes('node_modules/recharts') || id.includes('node_modules/recharts'))
            return 'charts'
          if (id.includes('node_modules/react') || id.includes('node_modules/react-dom') || id.includes('node_modules/react-router') || id.includes('node_modules/scheduler'))
            return 'react-vendor'
          if (id.includes('node_modules/markdown') || id.includes('node_modules/hast') || id.includes('node_modules/mdast') || id.includes('node_modules/micromark') || id.includes('node_modules/remark') || id.includes('node_modules/unist') || id.includes('node_modules/comma-separated-tokens'))
            return 'markdown'
          if (id.includes('node_modules'))
            return 'vendor'
        },
      },
    },
  },
})