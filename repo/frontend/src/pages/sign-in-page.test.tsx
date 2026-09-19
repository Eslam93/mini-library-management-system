import { screen, within } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { beforeAll, describe, expect, it } from "vitest"

import { App } from "@/app"
import type { AuthConfigOut } from "@/lib/types"
import { errorResponse, requestsTo, stubApi } from "@/test/api-stub"
import { bookDetail, memberUser, page, staffUser } from "@/test/fixtures"
import { preloadPages } from "@/test/pages"
import { renderWithProviders } from "@/test/render"

// Signing in opens a page, which the app loads from its own file.
beforeAll(preloadPages)

function stubSignIn(config: AuthConfigOut, routes: Parameters<typeof stubApi>[0] = {}) {
  return stubApi({
    "GET /api/health": () => ({ status: "ok", checks: { database: "ok" } }),
    "GET /api/auth/config": () => config,
    ...routes,
  })
}

function renderSignIn(route = "/sign-in") {
  return renderWithProviders(<App />, { route, user: null })
}

function currentLocation() {
  return screen.getByTestId("location").textContent
}

describe("SignInPage", () => {
  it("offers only Google when only Google is set up", async () => {
    stubSignIn({ google: true, demo_login: false })

    renderSignIn()

    expect(await screen.findByRole("link", { name: "Continue with Google" })).toHaveAttribute(
      "href",
      "/api/auth/google/login",
    )
    expect(screen.queryByRole("heading", { name: "Try the demo" })).not.toBeInTheDocument()
    expect(screen.queryByRole("button", { name: /Sign in as/ })).not.toBeInTheDocument()
  })

  it("offers only the demo, one clearly labelled button per role, when only the demo is on", async () => {
    stubSignIn({ google: false, demo_login: true })

    renderSignIn()

    const demo = await screen.findByRole("region", { name: "Try the demo" })
    expect(within(demo).getByRole("button", { name: "Sign in as staff" })).toHaveAccessibleDescription(
      "Manage the catalog and members, lend and return books, and see all activity.",
    )
    expect(within(demo).getByRole("button", { name: "Sign in as member" })).toHaveAccessibleDescription(
      "Browse the catalog and see your own loans, due dates and history.",
    )
    expect(screen.queryByRole("link", { name: "Continue with Google" })).not.toBeInTheDocument()
  })

  it("says so when no sign-in method is on", async () => {
    stubSignIn({ google: false, demo_login: false })

    renderSignIn()

    expect(await screen.findByRole("heading", { name: "Sign-in is not set up" })).toBeInTheDocument()
    expect(screen.queryByRole("link", { name: "Continue with Google" })).not.toBeInTheDocument()
    expect(screen.queryByRole("button", { name: /Sign in as/ })).not.toBeInTheDocument()
  })

  it("signs in as the demo member and opens the catalog", async () => {
    const fetchMock = stubSignIn(
      { google: false, demo_login: true },
      {
        "POST /api/auth/demo": () => memberUser(),
        "GET /api/books": () => page([]),
      },
    )
    const user = userEvent.setup()
    renderSignIn()

    await user.click(await screen.findByRole("button", { name: "Sign in as member" }))

    expect(await screen.findByRole("heading", { level: 1, name: "Catalog" })).toBeInTheDocument()
    expect(currentLocation()).toBe("/catalog")
    expect(requestsTo(fetchMock, "POST /api/auth/demo")[0].body).toEqual({ role: "member" })
    const navigation = screen.getByRole("navigation", { name: "Main navigation" })
    expect(within(navigation).getByRole("link", { name: "My loans" })).toBeInTheDocument()
  })

  it("signs in as the demo staff user and opens the dashboard", async () => {
    stubSignIn({ google: true, demo_login: true }, { "POST /api/auth/demo": () => staffUser() })
    const user = userEvent.setup()
    renderSignIn()

    await user.click(await screen.findByRole("button", { name: "Sign in as staff" }))

    expect(await screen.findByRole("heading", { level: 1, name: "Dashboard" })).toBeInTheDocument()
    expect(currentLocation()).toBe("/dashboard")
  })

  it("comes back to the page in next after signing in", async () => {
    stubSignIn(
      { google: true, demo_login: true },
      {
        "POST /api/auth/demo": () => memberUser(),
        "GET /api/books/book-1": () => bookDetail(),
      },
    )
    const user = userEvent.setup()
    renderSignIn("/sign-in?next=%2Fbooks%2Fbook-1")

    expect(await screen.findByRole("link", { name: "Continue with Google" })).toHaveAttribute(
      "href",
      "/api/auth/google/login?next=%2Fbooks%2Fbook-1",
    )
    await user.click(screen.getByRole("button", { name: "Sign in as member" }))

    expect(await screen.findByRole("heading", { level: 1, name: "Dune" })).toBeInTheDocument()
    expect(currentLocation()).toBe("/books/book-1")
  })

  it("ignores a next that leads off the site", async () => {
    stubSignIn({ google: true, demo_login: true }, { "POST /api/auth/demo": () => staffUser() })
    const user = userEvent.setup()
    renderSignIn("/sign-in?next=%2F%2Fevil.example%2Fpage")

    expect(await screen.findByRole("link", { name: "Continue with Google" })).toHaveAttribute(
      "href",
      "/api/auth/google/login",
    )
    await user.click(screen.getByRole("button", { name: "Sign in as staff" }))

    expect(await screen.findByRole("heading", { level: 1, name: "Dashboard" })).toBeInTheDocument()
  })

  it("explains a failed Google sign-in", async () => {
    stubSignIn({ google: true, demo_login: false })

    renderSignIn("/sign-in?error=google")

    expect(await screen.findByRole("alert")).toHaveTextContent("Google sign-in did not work")
  })

  it("shows why a demo sign-in failed", async () => {
    stubSignIn(
      { google: false, demo_login: true },
      { "POST /api/auth/demo": () => errorResponse(404, "not_found", "Not found.") },
    )
    const user = userEvent.setup()
    renderSignIn()

    await user.click(await screen.findByRole("button", { name: "Sign in as staff" }))

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Demo sign-in is turned off on this server.",
    )
    expect(currentLocation()).toBe("/sign-in")
  })

  it("sends someone already signed in to their start page", async () => {
    stubSignIn({ google: true, demo_login: true }, { "GET /api/books": () => page([]) })

    renderWithProviders(<App />, { route: "/sign-in", user: memberUser() })

    expect(await screen.findByRole("heading", { level: 1, name: "Catalog" })).toBeInTheDocument()
    expect(currentLocation()).toBe("/catalog")
  })
})
