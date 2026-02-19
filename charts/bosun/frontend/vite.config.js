import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Mermaid → langium has many transitive deps (vscode-*, @chevrotain/*)
// that aren't available in Bazel's sandbox because pnpm strict mode
// doesn't hoist them into langium's node_modules scope.
// This plugin catches any unresolvable import and provides an empty stub,
// preventing the build from failing on these Node.js-only/unused modules.
function stubUnresolvable() {
  return {
    name: "stub-unresolvable",
    enforce: "pre",
    async resolveId(source, importer, options) {
      if (source.startsWith("\0") || !importer) return null;
      // Only stub imports from inside langium/chevrotain packages
      if (
        !importer.includes("/langium/") &&
        !importer.includes("/@chevrotain/") &&
        !importer.includes("/chevrotain/") &&
        !importer.includes("/vscode-")
      )
        return null;
      const resolution = await this.resolve(source, importer, {
        ...options,
        skipSelf: true,
      });
      if (resolution) return resolution;
      return { id: "\0stub:" + source, syntheticNamedExports: true };
    },
    load(id) {
      if (id.startsWith("\0stub:")) {
        // Return a Proxy as the default export so any named import (via
        // syntheticNamedExports) resolves to a callable no-op at runtime.
        // This prevents both Rollup binding errors AND runtime crashes.
        return {
          code: [
            "const handler = { get: (_, p) => typeof p === 'symbol' ? undefined : function(){} };",
            "export default new Proxy({}, handler);",
          ].join("\n"),
          syntheticNamedExports: true,
        };
      }
    },
  };
}

export default defineConfig({
  plugins: [stubUnresolvable(), react()],
  server: {
    proxy: {
      "/ws": {
        target: "ws://localhost:8420",
        ws: true,
      },
      "/api": {
        target: "http://localhost:8420",
      },
    },
  },
  build: {
    outDir: "dist",
  },
});
