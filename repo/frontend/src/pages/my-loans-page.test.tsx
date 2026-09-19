import { screen, within } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { Route, Routes } from "react-router"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

import { formatDate, formatDueDate } from "@/lib/format"
import { HistoryPage } from "@/pages/history-page"
import { MyLoansPage } from "@/pages/my-loans-page"
import { requestsTo, stubApi } from "@/test/api-stub"
import { loan, memberUser, page } from "@/test/fixtures"
import { renderWithProviders } from "@/test/render"

function renderPage(path: "/my-loans" | "/history") {
  return renderWithProviders(
    <Routes>
      <Route path="/my-loans" element={<MyLoansPage />} />
      <Route path="/history" element={<HistoryPage />} />
    </Routes>,
    { route: path, user: memberUser() },
  )
}

function rowOf(title: string) {
  return screen.getByRole("link", { name: title }).closest("tr") as HTMLElement
}

describe("MyLoansPage", () => {
  beforeEach(() => {
    // Midday UTC keeps "today" the same calendar date in every time zone.
    vi.useFakeTimers({ toFake: ["Date"] })
    vi.setSystemTime(new Date("2026-09-19T12:00:00Z"))
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it("shows each active loan with its due date, overdue or how many days are left", async () => {
    const fetchMock = stubApi({
      "GET /api/me/loans": () =>
        page([
          loan({
            id: "loan-1",
            book: { id: "book-1", title: "Dune", author: "Frank Herbert" },
            due_at: "2026-09-15T23:59:59Z",
            is_overdue: true,
          }),
          loan({
            id: "loan-2",
            copy: { id: "copy-2", code: "CP-0002" },
            book: { id: "book-2", title: "Emma", author: "Jane Austen" },
            due_at: "2026-09-19T23:59:59Z",
          }),
          loan({
            id: "loan-3",
            book: { id: "book-3", title: "Middlemarch", author: "George Eliot" },
            due_at: "2026-09-21T23:59:59Z",
          }),
          loan({
            id: "loan-4",
            book: { id: "book-4", title: "Persuasion", author: "Jane Austen" },
            due_at: "2026-10-03T23:59:59Z",
          }),
        ]),
    })

    renderPage("/my-loans")

    expect(await screen.findByRole("link", { name: "Dune" })).toHaveAttribute("href", "/books/book-1")
    expect(within(rowOf("Dune")).getByText("Overdue")).toBeInTheDocument()
    expect(within(rowOf("Dune")).getByText(formatDueDate("2026-09-15T23:59:59Z"))).toBeInTheDocument()
    expect(within(rowOf("Emma")).getByText("CP-0002")).toBeInTheDocument()
    expect(within(rowOf("Emma")).getByText("Due today")).toBeInTheDocument()
    // Due soon is highlighted; a date further out is plain text.
    expect(within(rowOf("Middlemarch")).getByText("Due in 2 days")).toHaveAttribute(
      "data-slot",
      "badge",
    )
    expect(within(rowOf("Persuasion")).getByText("Due in 14 days")).not.toHaveAttribute(
      "data-slot",
      "badge",
    )
    expect(screen.getByText("4 loans")).toBeInTheDocument()

    const [request] = requestsTo(fetchMock, "GET /api/me/loans")
    expect(request.search.get("status")).toBe("active")
  })

  it("says so when the member has nothing on loan", async () => {
    stubApi({ "GET /api/me/loans": () => page([]) })

    renderPage("/my-loans")

    expect(
      await screen.findByRole("heading", { name: "You have no active loans" }),
    ).toBeInTheDocument()
    expect(screen.getByRole("link", { name: "Browse the catalog" })).toHaveAttribute("href", "/catalog")
  })
})

describe("HistoryPage", () => {
  it("shows returned loans with when they were borrowed and returned, and pages", async () => {
    const returned = loan({
      borrowed_at: "2026-08-01T10:00:00Z",
      due_at: "2026-08-15T23:59:59Z",
      returned_at: "2026-08-10T15:00:00Z",
    })
    const fetchMock = stubApi({
      "GET /api/me/loans": ({ search }) =>
        page([returned], { total: 25, offset: Number(search.get("offset") ?? 0) }),
    })
    const user = userEvent.setup()

    renderPage("/history")

    await screen.findByRole("link", { name: "Dune" })
    const row = rowOf("Dune")
    expect(within(row).getByText(formatDate("2026-08-01T10:00:00Z"))).toBeInTheDocument()
    expect(within(row).getByText(formatDate("2026-08-10T15:00:00Z"))).toBeInTheDocument()
    expect(screen.getByText("Showing 1–20 of 25 loans")).toBeInTheDocument()

    await user.click(screen.getByRole("button", { name: "Next" }))

    expect(await screen.findByText("Showing 21–25 of 25 loans")).toBeInTheDocument()
    const requests = requestsTo(fetchMock, "GET /api/me/loans")
    expect(requests.map(({ search }) => search.get("status"))).toEqual(["returned", "returned"])
    expect(requests.map(({ search }) => search.get("offset"))).toEqual(["0", "20"])
  })

  it("says so when nothing has been returned yet", async () => {
    stubApi({ "GET /api/me/loans": () => page([]) })

    renderPage("/history")

    expect(await screen.findByRole("heading", { name: "No history yet" })).toBeInTheDocument()
  })
})
