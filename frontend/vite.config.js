import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import { defineConfig } from 'vite'

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    host: true,
    port: 5173,
    proxy: {
      '/api': { target: process.env.API_URL || 'http://localhost:8000', changeOrigin: true },
      '/ws': { target: process.env.API_URL || 'http://localhost:8000', ws: true },
    },
  },
})
