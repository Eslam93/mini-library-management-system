import { screen } from "@testing-library/react"
import { describe, expect, it } from "vitest"

import { PrivacyPage, TermsPage } from "@/pages/notices-page"
import { renderWithProviders } from "@/test/render"

describe("the notices a sign-in provider links to", () => {
  it("says what signing in with Google stores, without needing an account", () => {
    renderWithProviders(<PrivacyPage />, { user: null })

    expect(screen.getByRole("heading", { name: "Privacy" })).toBeInTheDocument()
    expect(screen.getByText(/your name, your email address and/)).toBeInTheDocument()
    expect(screen.getByRole("link", { name: "Back to sign in" })).toHaveAttribute("href", "/sign-in")
  })

  it("says the demonstration comes with no warranty and points at the source", () => {
    renderWithProviders(<TermsPage />, { user: null })

    expect(screen.getByRole("heading", { name: "Terms" })).toBeInTheDocument()
    expect(screen.getByText(/no\s+warranty/)).toBeInTheDocument()
    expect(screen.getByRole("link", { name: /github\.com/ })).toBeInTheDocument()
  })
})
