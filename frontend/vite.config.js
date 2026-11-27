import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// The dev server forwards API calls to FastAPI, so the frontend holds no backend URL or secrets.
const API = process.env.VITE_API_PROXY || 'http://localhost:8000'

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: { proxy: { '/api': API, '/health': API } },
  preview: { proxy: { '/api': API, '/health': API } },
})
