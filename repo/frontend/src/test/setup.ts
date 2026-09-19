import "@testing-library/jest-dom/vitest"
import { cleanup } from "@testing-library/react"
import { afterEach } from "vitest"

// Tests import from vitest directly (no globals), so unmount after each test here.
afterEach(() => {
  cleanup()
})
