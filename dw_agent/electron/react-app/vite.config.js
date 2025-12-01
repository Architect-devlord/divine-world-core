// C:\Users\user\Desktop\divineworld\dw_agent\electron\react-app\vite.config.js
// FIXED VERSION - Ensures proper bundling for standalone .exe

import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react-swc'

export default defineConfig({
    plugins: [react()],
    
    // Development server config
    server: {
        port: 8765,
        strictPort: true,
        open: true
    },
    
    // CRITICAL: Build configuration for standalone exe
    build: {
        outDir: 'dist',  // Output directory
        emptyOutDir: true,  // Clean before build
        
        // CRITICAL: Assets must be relative for standalone serving
        assetsDir: 'assets',
        
        // Ensure proper chunking
        rollupOptions: {
            output: {
                manualChunks: undefined,  // Single bundle for simplicity
                // Keep asset names predictable
                assetFileNames: 'assets/[name].[ext]',
                chunkFileNames: 'assets/[name].[hash].js',
                entryFileNames: 'assets/[name].[hash].js',
            }
        },
        
        // Source maps for debugging (optional)
        sourcemap: false,
        
        // Optimize for size
        minify: 'terser',
        
        // Target modern browsers
        target: 'esnext',
    },
    
    // CRITICAL: Use relative paths for bundled exe
    base: './',  // This makes all paths relative!
    
    // Preview server (for testing built version)
    preview: {
        port: 8766,
        strictPort: true,
        open: true
    }
})