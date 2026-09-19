import { screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { toast } from "sonner"
import { describe, expect, it, vi } from "vitest"

import { AddMemberDialog } from "@/features/members/add-member-dialog"
import { errorResponse, requestsTo, stubApi } from "@/test/api-stub"
import { member } from "@/test/fixtures"
import { jsonResponse, renderWithProviders } from "@/test/render"

describe("AddMemberDialog", () => {
  it("puts member_email_taken on the email field", async () => {
    stubApi({
      "POST /api/members": () =>
        errorResponse(409, "member_email_taken", "Another member already uses this email address."),
    })
    const user = userEvent.setup()
    renderWithProviders(<AddMemberDialog open onOpenChange={vi.fn()} />)

    await user.type(screen.getByRole("textbox", { name: "Full name" }), "Maya Hassan")
    await user.type(screen.getByRole("textbox", { name: "Email (optional)" }), "maya@example.com")
    await user.click(screen.getByRole("button", { name: "Add member" }))

    const email = screen.getByRole("textbox", { name: "Email (optional)" })
    expect(
      await screen.findByText("Another member already uses this email address."),
    ).toBeInTheDocument()
    expect(email).toHaveAttribute("aria-invalid", "true")
    expect(email).toHaveFocus()
    expect(screen.queryByRole("alert")).not.toBeInTheDocument()
  })

  it("checks the name and the email format before sending", async () => {
    const fetchMock = stubApi({})
    const user = userEvent.setup()
    renderWithProviders(<AddMemberDialog open onOpenChange={vi.fn()} />)

    await user.type(screen.getByRole("textbox", { name: "Email (optional)" }), "not-an-email")
    await user.click(screen.getByRole("button", { name: "Add member" }))

    expect(await screen.findByText("Enter the member's full name.")).toBeInTheDocument()
    expect(
      screen.getByText("Enter a valid email address, such as name@example.com."),
    ).toBeInTheDocument()
    expect(fetchMock).not.toHaveBeenCalled()
  })

  it("adds a member without an email and confirms it", async () => {
    const success = vi.spyOn(toast, "success")
    const fetchMock = stubApi({
      "POST /api/members": () => jsonResponse(member({ email: null }), 201),
    })
    const onOpenChange = vi.fn()
    const user = userEvent.setup()
    renderWithProviders(<AddMemberDialog open onOpenChange={onOpenChange} />)

    await user.type(screen.getByRole("textbox", { name: "Full name" }), " Maya Hassan ")
    await user.click(screen.getByRole("button", { name: "Add member" }))

    await waitFor(() => expect(onOpenChange).toHaveBeenCalledWith(false))
    expect(requestsTo(fetchMock, "POST /api/members")[0].body).toEqual({ full_name: "Maya Hassan" })
    expect(success).toHaveBeenCalledWith("Added Maya Hassan as a member")
  })
})
