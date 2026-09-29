import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// 開発時（npm run dev）は /api をローカルのFastAPIへ転送する
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      "/api": "http://localhost:8000",
    },
  },
});
