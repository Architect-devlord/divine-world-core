// C:\Users\user\Desktop\divineworld\dw_agent\electron\react-app\vite.config.js
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react-swc'

// ─────────────────────────────────────────────────────────────────────────────
// Chunk strategy — keeps every output chunk under Rollup's 500 kB warning.
//
//   three        — Three.js core + JSM loaders  (~600 kB raw, rarely changes)
//   vendor-react — React + ReactDOM + framer-motion
//   vendor-ui    — lucide-react icons
//   vendor-misc  — all other node_modules
//   index        — your app code (small, changes every deploy)
// ─────────────────────────────────────────────────────────────────────────────
function manualChunks(id) {
  if (id.includes('node_modules/three'))           return 'three'
  if (id.includes('node_modules/react/') ||
      id.includes('node_modules/react-dom/') ||
      id.includes('node_modules/framer-motion/'))  return 'vendor-react'
  if (id.includes('node_modules/lucide-react'))    return 'vendor-ui'
  if (id.includes('node_modules/'))               return 'vendor-misc'
}

export default defineConfig({
  plugins: [react()],

  // Dev server — proxy API + WebSocket to the FastAPI agent backend
  server: {
    port: 8765,
    strictPort: true,
    open: true,
    proxy: {
      '/api':         { target: 'http://127.0.0.1:11400', changeOrigin: true },
      '/status':      { target: 'http://127.0.0.1:11400', changeOrigin: true },
      '/thoughts':   { target: 'http://127.0.0.1:11400', changeOrigin: true },
      '/agent-ws':    {
        target: 'ws://127.0.0.1:11400',
        ws: true,
        rewrite: path => path.replace(/^\/agent-ws/, '/ws'),
      },
      '/chat':        { target: 'http://127.0.0.1:11400', changeOrigin: true },
    },
  },

  // CRITICAL: relative paths so dist/ works served from inside the .exe
  base: './',

  build: {
    outDir: 'dist',
    emptyOutDir: true,
    assetsDir: 'assets',

    rollupOptions: {
      output: {
        manualChunks,
        // Predictable asset names (same as original)
        assetFileNames: 'assets/[name].[ext]',
        chunkFileNames: 'assets/[name].[hash].js',
        entryFileNames: 'assets/[name].[hash].js',
      },
    },

    // ── Minifier selection ────────────────────────────────────────────
    // rolldown-vite v7+ (which this project uses) dropped the bundled
    // esbuild minifier — it now uses Oxc natively and requires esbuild
    // to be installed as a separate package if you set minify:'esbuild'.
    // 'oxc' is rolldown-vite's built-in minifier: zero extra deps, faster
    // than esbuild, and produces virtually identical output size.
    // If you ever downgrade to classic Vite <6 swap this back to 'esbuild'.
    minify: 'oxc',

    // Raise the warning limit — Three.js is ~600 kB even after chunking
    chunkSizeWarningLimit: 1500,

    target: 'esnext',
    sourcemap: false,
  },

  // Preview server (for testing built dist/ locally)
  preview: {
    port: 8766,
    strictPort: true,
    open: true,
  },
})