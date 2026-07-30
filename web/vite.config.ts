import { defineConfig } from 'vite';
import { copyFileSync } from 'node:fs';

// Artifacts are generated at the repo root by pipeline.export.build_artifacts and served as static
// files. Pointing publicDir at them keeps a single copy: the site reads exactly what the pipeline
// wrote, with no build step in between that could quietly reshape a number.
export default defineConfig({
  publicDir: '../artifacts',
  build: { outDir: 'dist', emptyOutDir: true },
  plugins: [
    {
      name: 'copy-brand-assets',
      closeBundle() {
        copyFileSync(
          new URL('./public/social-card.png', import.meta.url),
          new URL('./dist/social-card.png', import.meta.url),
        );
      },
    },
  ],
});
