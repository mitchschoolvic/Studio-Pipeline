import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    host: '0.0.0.0',  // Allow network access during development
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
        ws: true, // Enable WebSocket proxying
      },
    },
  },
  define: {
    // Expose environment variables to the app
    'import.meta.env.VITE_APP_VERSION': JSON.stringify(process.env.VITE_APP_VERSION),
    'import.meta.env.VITE_APP_DEV_MODE': JSON.stringify(process.env.VITE_APP_DEV_MODE),
    'import.meta.env.VITE_APP_AI_ENABLED': JSON.stringify(process.env.VITE_APP_AI_ENABLED),
  },
})
