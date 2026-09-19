import { screen, within } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

import { ResultDisplay } from "@/features/copilot/result-display"
import type { CopilotDisplay, CopilotFace } from "@/features/copilot/types"
import { formatDueDate } from "@/lib/format"
import { bookDetail, borrowedCopy, copyLookup, copyOnLoan, loan, member, tableDisplay } from "@/test/fixtures"
import { renderWithProviders } from "@/test/render"

function renderDisplay(display: CopilotDisplay, face: CopilotFace = "staff") {
  const onNavigate = vi.fn()
  renderWithProviders(
    <ResultDisplay display={display} face={face} onNavigate={onNavigate} onAsk={vi.fn()} busy={false} />,
  )
  return { onNavigate }
}

const overdueLoan = loan({
  member: { id: "member-2", full_name: "Omar Nasser" },
  due_at: "2026-09-15T23:59:59Z",
  is_overdue: true,
  days_overdue: 4,
})

describe("ResultDisplay", () => {
  beforeEach(() => {
    vi.useFakeTimers({ toFake: ["Date"] })
    vi.setSystemTime(new Date("2026-09-19T12:00:00Z"))
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it("shows members with their email and active loans, each linking to the member's page", async () => {
    const { onNavigate } = renderDisplay({
      kind: "members",
      items: [
        member({ active_loans: 2 }),
        member({ id: "member-3", full_name: "Maya Haddad", email: null, active_loans: 0 }),
      ],
    })

    const [hassan, haddad] = within(screen.getByRole("list", { name: "2 members" })).getAllByRole("listitem")
    expect(within(hassan).getByRole("link", { name: "Maya Hassan" })).toHaveAttribute("href", "/members/member-1")
    expect(within(hassan).getByText("maya@example.com")).toBeInTheDocument()
    expect(within(hassan).getByText("2 active loans")).toBeInTheDocument()
    expect(within(haddad).getByText("No active loans")).toBeInTheDocument()

    await userEvent.setup().click(within(haddad).getByRole("link", { name: "Maya Haddad" }))
    expect(onNavigate).toHaveBeenCalledTimes(1)
    expect(screen.getByTestId("location")).toHaveTextContent("/members/member-3")
  })

  it("shows a copy on loan with its book, its borrower and how overdue it is", () => {
    renderDisplay({ kind: "copy", lookup: copyLookup({ active_loan: overdueLoan }) })

    const copy = screen.getByRole("article", { name: "Copy CP-0001" })
    expect(within(copy).getByText("4 days overdue")).toBeInTheDocument()
    expect(within(copy).getByRole("link", { name: "Dune" })).toHaveAttribute("href", "/books/book-1")
    expect(within(copy).getByRole("link", { name: "Omar Nasser" })).toHaveAttribute("href", "/members/member-2")
    expect(within(copy).getByText(`· Due ${formatDueDate("2026-09-15T23:59:59Z")}`)).toBeInTheDocument()
  })

  it("shows a copy on the shelf as available, with nobody holding it", () => {
    renderDisplay({ kind: "copy", lookup: copyLookup() })

    const copy = screen.getByRole("article", { name: "Copy CP-0001" })
    expect(within(copy).getByText("Available")).toBeInTheDocument()
    expect(within(copy).queryByText(/Borrowed by/)).not.toBeInTheDocument()
  })

  it("names who has each borrowed copy of a book for staff, linking to the member's page", () => {
    renderDisplay({ kind: "book", book: bookDetail({ copies: [borrowedCopy("copy-1", "CP-0001")] }) })

    const [copy] = within(screen.getByRole("list", { name: "Copies" })).getAllByRole("listitem")
    expect(within(copy).getByRole("link", { name: "Lina Farah" })).toHaveAttribute("href", "/members/member-9")
  })

  it("shows a member only when a borrowed copy is due back", () => {
    const dueAt = "2026-09-25T23:59:59Z"
    renderDisplay({ kind: "book", book: bookDetail({ copies: [copyOnLoan("copy-1", "CP-0001", dueAt)] }) }, "member")

    const [copy] = within(screen.getByRole("list", { name: "Copies" })).getAllByRole("listitem")
    expect(within(copy).getByText(`Due back ${formatDueDate(dueAt)}`)).toBeInTheDocument()
    expect(within(copy).queryByRole("link")).not.toBeInTheDocument()
  })

  it("names the member of each loan for staff, linking to the member's page", () => {
    renderDisplay({ kind: "loans", items: [overdueLoan] }, "staff")

    const staffRow = within(screen.getByRole("list", { name: "1 loan" })).getByRole("listitem")
    expect(within(staffRow).getByRole("link", { name: "Omar Nasser" })).toHaveAttribute("href", "/members/member-2")
    expect(within(staffRow).getByText("Overdue")).toBeInTheDocument()
  })

  it("shows the analyst's figures as a table with its total", () => {
    renderDisplay(tableDisplay({ chart: null }))

    const table = screen.getByRole("table", { name: "Loans by category" })
    const rows = within(table).getAllByRole("row")
    expect(within(rows[1]).getByRole("rowheader")).toHaveTextContent("Technology")
    expect(within(rows[1]).getAllByRole("cell")[0]).toHaveTextContent("1,234")
    expect(within(rows.at(-1) as HTMLElement).getByRole("rowheader")).toHaveTextContent("Total")
  })

  it("leaves the member's own name out of their loan rows", () => {
    renderDisplay({ kind: "loans", items: [overdueLoan] }, "member")

    const memberRow = within(screen.getByRole("list", { name: "1 loan" })).getByRole("listitem")
    expect(within(memberRow).getByRole("link", { name: "Dune" })).toBeInTheDocument()
    expect(within(memberRow).queryByText("Omar Nasser")).not.toBeInTheDocument()
  })
})
