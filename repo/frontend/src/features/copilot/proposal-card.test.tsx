import { screen, waitFor, within } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

import { activityKeys } from "@/features/activity/api"
import { bookKeys } from "@/features/books/api"
import { copyKeys } from "@/features/circulation/api"
import { copilotKeys } from "@/features/copilot/api"
import { ProposalCard } from "@/features/copilot/proposal-card"
import type { ProposalOut } from "@/features/copilot/types"
import { dashboardKeys } from "@/features/dashboard/api"
import { loanKeys } from "@/features/loans/api"
import { memberKeys } from "@/features/members/api"
import { formatDate, formatDueDate, formatRelative } from "@/lib/format"
import { errorResponse, requestsTo, stubApi } from "@/test/api-stub"
import { loan, proposal } from "@/test/fixtures"
import { jsonResponse, renderWithProviders } from "@/test/render"

const PROPOSAL_PATH = "/api/copilot/proposals/proposal-1"

type RenderCardOptions = {
  /**
   * True for a card that arrived in this page's conversation: the chat has
   * already put the proposal in the cache. False for a card restored from storage.
   */
  streamed?: boolean
}

function renderCard(seed: ProposalOut = proposal(), { streamed = true }: RenderCardOptions = {}) {
  const onNavigate = vi.fn()
  const result = renderWithProviders(<ProposalCard proposal={seed} onNavigate={onNavigate} />, {
    route: "/circulation",
    prepare: (queryClient) => {
      if (streamed) queryClient.setQueryData(copilotKeys.proposal(seed.id), seed)
    },
  })
  return { ...result, onNavigate }
}

function card(action: "borrow" | "return" = "borrow") {
  return screen.getByRole("article", { name: `Proposed ${action}` })
}

describe("ProposalCard", () => {
  beforeEach(() => {
    // One minute after the proposal was made, nine before it expires.
    vi.useFakeTimers({ toFake: ["Date"] })
    vi.setSystemTime(new Date("2026-09-19T12:01:00Z"))
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it("shows a pending borrow with its book, copy, member, due date and expiry, and asks nothing more", () => {
    const fetchMock = stubApi({})

    renderCard()

    const borrow = card()
    expect(within(borrow).getByText("Borrow")).toBeInTheDocument()
    expect(within(borrow).getByRole("link", { name: "The Hobbit" })).toHaveAttribute("href", "/books/book-7")
    expect(within(borrow).getByText("J. R. R. Tolkien")).toBeInTheDocument()
    expect(within(borrow).getByText("CP-0217")).toBeInTheDocument()
    expect(within(borrow).getByRole("link", { name: "Maya Hassan" })).toHaveAttribute("href", "/members/member-1")
    expect(within(borrow).getByText(formatDueDate("2026-10-03T23:59:59Z"))).toBeInTheDocument()
    const expiry = formatRelative("2026-09-19T12:10:00Z", Date.now())
    expect(within(borrow).getByText(new RegExp(`Expires ${expiry}`))).toBeInTheDocument()
    expect(within(borrow).getByRole("button", { name: "Confirm" })).toBeEnabled()
    expect(within(borrow).getByRole("button", { name: "Cancel" })).toBeEnabled()
    expect(fetchMock).not.toHaveBeenCalled()
  })

  it("confirms: both buttons wait while it runs, then it shows the loan with links and refreshes the loan views", async () => {
    let finishConfirm!: (response: Response) => void
    const fetchMock = stubApi({
      [`POST ${PROPOSAL_PATH}/confirm`]: () =>
        new Promise<Response>((resolve) => {
          finishConfirm = resolve
        }),
    })
    const user = userEvent.setup()
    const { queryClient, onNavigate } = renderCard()
    const invalidate = vi.spyOn(queryClient, "invalidateQueries")

    await user.click(within(card()).getByRole("button", { name: "Confirm" }))

    expect(within(card()).getByRole("button", { name: "Confirming…" })).toBeDisabled()
    expect(within(card()).getByRole("button", { name: "Cancel" })).toBeDisabled()
    expect(invalidate).not.toHaveBeenCalled()

    const newLoan = loan({
      id: "loan-9",
      copy: { id: "copy-17", code: "CP-0217" },
      book: { id: "book-7", title: "The Hobbit", author: "J. R. R. Tolkien" },
      member: { id: "member-1", full_name: "Maya Hassan" },
      borrowed_at: "2026-09-19T12:01:00Z",
      due_at: "2026-10-03T23:59:59Z",
    })
    finishConfirm(
      jsonResponse(proposal({ status: "confirmed", resolved_at: "2026-09-19T12:01:00Z", loan: newLoan })),
    )

    expect(await within(card()).findByText(`Borrowed, due ${formatDueDate(newLoan.due_at)}`)).toBeInTheDocument()
    expect(within(card()).queryByRole("button")).not.toBeInTheDocument()
    expect(requestsTo(fetchMock, `POST ${PROPOSAL_PATH}/confirm`)).toHaveLength(1)
    const refreshed = invalidate.mock.calls.map(([filters]) => filters?.queryKey)
    expect(refreshed).toEqual(
      expect.arrayContaining([
        loanKeys.all,
        dashboardKeys.all,
        bookKeys.lists(),
        bookKeys.detail("book-7"),
        memberKeys.all,
        activityKeys.all,
        copyKeys.all,
      ]),
    )

    // The member's link leads to the member's page and closes the panel.
    await user.click(within(card()).getByRole("link", { name: "Maya Hassan" }))
    expect(onNavigate).toHaveBeenCalledTimes(1)
    expect(screen.getByTestId("location")).toHaveTextContent("/members/member-1")
  })

  it("shows the server's message when the copy was borrowed elsewhere before the confirm", async () => {
    stubApi({
      [`POST ${PROPOSAL_PATH}/confirm`]: () =>
        errorResponse(409, "copy_unavailable", "Copy CP-0217 is already on loan."),
    })
    const user = userEvent.setup()
    renderCard()

    await user.click(within(card()).getByRole("button", { name: "Confirm" }))

    const alert = await within(card()).findByRole("alert")
    expect(alert).toHaveTextContent("Could not borrow")
    expect(alert).toHaveTextContent("Copy CP-0217 is already on loan. Nothing changed.")
    expect(within(card()).queryByRole("button")).not.toBeInTheDocument()
  })

  it("cancels, and says nothing changed", async () => {
    const fetchMock = stubApi({
      [`POST ${PROPOSAL_PATH}/cancel`]: () => new Response(null, { status: 204 }),
    })
    const user = userEvent.setup()
    renderCard()

    await user.click(within(card()).getByRole("button", { name: "Cancel" }))

    expect(await within(card()).findByText("Cancelled. Nothing changed.")).toBeInTheDocument()
    expect(within(card()).queryByRole("button")).not.toBeInTheDocument()
    expect(requestsTo(fetchMock, `POST ${PROPOSAL_PATH}/confirm`)).toHaveLength(0)
  })

  it("shows expired once expires_at has passed, without asking the server", () => {
    const fetchMock = stubApi({})

    renderCard(proposal({ expires_at: "2026-09-19T12:00:30Z" }), { streamed: false })

    expect(within(card()).getByText(/This proposal expired, so nothing changed/)).toBeInTheDocument()
    expect(within(card()).queryByRole("button")).not.toBeInTheDocument()
    expect(fetchMock).not.toHaveBeenCalled()
  })

  it("shows expired when the server refuses a confirm as expired", async () => {
    stubApi({
      [`POST ${PROPOSAL_PATH}/confirm`]: () =>
        errorResponse(409, "proposal_expired", "This proposal has expired."),
    })
    const user = userEvent.setup()
    renderCard()

    await user.click(within(card()).getByRole("button", { name: "Confirm" }))

    expect(await within(card()).findByText(/This proposal expired/)).toBeInTheDocument()
    expect(within(card()).queryByRole("button")).not.toBeInTheDocument()
  })

  it("stays pending after a lost connection, so staff can try again", async () => {
    stubApi({
      [`POST ${PROPOSAL_PATH}/confirm`]: () => {
        throw new TypeError("Failed to fetch")
      },
    })
    const user = userEvent.setup()
    renderCard()

    await user.click(within(card()).getByRole("button", { name: "Confirm" }))

    expect(await within(card()).findByRole("alert")).toHaveTextContent("Could not reach the server.")
    expect(within(card()).getByRole("button", { name: "Confirm" })).toBeEnabled()
  })

  it("reads a pending card restored from storage once, and shows how the proposal ended", async () => {
    const seed = proposal({
      action: "return",
      borrowed_at: "2026-09-01T10:00:00Z",
      due_at: "2026-09-15T23:59:59Z",
      is_overdue: true,
    })
    const fetchMock = stubApi({
      [`GET ${PROPOSAL_PATH}`]: () =>
        proposal({ ...seed, status: "confirmed", resolved_at: "2026-09-19T12:00:40Z" }),
    })

    renderCard(seed, { streamed: false })

    const returning = card("return")
    expect(await within(returning).findByText("Returned")).toBeInTheDocument()
    expect(within(returning).getByText("Return")).toBeInTheDocument()
    expect(within(returning).getByText(formatDate("2026-09-01T10:00:00Z"))).toBeInTheDocument()
    expect(within(returning).getByText(formatDueDate("2026-09-15T23:59:59Z"))).toBeInTheDocument()
    expect(within(returning).getByText("Overdue")).toBeInTheDocument()
    expect(within(returning).queryByRole("button")).not.toBeInTheDocument()
    await waitFor(() => expect(requestsTo(fetchMock, `GET ${PROPOSAL_PATH}`)).toHaveLength(1))
  })
})
