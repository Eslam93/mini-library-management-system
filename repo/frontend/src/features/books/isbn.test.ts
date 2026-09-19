import { describe, expect, it } from "vitest"

import { hasIsbnShape, hasValidIsbnChecksum, normalizeIsbn } from "@/features/books/isbn"

describe("ISBN rules", () => {
  it("drops spaces and hyphens and upper-cases a final x", () => {
    expect(normalizeIsbn(" 978-0-441 17271-9 ")).toBe("9780441172719")
    expect(normalizeIsbn("0-8044-2957-x")).toBe("080442957X")
  })

  it.each(["0441172717", "080442957X", "9780441172719", "9780140449136"])(
    "accepts the valid ISBN %s",
    (isbn) => {
      expect(hasIsbnShape(isbn)).toBe(true)
      expect(hasValidIsbnChecksum(isbn)).toBe(true)
    },
  )

  it.each(["0441172718", "9780441172718"])("rejects the check digit of %s", (isbn) => {
    expect(hasIsbnShape(isbn)).toBe(true)
    expect(hasValidIsbnChecksum(isbn)).toBe(false)
  })

  it.each(["12345", "97804411727190", "X441172717", "978044117271X"])(
    "rejects the shape of %s",
    (isbn) => {
      expect(hasIsbnShape(isbn)).toBe(false)
    },
  )
})
