import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import { resolve } from "node:path";

// La KB doit s'ouvrir par double-clic (file://). Chrome y bloque les scripts
// `type="module"` et tout attribut `crossorigin` (origine "null") : on émet donc un bundle
// IIFE chargé en script classique, et on charge d'abord ./data.js (données embarquées,
// écrit par kb/builder.py) à la place du fetch de data.json.
function fileProtocolCompatible() {
  return {
    name: "hexa-kb-file-protocol",
    apply: "build",
    transformIndexHtml(html) {
      return html
        .replace(/<script type="module" crossorigin/g, '<script defer src="./data.js"></script>\n    <script defer')
        .replace(/ crossorigin(?=[\s>])/g, "");
    },
  };
}

export default defineConfig({
  base: "./",
  plugins: [react(), fileProtocolCompatible()],
  build: {
    outDir: "knowledge_base",
    emptyOutDir: false,
    modulePreload: false,
    rollupOptions: {
      output: { format: "iife" },
    },
  },
  publicDir: false,
  resolve: {
    alias: {
      "@": resolve(__dirname, "src"),
    },
  },
});
