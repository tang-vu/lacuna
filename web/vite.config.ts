import { defineConfig } from 'vite';

// Artifacts are generated at the repo root by pipeline.export.build_artifacts and served as static
// files. Pointing publicDir at them keeps a single copy: the site reads exactly what the pipeline
// wrote, with no build step in between that could quietly reshape a number.
export default defineConfig({
  publicDir: '../artifacts',
  build: { outDir: 'dist', emptyOutDir: true },
});
