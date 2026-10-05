import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// In development the API runs on :8000; in production FastAPI serves this app itself.
const backend = 'http://localhost:8000'

export default defineConfig({
  plugins: [react()],
  server: { proxy: { '/api': backend, '/agent': backend, '/tools': backend } },
})
