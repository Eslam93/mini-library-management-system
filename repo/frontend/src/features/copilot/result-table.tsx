import { lazy, Suspense, useId } from "react"

import { ErrorBoundary } from "@/components/states/error-boundary"
import { Skeleton } from "@/components/ui/skeleton"
import { Table, TableBody, TableCaption, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import { formatTableValue, NO_VALUE } from "@/features/copilot/table-format"
import type { TableCell as TableCellValue, TableColumn, TableDisplay, TableRow as TableRowValues } from "@/features/copilot/types"
import { cn } from "@/lib/utils"

// The chart library is large and only some answers have a chart, so it loads
// in its own chunk the first time a table asks for one.
const ResultChart = lazy(() =>
  import("@/features/copilot/result-chart").then((module) => ({ default: module.ResultChart })),
)

/**
 * Figures the analyst measured: the title, the period, the chart the server
 * chose, and the table. The table renders at once and holds every figure, so
 * the numbers are readable before the chart arrives and if it never does.
 */
export function ResultTable({ table }: { table: TableDisplay }) {
  const titleId = useId()
  const subtitleId = useId()
  const [first] = table.columns
  // The first column names each row when it is text, such as a category or a month.
  const rowHeader = first?.format === "text" ? first : null

  return (
    <article aria-labelledby={titleId} className="space-y-3 overflow-hidden rounded-lg border bg-card pt-3 shadow-xs">
      <header className="px-3">
        <p id={titleId} className="text-sm font-medium">
          {table.title}
        </p>
        <p id={subtitleId} className="text-xs text-muted-foreground">
          {table.subtitle}
        </p>
      </header>

      {table.chart && (
        <ErrorBoundary fallback={() => <ChartFailed />}>
          <Suspense fallback={<ChartPlaceholder />}>
            <ResultChart chart={table.chart} columns={table.columns} rows={table.rows} />
          </Suspense>
        </ErrorBoundary>
      )}

      {/* The table scrolls sideways inside the card when its columns are wider than the panel. */}
      <Table aria-describedby={subtitleId} className="border-t">
        <TableCaption className="sr-only">{table.title}</TableCaption>
        <TableHeader>
          <TableRow className="hover:bg-transparent">
            {table.columns.map((column) => (
              <TableHead key={column.key} scope="col" className={cn(isNumeric(column) && "text-right")}>
                {column.label}
              </TableHead>
            ))}
          </TableRow>
        </TableHeader>
        <TableBody>
          {table.rows.length === 0 && (
            <TableRow>
              <TableCell colSpan={table.columns.length} className="py-2 text-muted-foreground">
                Nothing to show.
              </TableCell>
            </TableRow>
          )}
          {table.rows.map((row, index) => (
            <TableRow key={index}>
              {table.columns.map((column) => (
                <Cell key={column.key} column={column} value={row[column.key] ?? null} header={column === rowHeader} />
              ))}
            </TableRow>
          ))}
        </TableBody>
        {table.total && <TotalRow columns={table.columns} total={table.total} rowHeader={rowHeader} />}
      </Table>
    </article>
  )
}

type CellProps = {
  column: TableColumn
  value: TableCellValue
  /** The cell names its row, for screen readers moving across the table. */
  header?: boolean
}

function Cell({ column, value, header = false }: CellProps) {
  const numeric = isNumeric(column)
  const className = cn(
    "px-3 py-2",
    numeric ? "text-right whitespace-nowrap tabular-nums" : "min-w-32",
    header && "text-left font-medium",
  )
  const content =
    value === null ? (
      <>
        <span aria-hidden>{NO_VALUE}</span>
        <span className="sr-only">No value</span>
      </>
    ) : (
      formatTableValue(value, column.format)
    )

  if (header) {
    return (
      <th scope="row" className={className}>
        {content}
      </th>
    )
  }
  return <TableCell className={className}>{content}</TableCell>
}

type TotalRowProps = {
  columns: TableColumn[]
  total: TableRowValues
  rowHeader: TableColumn | null
}

/**
 * The total the server measured over the whole scope. A column the total
 * leaves out, such as a share, stays empty; the row header reads "Total".
 */
function TotalRow({ columns, total, rowHeader }: TotalRowProps) {
  return (
    <tfoot className="border-t bg-muted/50 font-medium">
      <TableRow className="hover:bg-transparent">
        {columns.map((column) => {
          if (column === rowHeader && total[column.key] === undefined) {
            return (
              <th key={column.key} scope="row" className="px-3 py-2 text-left font-medium">
                Total
              </th>
            )
          }
          if (total[column.key] === undefined) return <TableCell key={column.key} className="px-3 py-2" />
          return <Cell key={column.key} column={column} value={total[column.key]} header={column === rowHeader} />
        })}
      </TableRow>
    </tfoot>
  )
}

function isNumeric(column: TableColumn) {
  return column.format !== "text"
}

function ChartPlaceholder() {
  return (
    <div role="status" className="px-3">
      <span className="sr-only">Loading the chart</span>
      <Skeleton className="h-32 w-full" />
    </div>
  )
}

function ChartFailed() {
  return <p className="px-3 text-xs text-muted-foreground">The chart could not be shown. The table has every figure.</p>
}
