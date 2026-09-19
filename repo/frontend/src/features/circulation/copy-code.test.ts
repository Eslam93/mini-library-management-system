import { describe, expect, it } from "vitest"

import { normalizeCopyCode } from "@/features/circulation/copy-code"

describe("normalizeCopyCode", () => {
  it.each([
    ["CP-0012", "CP-0012"],
    ["cp-12", "CP-0012"],
    ["12", "CP-0012"],
    ["  cp 0012 ", "CP-0012"],
    ["CP12", "CP-0012"],
    ["0007", "CP-0007"],
    ["cp-12345", "CP-12345"],
  ])("reads %j as %s", (typed, code) => {
    expect(normalizeCopyCode(typed)).toBe(code)
  })

  it.each(["", "dune", "CP-", "BK-0012", "12a"])("rejects %j", (typed) => {
    expect(normalizeCopyCode(typed)).toBeNull()
  })
})
