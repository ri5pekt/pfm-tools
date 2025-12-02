// vite.config.js
import { fileURLToPath, URL } from "node:url";
import { defineConfig } from "vite";
import vue from "@vitejs/plugin-vue";

export default defineConfig({
    plugins: [vue()],
    resolve: {
        alias: {
            "@": fileURLToPath(new URL("./src", import.meta.url)),
        },
    },
    server: {
        host: "0.0.0.0",
        port: 5173,
        strictPort: true,
        // If later you want to proxy through Vite to avoid CORS, you can uncomment:
        // proxy: {
        //   '/api': {
        //     target: 'http://localhost:8000',
        //     changeOrigin: true,
        //   },
        // },
    },
    build: {
        sourcemap: true,
    },
});
