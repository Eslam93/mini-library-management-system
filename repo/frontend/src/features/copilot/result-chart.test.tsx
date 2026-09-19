import { render, screen, within } from "@testing-library/react"
import { describe, expect, it, vi } from "vitest"

import { ResultChart } from "@/features/copilot/result-chart"
import type { TableChart, TableColumn, TableRow } from "@/features/copilot/types"
import { tableDisplay } from "@/test/fixtures"

// jsdom has no layout, so the chart library draws no bars or lines here
// unless a test gives the chart a size. Most tests check what the panel adds
// around the drawing: the name screen readers hear and the legend.

const monthColumns: TableColumn[] = [
  { key: "label", label: "Month", format: "text" },
  { key: "value", label: "Loans", format: "count" },
]
const monthRows = [
  { label: "Jul 2026", value: 180 },
  { label: "Aug 2026", value: 150 },
  { label: "Sep 2026", value: 95 },
]

// A forecast as the analyst sends it: measured months, then forecast months with their likely range.
const forecastColumns: TableColumn[] = [
  { key: "label", label: "Month", format: "text" },
  { key: "actual", label: "Loans", format: "count" },
  { key: "forecast", label: "Forecast", format: "count" },
  { key: "low", label: "Low", format: "count" },
  { key: "high", label: "High", format: "count" },
]
const forecastRows: TableRow[] = [
  { label: "Jul 2026", actual: 180 },
  { label: "Aug 2026", actual: 150 },
  { label: "Sep 2026", actual: 160 },
  { label: "Oct 2026", forecast: 170, low: 140, high: 200 },
  { label: "Nov 2026", forecast: 175, low: 138, high: 210 },
]
const forecastChart: TableChart = {
  type: "line",
  x: "label",
  series: [
    { key: "actual", label: "Loans" },
    { key: "forecast", label: "Forecast" },
  ],
  band: { low: "low", high: "high", label: "Likely range" },
}

/**
 * Gives every chart a 400 by 200 pixel box, and asks for reduced motion so
 * the lines are drawn at once, in their final dashes, instead of animating in.
 */
function giveChartsASize() {
  vi.stubGlobal(
    "ResizeObserver",
    class {
      observe() {}
      unobserve() {}
      disconnect() {}
    },
  )
  vi.stubGlobal("matchMedia", (query: string) => ({
    matches: query.includes("prefers-reduced-motion: reduce"),
    media: query,
    addEventListener() {},
    removeEventListener() {},
    addListener() {},
    removeListener() {},
  }))
  vi.spyOn(HTMLElement.prototype, "getBoundingClientRect").mockReturnValue(
    DOMRect.fromRect({ width: 400, height: 200 }),
  )
}

describe("ResultChart", () => {
  it("names a bar chart by what it plots and keys both series in a legend", () => {
    const { chart, columns, rows } = tableDisplay()
    render(<ResultChart chart={chart as TableChart} columns={columns} rows={rows} />)

    const figure = screen.getByRole("img", { name: "Bar chart of This quarter and Previous quarter by Category" })
    expect(within(figure).getAllByRole("listitem").map((item) => item.textContent)).toEqual([
      "This quarter",
      "Previous quarter",
    ])
  })

  it("names a line chart for a time series, with no legend for its one series", () => {
    const chart: TableChart = { type: "line", x: "label", series: [{ key: "value", label: "Loans" }] }
    render(<ResultChart chart={chart} columns={monthColumns} rows={monthRows} />)

    const figure = screen.getByRole("img", { name: "Line chart of Loans by Month" })
    expect(within(figure).queryByRole("list")).not.toBeInTheDocument()
  })

  it("names a forecast with its range and keys the measured line, the dashed forecast and the range", () => {
    render(<ResultChart chart={forecastChart} columns={forecastColumns} rows={forecastRows} />)

    const figure = screen.getByRole("img", {
      name: "Line chart of Loans and Forecast by Month, and Likely range as a shaded band",
    })
    const keys = within(figure).getAllByRole("listitem")
    expect(keys.map((item) => item.textContent)).toEqual(["Loans", "Forecast", "Likely range"])
    expect(keys.map((item) => item.querySelector("[data-swatch]")?.getAttribute("data-swatch"))).toEqual([
      "solid",
      "dashed",
      "band",
    ])
  })

  it("draws the range under the lines, with the measured line solid and the forecast dashed", () => {
    giveChartsASize()
    const { container } = render(
      <ResultChart chart={forecastChart} columns={forecastColumns} rows={forecastRows} />,
    )

    const band = container.querySelectorAll(".recharts-area-area")
    expect(band).toHaveLength(1)
    expect(band[0]).toHaveAttribute("fill", "var(--chart-range)")
    const [measured, forecast] = container.querySelectorAll(".recharts-line-curve")
    expect(measured).not.toHaveAttribute("stroke-dasharray")
    expect(forecast).toHaveAttribute("stroke-dasharray", "6 4")
    expect(forecast).toHaveAttribute("stroke", measured.getAttribute("stroke"))
    // Earlier in the drawing means underneath.
    expect(band[0].compareDocumentPosition(measured) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
  })

  it("draws a comparison without a band as two solid lines in their own colours", () => {
    giveChartsASize()
    const chart: TableChart = {
      type: "line",
      x: "label",
      series: [
        { key: "value", label: "This year" },
        { key: "previous_value", label: "Last year" },
      ],
    }
    const rows = monthRows.map((row) => ({ ...row, previous_value: row.value - 20 }))
    const { container } = render(<ResultChart chart={chart} columns={monthColumns} rows={rows} />)

    expect(container.querySelector(".recharts-area-area")).toBeNull()
    const lines = [...container.querySelectorAll(".recharts-line-curve")]
    expect(lines.map((line) => line.getAttribute("stroke"))).toEqual([
      "var(--chart-current)",
      "var(--chart-previous)",
    ])
    expect(lines.filter((line) => line.hasAttribute("stroke-dasharray"))).toEqual([])
  })
})
