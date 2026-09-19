import { describe, expect, it } from "vitest"

import { formatAxisValue, formatTableValue, NO_VALUE } from "@/features/copilot/table-format"
import type { TableColumnFormat } from "@/features/copilot/types"

const FORMATS: TableColumnFormat[] = ["text", "count", "percent", "points", "change_percent", "days"]

describe("formatTableValue", () => {
  it("writes counts with thousands separators", () => {
    expect(formatTableValue(1234, "count")).toBe("1,234")
    expect(formatTableValue(0, "count")).toBe("0")
    expect(formatTableValue(-30, "count")).toBe("-30")
  })

  it("writes a percentage with one decimal", () => {
    expect(formatTableValue(37.1, "percent")).toBe("37.1%")
    expect(formatTableValue(37, "percent")).toBe("37.0%")
  })

  it("writes a change in percentage points with its sign", () => {
    expect(formatTableValue(8.2, "points")).toBe("+8.2 pts")
    expect(formatTableValue(-1.5, "points")).toBe("-1.5 pts")
    expect(formatTableValue(0, "points")).toBe("0.0 pts")
  })

  it("writes a relative change with its sign", () => {
    expect(formatTableValue(12.5, "change_percent")).toBe("+12.5%")
    expect(formatTableValue(-3, "change_percent")).toBe("-3.0%")
    expect(formatTableValue(0, "change_percent")).toBe("0.0%")
  })

  it("writes days with one decimal", () => {
    expect(formatTableValue(12.3, "days")).toBe("12.3 days")
    expect(formatTableValue(14, "days")).toBe("14.0 days")
  })

  it("keeps text as the server sent it, so a year gets no thousands separator", () => {
    expect(formatTableValue("Technology", "text")).toBe("Technology")
    expect(formatTableValue(2026, "text")).toBe("2026")
  })

  it("shows a dash for a missing value in every format", () => {
    for (const format of FORMATS) {
      expect(formatTableValue(null, format)).toBe(NO_VALUE)
    }
    expect(NO_VALUE).toBe("–")
  })
})

describe("formatAxisValue", () => {
  it("drops the trailing decimal and keeps the percent sign", () => {
    expect(formatAxisValue(1500, "count")).toBe("1,500")
    expect(formatAxisValue(20, "percent")).toBe("20%")
    expect(formatAxisValue(12.5, "days")).toBe("12.5")
  })
})
