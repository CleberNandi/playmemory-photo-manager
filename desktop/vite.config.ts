import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig(({ command }) => {
  const connectSource = command === "serve"
    ? "'self' ws://127.0.0.1:5173"
    : "'none'";
  const csp = `default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src ${connectSource}; object-src 'none'; base-uri 'none'; form-action 'none'`;
  return {
    plugins: [
      react(),
      { name: "desktop-csp", transformIndexHtml: (html) => html.replace("%PLAYMEMORIES_CSP%", csp) },
    ],
    base: "./",
    build: { outDir: "dist/renderer", emptyOutDir: false },
    server: { host: "127.0.0.1", port: 5173, strictPort: true },
  };
});
