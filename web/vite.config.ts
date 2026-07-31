import { defineConfig } from 'vite';
import { cpSync } from 'node:fs';

// Artifacts are generated at the repo root by pipeline.export.build_artifacts and served as static
// files. Pointing publicDir at them keeps a single copy: the site reads exactly what the pipeline
// wrote, with no build step in between that could quietly reshape a number.
export default defineConfig({
  publicDir: '../artifacts',
  build: { outDir: 'dist', emptyOutDir: true },
  plugins: [
    {
      name: 'copy-site-files',
      transformIndexHtml() {
        const tags = [];
        const googleVerification = process.env.GOOGLE_SITE_VERIFICATION?.trim();
        const bingVerification = process.env.BING_SITE_VERIFICATION?.trim();

        if (googleVerification) {
          tags.push({
            tag: 'meta',
            attrs: { name: 'google-site-verification', content: googleVerification },
            injectTo: 'head' as const,
          });
        }
        if (bingVerification) {
          tags.push({
            tag: 'meta',
            attrs: { name: 'msvalidate.01', content: bingVerification },
            injectTo: 'head' as const,
          });
        }

        return tags;
      },
      closeBundle() {
        cpSync(new URL('./public/', import.meta.url), new URL('./dist/', import.meta.url), {
          recursive: true,
          force: true,
        });
      },
    },
  ],
});
