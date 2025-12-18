import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import path from 'path'

// https://vitejs.dev/config/
export default defineConfig({
    plugins: [react()],
    resolve: {
        alias: {
            '@': path.resolve(__dirname, './src'),
            '@/components': path.resolve(__dirname, './src/components'),
            '@/pages': path.resolve(__dirname, './src/pages'),
            '@/services': path.resolve(__dirname, './src/services'),
            '@/hooks': path.resolve(__dirname, './src/hooks'),
            '@/styles': path.resolve(__dirname, './src/styles'),
            '@/types': path.resolve(__dirname, './src/types'),
            '@/utils': path.resolve(__dirname, './src/utils'),
        },
    },
    server: {
        port: 3000,
        proxy: {
            '/api': {
                target: 'http://localhost:8000',
                changeOrigin: true,
            },
        },
    },
})
