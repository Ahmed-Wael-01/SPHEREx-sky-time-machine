import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// In dev, /api goes to Flask on :5000. /data is served from public/data by Vite itself.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: { '/api': 'http://localhost:5000' },
  },
})
