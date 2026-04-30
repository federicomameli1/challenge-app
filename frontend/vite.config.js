import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), "");
  const requestedBackendTarget =
    env.VITE_DEV_BACKEND_PROXY || env.VITE_AGENT_BACKEND_URL || "";
  const backendTarget = /^https?:\/\//i.test(requestedBackendTarget)
    ? requestedBackendTarget
    : "http://127.0.0.1:8001";

  return {
    plugins: [react()],
    server: {
      proxy: {
        "/api": {
          target: backendTarget,
          changeOrigin: true,
          rewrite: (path) => path.replace(/^\/api/, ""),
        },
      },
    },
    test: {
      environment: "jsdom",
      setupFiles: ["./src/setupTests.js"],
      globals: true,
    },
  };
});
