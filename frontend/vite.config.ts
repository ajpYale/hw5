import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Port 5173 is the origin the API's CORS settings allow.
export default defineConfig({
  plugins: [react()],
  server: { port: 5173, strictPort: true },
});
