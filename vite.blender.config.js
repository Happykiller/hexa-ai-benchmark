import { defineConfig, mergeConfig } from "vite";
import baseConfig from "./vite.config.js";

// Site de la KB du benchmark Blender : même code (src/), autre dossier de sortie.
// La variante est lue par src/App.jsx via import.meta.env.VITE_KB_VARIANT.
export default mergeConfig(
  baseConfig,
  defineConfig({
    define: { "import.meta.env.VITE_KB_VARIANT": JSON.stringify("blender") },
    build: { outDir: "knowledge_base_blender" },
  }),
);
