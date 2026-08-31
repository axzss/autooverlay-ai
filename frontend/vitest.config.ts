import { defineConfig } from 'vitest/config'
import { resolve } from 'node:path'

// Pure-logic suite: node environment (no DOM needed, and it is faster).
// '@' must resolve to ./app to match tsconfig.json paths, because source
// files under app/ and lib/ import via '@/...'.
export default defineConfig({
  resolve: {
    alias: {
      '@': resolve(__dirname, './app'),
    },
  },
  test: {
    environment: 'node',
    include: ['tests/**/*.test.ts'],
    reporters: ['default'],
  },
})
