import {
  Area,
  Bar,
  BarChart,
  CartesianGrid,
  ComposedChart,
  Line,
  Tooltip,
  XAxis,
  YAxis,
  type YAxisTickContentProps,
} from "recharts"

import { formatAxisValue, formatTableValue } from "@/features/copilot/table-format"
import type {
  TableCell,
  TableChart,
  TableChartBand,
  TableColumn,
  TableColumnFormat,
  TableRow,
} from "@/features/copilot/types"

// The current period in the accent colour; the previous period in a quieter
// step of the same hue, so the comparison reads as context. Both are theme
// tokens, so light and dark each get their own step.
const SERIES_COLORS = ["var(--chart-current)", "var(--chart-previous)"]
const FALLBACK_COLOR = "var(--muted-foreground)"
// A range is a light wash of the accent, so the lines stay the first thing read.
const BAND_COLOR = "var(--chart-range)"
// A dashed line is the usual sign for values that were projected, not measured.
const PROJECTION_DASH = "6 4"

const TICK = { fill: "var(--muted-foreground)", fontSize: 12 }
const GRID = "var(--border)"
const TOOLTIP_BOX = {
  background: "var(--popover)",
  border: "1px solid var(--border)",
  borderRadius: "calc(var(--radius) - 2px)",
  fontSize: 12,
}
// Tooltip text wears the text colour, not the series colour, so it stays readable.
const TOOLTIP_TEXT = { color: "var(--popover-foreground)" }

// Bars run sideways because the panel is narrow: each category name sits on one line beside its bars.
const CATEGORY_AXIS_WIDTH = 112
const CATEGORY_LABEL_LENGTH = 16
const BAR_THICKNESS = 12
const LINE_HEIGHT = 200
const AXIS_HEIGHT = 28

type ResultChartProps = {
  chart: TableChart
  columns: TableColumn[]
  rows: TableRow[]
}

type ChartSeries = {
  key: string
  label: string
  color: string
  /** A projection, drawn dashed. */
  dashed: boolean
}

/**
 * The chart the server chose for a table: horizontal bars for categories, a
 * line for a time series, one set of bars or one line per series. A line
 * chart with a band shades the range under the lines and dashes the
 * projected line. The table beside it holds every figure, so the chart is an
 * image to screen readers.
 */
export function ResultChart({ chart, columns, rows }: ResultChartProps) {
  const formats = new Map(columns.map((column) => [column.key, column.format]))
  const formatOf = (key: string): TableColumnFormat => formats.get(key) ?? "count"
  const axisFormat = formatOf(chart.series[0]?.key ?? "")
  const xLabel = columns.find((column) => column.key === chart.x)?.label ?? chart.x
  const band = chart.type === "line" ? (chart.band ?? null) : null
  const series: ChartSeries[] = chart.series.map((entry, index) => ({
    ...entry,
    // With a band every line is the same measure, so the projection keeps the
    // measured line's colour and only its dashes set it apart.
    color: band ? SERIES_COLORS[0] : (SERIES_COLORS[index] ?? FALLBACK_COLOR),
    dashed: band !== null && index > 0,
  }))
  const kind = chart.type === "line" ? "Line chart" : "Bar chart"
  const plotted = `${kind} of ${series.map((entry) => entry.label).join(" and ")} by ${xLabel}`
  const label = band ? `${plotted}, and ${band.label} as a shaded band` : plotted

  const tooltip = (
    <Tooltip
      contentStyle={TOOLTIP_BOX}
      labelStyle={{ ...TOOLTIP_TEXT, fontWeight: 500 }}
      itemStyle={TOOLTIP_TEXT}
      cursor={chart.type === "line" ? { stroke: GRID } : { fill: "var(--muted)" }}
      separator=": "
      // The series in the server's order, current first, then the band; the library would sort them by name.
      itemSorter={(item) =>
        typeof item.dataKey === "string"
          ? series.findIndex((entry) => entry.key === item.dataKey)
          : series.length
      }
      formatter={(value, _name, item) =>
        // The band's value is its [low, high] pair.
        Array.isArray(value) && band
          ? `${formatTableValue(toCell(value[0]), formatOf(band.low))} to ${formatTableValue(toCell(value[1]), formatOf(band.high))}`
          : formatTableValue(toCell(value), formatOf(String(item.dataKey)))
      }
    />
  )

  return (
    <div role="img" aria-label={label} className="space-y-2 px-3">
      {(series.length > 1 || band) && <Legend series={series} band={band} line={chart.type === "line"} />}
      {chart.type === "line" ? (
        <ComposedChart
          data={rows}
          responsive
          accessibilityLayer={false}
          style={{ width: "100%", height: LINE_HEIGHT }}
          margin={{ top: 8, right: 12, bottom: 0, left: 0 }}
        >
          <CartesianGrid stroke={GRID} vertical={false} />
          <XAxis dataKey={chart.x} tick={TICK} tickLine={false} axisLine={{ stroke: GRID }} minTickGap={12} />
          <YAxis
            tick={TICK}
            tickLine={false}
            axisLine={false}
            width={44}
            tickFormatter={(value: number) => formatAxisValue(value, axisFormat)}
          />
          {tooltip}
          {/* Drawn before the lines, so it sits under them. */}
          {band && (
            <Area
              dataKey={(row: TableRow) => bandRange(row, band)}
              name={band.label}
              type="linear"
              stroke="none"
              fill={BAND_COLOR}
              fillOpacity={1}
              activeDot={false}
            />
          )}
          {series.map((entry) => (
            <Line
              key={entry.key}
              dataKey={entry.key}
              name={entry.label}
              type="linear"
              stroke={entry.color}
              strokeWidth={2}
              strokeDasharray={entry.dashed ? PROJECTION_DASH : undefined}
              dot={{ r: 3, fill: entry.color, stroke: "var(--card)", strokeWidth: 2 }}
              activeDot={{ r: 5, stroke: "var(--card)", strokeWidth: 2 }}
            />
          ))}
        </ComposedChart>
      ) : (
        <BarChart
          data={rows}
          layout="vertical"
          responsive
          accessibilityLayer={false}
          style={{ width: "100%", height: barChartHeight(rows.length, series.length) }}
          margin={{ top: 0, right: 12, bottom: 0, left: 0 }}
          barGap={2}
        >
          <CartesianGrid stroke={GRID} horizontal={false} />
          <XAxis
            type="number"
            tick={TICK}
            tickLine={false}
            axisLine={{ stroke: GRID }}
            height={AXIS_HEIGHT}
            tickFormatter={(value: number) => formatAxisValue(value, axisFormat)}
          />
          <YAxis
            type="category"
            dataKey={chart.x}
            tick={CategoryTick}
            // Every bar keeps its name; the library would otherwise drop names it measures as crowded.
            interval={0}
            tickLine={false}
            axisLine={false}
            width={CATEGORY_AXIS_WIDTH}
          />
          {tooltip}
          {series.map((entry) => (
            <Bar
              key={entry.key}
              dataKey={entry.key}
              name={entry.label}
              fill={entry.color}
              barSize={BAR_THICKNESS}
              // Rounded at the end that shows the value, square at the baseline.
              radius={[0, 4, 4, 0]}
            />
          ))}
        </BarChart>
      )}
    </div>
  )
}

type LegendProps = {
  series: ChartSeries[]
  band: TableChartBand | null
  line: boolean
}

function Legend({ series, band, line }: LegendProps) {
  return (
    <ul className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted-foreground">
      {series.map((entry) => (
        <li key={entry.key} className="flex items-center gap-1.5">
          {entry.dashed ? (
            <span data-swatch="dashed" className="w-3.5 border-t-2 border-dashed" style={{ borderColor: entry.color }} />
          ) : (
            <span
              data-swatch="solid"
              className={line ? "h-0.5 w-3.5 rounded-full" : "size-2.5 rounded-sm"}
              style={{ background: entry.color }}
            />
          )}
          {entry.label}
        </li>
      ))}
      {band && (
        <li className="flex items-center gap-1.5">
          <span data-swatch="band" className="size-2.5 rounded-sm" style={{ background: BAND_COLOR }} />
          {band.label}
        </li>
      )}
    </ul>
  )
}

/**
 * A row's range as the [low, high] pair the chart library draws a band from.
 * A row without both ends, such as a measured month, leaves a gap.
 */
function bandRange(row: TableRow, band: TableChartBand): [number, number] | null {
  const low = row[band.low]
  const high = row[band.high]
  return typeof low === "number" && typeof high === "number" ? [low, high] : null
}

/** Room for every bar plus the number axis; each category gets a band as tall as its bars and a gap. */
function barChartHeight(rowCount: number, seriesCount: number) {
  const band = seriesCount * (BAR_THICKNESS + 2) + 14
  return rowCount * band + AXIS_HEIGHT
}

/**
 * A category name on one line. The chart library would wrap a long name over
 * two lines into the next bar, so a long name, such as a book title, is cut
 * instead; hovering shows it whole, and the table has it in full.
 */
function CategoryTick({ x, y, payload }: YAxisTickContentProps) {
  const name = String(payload.value)
  const short =
    name.length > CATEGORY_LABEL_LENGTH ? `${name.slice(0, CATEGORY_LABEL_LENGTH - 1).trimEnd()}…` : name
  return (
    <text x={x} y={y} dy="0.35em" textAnchor="end" fill={TICK.fill} fontSize={TICK.fontSize}>
      <title>{name}</title>
      {short}
    </text>
  )
}

function toCell(value: unknown): TableCell {
  return typeof value === "number" || typeof value === "string" ? value : null
}
