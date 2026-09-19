import { screen, waitFor, within } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { Route, Routes } from "react-router"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

import { formatCount } from "@/lib/format"
import { DashboardPage } from "@/pages/dashboard-page"
import { errorResponse, requestsTo, stubApi } from "@/test/api-stub"
import { activityEvent, dashboard, loan } from "@/test/fixtures"
import { renderWithProviders } from "@/test/render"

const overdueLoan = loan({
  id: "loan-1",
  copy: { id: "copy-1", code: "CP-0001" },
  member: { id: "member-1", full_name: "Maya Hassan" },
  due_at: "2026-09-16T23:59:59Z",
  is_overdue: true,
  days_overdue: 3,
})

const dueSoonLoan = loan({
  id: "loan-2",
  copy: { id: "copy-7", code: "CP-0007" },
  book: { id: "book-2", title: "Emma", author: "Jane Austen" },
  member: { id: "member-2", full_name: "Omar Nasser" },
  due_at: "2026-09-20T23:59:59Z",
})

const busyLibrary = dashboard({
  counts: {
    titles: 280,
    copies: 512,
    available: 431,
    on_loan: 81,
    overdue: 7,
    members: 204,
    active_members_90d: 1234,
  },
  overdue: [overdueLoan],
  due_soon: [dueSoonLoan],
  recent_activity: [activityEvent({ summary: "Returned Emma (CP-0007) from Omar Nasser" })],
})

function renderDashboard() {
  return renderWithProviders(
    <Routes>
      <Route path="/dashboard" element={<DashboardPage />} />
    </Routes>,
    { route: "/dashboard" },
  )
}

describe("DashboardPage", () => {
  beforeEach(() => {
    // Midday UTC keeps "today" the same calendar date in every time zone.
    vi.useFakeTimers({ toFake: ["Date"] })
    vi.setSystemTime(new Date("2026-09-19T12:00:00Z"))
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it("shows each count with its label, linking to where the work is done", async () => {
    stubApi({ "GET /api/dashboard": () => busyLibrary })

    renderDashboard()

    const counts = await screen.findByRole("list", { name: "Library counts" })
    const card = (label: RegExp) => within(counts).getByRole("link", { name: label })
    expect(card(/^Titles/)).toHaveTextContent("280")
    expect(card(/^Titles/)).toHaveAttribute("href", "/catalog")
    expect(card(/^Copies/)).toHaveTextContent("512")
    expect(card(/^Available now/)).toHaveTextContent("431")
    expect(card(/^On loan/)).toHaveTextContent("81")
    expect(card(/^Overdue/)).toHaveTextContent("7")
    expect(card(/^Overdue/)).toHaveAttribute("href", "/circulation?status=overdue")
    expect(card(/^Members/)).toHaveTextContent("204")
    expect(card(/^Active in 90 days/)).toHaveTextContent(formatCount(1234))
  })

  it("lists overdue and due-soon loans with their member and a Return action", async () => {
    stubApi({ "GET /api/dashboard": () => busyLibrary })

    renderDashboard()

    const overdue = await screen.findByRole("region", { name: "Overdue" })
    expect(within(overdue).getByRole("link", { name: "Dune" })).toHaveAttribute("href", "/books/book-1")
    expect(within(overdue).getByRole("link", { name: "Maya Hassan" })).toHaveAttribute(
      "href",
      "/members/member-1",
    )
    expect(within(overdue).getByText("CP-0001")).toBeInTheDocument()
    expect(within(overdue).getByText("3 days overdue")).toBeInTheDocument()
    expect(within(overdue).getByText("7 in all, oldest due date first.")).toBeInTheDocument()
    expect(within(overdue).getByRole("button", { name: "Return CP-0001" })).toBeInTheDocument()

    const dueSoon = screen.getByRole("region", { name: "Due in the next 3 days" })
    expect(within(dueSoon).getByRole("link", { name: "Omar Nasser" })).toHaveAttribute(
      "href",
      "/members/member-2",
    )
    expect(within(dueSoon).getByText("Due tomorrow")).toBeInTheDocument()
    expect(within(dueSoon).getByRole("button", { name: "Return CP-0007" })).toBeInTheDocument()

    const activity = screen.getByRole("region", { name: "Recent activity" })
    expect(within(activity).getByText("Returned Emma (CP-0007) from Omar Nasser")).toBeInTheDocument()
    expect(within(activity).getByRole("link", { name: "All activity" })).toHaveAttribute(
      "href",
      "/activity",
    )
  })

  it("says it is good news when nothing is overdue", async () => {
    stubApi({ "GET /api/dashboard": () => dashboard() })

    renderDashboard()

    const overdue = await screen.findByRole("region", { name: "Overdue" })
    expect(within(overdue).getByRole("heading", { name: "No overdue loans" })).toBeInTheDocument()
    expect(within(overdue).getByText(/Good news/)).toBeInTheDocument()
    expect(
      within(screen.getByRole("region", { name: "Due in the next 3 days" })).getByRole("heading", {
        name: "Nothing due in the next 3 days",
      }),
    ).toBeInTheDocument()
    expect(screen.getByRole("heading", { name: "No activity yet" })).toBeInTheDocument()
  })

  it("returns an overdue loan after confirmation and refreshes the numbers", async () => {
    const fetchMock = stubApi({
      "GET /api/dashboard": () => busyLibrary,
      "POST /api/loans/loan-1/return": () =>
        loan({ ...overdueLoan, returned_at: "2026-09-19T12:00:00Z", is_overdue: false, days_overdue: 0 }),
    })
    const user = userEvent.setup()
    renderDashboard()

    const overdue = await screen.findByRole("region", { name: "Overdue" })
    await user.click(within(overdue).getByRole("button", { name: "Return CP-0001" }))
    const dialog = await screen.findByRole("alertdialog", { name: "Return this copy?" })
    expect(dialog).toHaveTextContent("Dune (CP-0001), borrowed by Maya Hassan")
    await user.click(within(dialog).getByRole("button", { name: "Return copy" }))

    await waitFor(() => expect(requestsTo(fetchMock, "GET /api/dashboard")).toHaveLength(2))
    expect(requestsTo(fetchMock, "POST /api/loans/loan-1/return")).toHaveLength(1)
  })

  it("shows an error with a retry", async () => {
    let calls = 0
    stubApi({
      "GET /api/dashboard": () => {
        calls += 1
        return calls === 1 ? errorResponse(500, "internal_error", "The server failed.") : busyLibrary
      },
    })
    const user = userEvent.setup()
    renderDashboard()

    expect(await screen.findByRole("alert")).toHaveTextContent("Could not load the dashboard")
    await user.click(screen.getByRole("button", { name: "Try again" }))

    expect(await screen.findByRole("list", { name: "Library counts" })).toBeInTheDocument()
  })
})
