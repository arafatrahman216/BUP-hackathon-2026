import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    // Docker bind mounts on macOS/Windows don't emit file events: set CHOKIDAR_USEPOLLING=true.
    watch: process.env.CHOKIDAR_USEPOLLING === 'true' ? { usePolling: true, interval: 300 } : undefined,
  },
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: ['./src/test/setup.js'],
    css: { modules: { classNameStrategy: 'non-scoped' } },
    // Tests should never depend on a developer's .env
    env: { VITE_API_BASE_URL: 'http://api.test/api/v1' },
  },
})
