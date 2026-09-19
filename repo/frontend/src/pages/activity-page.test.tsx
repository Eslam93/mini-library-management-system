import { screen, within } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

import { activityKeys } from "@/features/activity/api"
import { ActivityPage } from "@/pages/activity-page"
import { stubApi } from "@/test/api-stub"
import { activityEvent } from "@/test/fixtures"
import { renderWithProviders } from "@/test/render"

const opened = new Date("2026-09-19T12:00:00Z")
const earlier = activityEvent({
  id: 1,
  occurred_at: "2026-09-19T11:55:00Z",
  summary: "Returned Emma (CP-0007) from Omar Nasser",
})
const later = activityEvent({
  id: 2,
  occurred_at: "2026-09-19T12:00:40Z",
  summary: "Borrowed The Hobbit (CP-0216) to Maya Hassan",
  via: "copilot",
})

describe("ActivityPage", () => {
  beforeEach(() => {
    // Only Date is faked, so the page's minute timer never ticks during a test.
    vi.useFakeTimers({ toFake: ["Date"] })
    vi.setSystemTime(opened)
  })

  afterEach(() => {
    vi.useRealTimers()
    vi.unstubAllGlobals()
  })

  it("never shows an action that arrived between two clock ticks as in the future", async () => {
    let events = [earlier]
    stubApi({ "GET /api/activity": () => events })
    const { queryClient } = renderWithProviders(<ActivityPage />, { route: "/activity" })
    await screen.findByText(earlier.summary)

    // An action made elsewhere, such as a Copilot confirm, refreshes the list 40 seconds later.
    vi.setSystemTime(new Date("2026-09-19T12:00:40Z"))
    events = [later, earlier]
    await queryClient.invalidateQueries({ queryKey: activityKeys.all })

    const row = (await screen.findByText(later.summary)).closest("li")
    expect(row).not.toBeNull()
    expect(within(row as HTMLElement).queryByText(/^in /)).toBeNull()
    expect(within(row as HTMLElement).getByText("now")).toBeInTheDocument()
  })
})
