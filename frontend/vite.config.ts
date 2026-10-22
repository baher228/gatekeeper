import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import { defineConfig } from 'vite'

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    host: true,
    proxy: { '/api': { target: process.env.VITE_API_TARGET ?? 'http://localhost:8000', changeOrigin: true } },
  },
})
