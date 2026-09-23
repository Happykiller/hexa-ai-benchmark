import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import { resolve } from "node:path";

// La KB doit s'ouvrir par double-clic (file://). Chrome y bloque les scripts
// `type="module"` et tout attribut `crossorigin` (origine "null") : on émet donc un bundle
// IIFE chargé en script classique, et on charge d'abord ./data.js (données embarquées,
// écrit par le magasin KB, hexa/core/kb/store.py) à la place du fetch de data.json.
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

// Un seul front pour toutes les KB : HEXA_SITE choisit le site (sites/<site>/).
// En dev, le dossier du site est servi à la racine (données, médias) ; au build, le bundle y
// est écrit à côté de data.json.
const SITES = ["todo", "blender"];
const site = process.env.HEXA_SITE || "todo";
if (!SITES.includes(site)) throw new Error(`HEXA_SITE inconnu : ${site} (attendu : ${SITES.join(", ")})`);
const siteDir = resolve(__dirname, "..", "sites", site);

export default defineConfig(({ command }) => ({
  root: __dirname,
  base: "./",
  plugins: [react(), fileProtocolCompatible()],
  define: { "import.meta.env.VITE_KB_VARIANT": JSON.stringify(site) },
  publicDir: command === "serve" ? siteDir : false,
  build: {
    outDir: siteDir,
    emptyOutDir: false,
    modulePreload: false,
    rollupOptions: {
      output: { format: "iife" },
    },
  },
  resolve: {
    alias: {
      "@": resolve(__dirname, "src"),
    },
  },
}));
