import { defineConfig, mergeConfig } from "vitest/config"

import viteConfig from "./vite.config.ts"

export default mergeConfig(
  viteConfig,
  defineConfig({
    test: {
      environment: "jsdom",
      setupFiles: ["./src/test/setup.ts"],
      restoreMocks: true,
      unstubGlobals: true,
      // Each worker builds its own jsdom, which costs enough memory that a machine
      // with many cores runs out of it and a worker dies with exit code 134, failing
      // the run although every test passed. Four workers keep the suite under a
      // minute and stable; see 99-pending.md.
      maxWorkers: 4,
    },
  }),
)
