import { render, screen, within } from "@testing-library/react"
import { beforeAll, describe, expect, it, vi } from "vitest"

import type { TableChart, TableDisplay } from "@/features/copilot/types"
import { tableDisplay } from "@/test/fixtures"

const CHART_MODULE = "@/features/copilot/result-chart"

/** Stands in for the real chart, which needs a browser layout to draw; these tests only check it was asked for. */
function ChartStub({ chart }: { chart: TableChart }) {
  const series = chart.series.map((entry) => entry.label).join(" and ")
  return <div role="img" aria-label={`${chart.type} chart of ${series}`} />
}

/**
 * Loads the table afresh with the chart module given, then renders it.
 * React.lazy keeps the first chart module it loads for as long as the table's
 * module lives, so every test gets its own copy of the table's module.
 */
async function renderTable(
  table: TableDisplay,
  chartModule: () => object | Promise<object> = () => ({ ResultChart: ChartStub }),
) {
  vi.resetModules()
  vi.doMock(CHART_MODULE, chartModule)
  const { ResultTable } = await import("@/features/copilot/result-table")
  render(<ResultTable table={table} />)
}

function cellTexts(row: HTMLElement) {
  return within(row)
    .getAllByRole("cell")
    .map((cell) => cell.textContent)
}

describe("ResultTable", () => {
  // The first import compiles the table's whole module graph, which can take
  // seconds on a busy machine. Doing it once here keeps that time out of each
  // test's time limit; the fresh imports in the tests then reuse the compiled code.
  beforeAll(async () => {
    await import("@/features/copilot/result-table")
  })

  it("shows the title, the period and every row, each cell written by its column's format", async () => {
    const display = tableDisplay({ chart: null })
    await renderTable(display)

    const card = screen.getByRole("article", { name: "Loans by category" })
    expect(within(card).getByText(display.subtitle)).toBeInTheDocument()
    const table = within(card).getByRole("table", { name: "Loans by category" })
    expect(table).toHaveAccessibleDescription(display.subtitle)

    const [header, technology] = within(table).getAllByRole("row")
    expect(within(header).getAllByRole("columnheader").map((cell) => cell.textContent)).toEqual([
      "Category",
      "Loans",
      "Share",
      "Previous",
      "Previous share",
      "Change",
      "Change %",
    ])
    expect(within(technology).getByRole("rowheader")).toHaveTextContent("Technology")
    expect(cellTexts(technology)).toEqual(["1,234", "37.1%", "1,097", "28.9%", "137", "+12.5%"])
  })

  it("shows the previous period and the change beside each row, with a fall signed and a missing change as a dash", async () => {
    await renderTable(tableDisplay({ chart: null }))

    const [, , fiction, poetry] = screen.getAllByRole("row")
    expect(within(fiction).getByRole("rowheader")).toHaveTextContent("Fiction")
    expect(cellTexts(fiction)).toEqual(["980", "29.5%", "1,010", "26.6%", "-30", "-3.0%"])

    // Nothing was borrowed last quarter, so there is no relative change to show.
    const poetryCells = within(poetry).getAllByRole("cell")
    expect(poetryCells.at(-1)).toHaveTextContent("–")
    expect(within(poetryCells.at(-1) as HTMLElement).getByText("No value")).toBeInTheDocument()
  })

  it("ends with the total the server measured, leaving out the columns it has no total for", async () => {
    await renderTable(tableDisplay({ chart: null }))

    const total = screen.getAllByRole("row").at(-1) as HTMLElement
    expect(within(total).getByRole("rowheader")).toHaveTextContent("Total")
    expect(cellTexts(total)).toEqual(["3,325", "", "3,800", "", "-475", "-12.5%"])
  })

  it("has no total row when the server sends no total", async () => {
    await renderTable(tableDisplay({ chart: null, total: null }))

    expect(screen.getAllByRole("row")).toHaveLength(4)
    expect(screen.queryByText("Total")).not.toBeInTheDocument()
  })

  it("writes a rate's change in percentage points", async () => {
    await renderTable({
      kind: "table",
      title: "Late return rate by month",
      subtitle: "Last quarter, against the quarter before",
      columns: [
        { key: "label", label: "Month", format: "text" },
        { key: "value", label: "Late returns", format: "percent" },
        { key: "previous_value", label: "Previous", format: "percent" },
        { key: "change", label: "Change", format: "points" },
      ],
      rows: [
        { label: "Jul 2026", value: 12.4, previous_value: 4.2, change: 8.2 },
        { label: "Aug 2026", value: null, previous_value: 3, change: null },
      ],
      total: { value: 11.9, previous_value: 4, change: 7.9 },
      chart: null,
    })

    const [, july, august, total] = screen.getAllByRole("row")
    expect(cellTexts(july)).toEqual(["12.4%", "4.2%", "+8.2 pts"])
    expect(within(august).getByRole("rowheader")).toHaveTextContent("Aug 2026")
    expect(cellTexts(august)).toEqual(["–No value", "3.0%", "–No value"])
    expect(cellTexts(total)).toEqual(["11.9%", "4.0%", "+7.9 pts"])
  })

  it("shows a single figure as a one-row table", async () => {
    await renderTable({
      kind: "table",
      title: "Active loans",
      subtitle: "Now",
      columns: [{ key: "value", label: "Active loans", format: "count" }],
      rows: [{ value: 119 }],
      total: null,
      chart: null,
    })

    const [, row] = screen.getAllByRole("row")
    expect(cellTexts(row)).toEqual(["119"])
    expect(screen.queryByRole("rowheader")).not.toBeInTheDocument()
  })

  it("shows a forecast's measured months and forecast months, each with a dash where it has no value", async () => {
    await renderTable({
      kind: "table",
      title: "Loans forecast",
      subtitle: "36 months of history",
      columns: [
        { key: "label", label: "Month", format: "text" },
        { key: "actual", label: "Loans", format: "count" },
        { key: "forecast", label: "Forecast", format: "count" },
        { key: "low", label: "Low", format: "count" },
        { key: "high", label: "High", format: "count" },
      ],
      rows: [
        { label: "Sep 2026", actual: 1480 },
        { label: "Oct 2026", forecast: 1520, low: 1310, high: 1705 },
      ],
      total: null,
      chart: {
        type: "line",
        x: "label",
        series: [
          { key: "actual", label: "Loans" },
          { key: "forecast", label: "Forecast" },
        ],
        band: { low: "low", high: "high", label: "Likely range" },
      },
    })

    const [header, measured, forecast] = within(screen.getByRole("table", { name: "Loans forecast" })).getAllByRole("row")
    expect(within(header).getAllByRole("columnheader").map((cell) => cell.textContent)).toEqual([
      "Month",
      "Loans",
      "Forecast",
      "Low",
      "High",
    ])
    expect(cellTexts(measured)).toEqual(["1,480", "–No value", "–No value", "–No value"])
    expect(within(forecast).getByRole("rowheader")).toHaveTextContent("Oct 2026")
    expect(cellTexts(forecast)).toEqual(["–No value", "1,520", "1,310", "1,705"])
    expect(await screen.findByRole("img", { name: "line chart of Loans and Forecast" })).toBeInTheDocument()
  })

  it("draws the chart the server chose above the table", async () => {
    await renderTable(tableDisplay())

    const chart = await screen.findByRole("img", { name: "bar chart of This quarter and Previous quarter" })
    const table = screen.getByRole("table", { name: "Loans by category" })
    expect(chart.compareDocumentPosition(table) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
    expect(screen.queryByRole("status")).not.toBeInTheDocument()
  })

  it("neither loads nor holds a place for a chart when the server chose none", async () => {
    const chartModule = vi.fn(() => ({ ResultChart: ChartStub }))
    await renderTable(tableDisplay({ chart: null }), chartModule)

    expect(screen.getByRole("table", { name: "Loans by category" })).toBeInTheDocument()
    expect(screen.queryByRole("img")).not.toBeInTheDocument()
    expect(screen.queryByRole("status")).not.toBeInTheDocument()
    expect(chartModule).not.toHaveBeenCalled()
  })

  it("shows every figure while the chart is still loading", async () => {
    // A chart chunk that never arrives.
    await renderTable(tableDisplay(), () => new Promise<never>(() => {}))

    expect(screen.getByRole("status")).toHaveTextContent("Loading the chart")
    const [, technology] = screen.getAllByRole("row")
    expect(cellTexts(technology)).toEqual(["1,234", "37.1%", "1,097", "28.9%", "137", "+12.5%"])
    expect(screen.queryByRole("img")).not.toBeInTheDocument()
  })

  it("keeps the table and says so when the chart cannot load", async () => {
    const consoleError = vi.spyOn(console, "error").mockImplementation(() => {})
    await renderTable(tableDisplay(), () => {
      throw new Error("The chart chunk could not be fetched")
    })

    expect(await screen.findByText("The chart could not be shown. The table has every figure.")).toBeInTheDocument()
    expect(screen.getByRole("table", { name: "Loans by category" })).toBeInTheDocument()
    expect(screen.queryByRole("status")).not.toBeInTheDocument()
    expect(consoleError).toHaveBeenCalled()
  })
})
