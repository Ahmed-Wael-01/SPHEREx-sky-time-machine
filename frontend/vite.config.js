import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// In dev, /api goes to Flask on :5000. /data is served from public/data by Vite itself.
// VITE_BASE is the folder the site is served from: "/" on Vercel or locally,
// "/SPHEREx-sky-time-machine/" on GitHub Pages (set by .github/workflows/pages.yml).
export default defineConfig({
  base: process.env.VITE_BASE || '/',
  plugins: [react()],
  server: {
    port: 5173,
    proxy: { '/api': 'http://localhost:5000' },
  },
})
