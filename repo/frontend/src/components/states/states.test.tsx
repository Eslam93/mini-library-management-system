import { useState } from "react"
import { useQuery } from "@tanstack/react-query"
import { screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { describe, expect, it, vi } from "vitest"

import { ErrorBoundary } from "@/components/states/error-boundary"
import { QueryState } from "@/components/states/query-state"
import { ApiError } from "@/lib/api"
import { renderWithProviders } from "@/test/render"

function BookList({ load }: { load: () => Promise<string[]> }) {
  const query = useQuery({ queryKey: ["books"], queryFn: load })
  return (
    <QueryState query={query}>
      {(books) => (
        <ul>
          {books.map((title) => (
            <li key={title}>{title}</li>
          ))}
        </ul>
      )}
    </QueryState>
  )
}

describe("QueryState", () => {
  it("shows the loading state, then the data", async () => {
    renderWithProviders(<BookList load={async () => ["Dune"]} />)

    expect(screen.getByRole("status")).toHaveTextContent("Loading")
    expect(await screen.findByText("Dune")).toBeInTheDocument()
  })

  it("shows the empty state for an empty list", async () => {
    renderWithProviders(<BookList load={async () => []} />)

    expect(await screen.findByText("Nothing here yet")).toBeInTheDocument()
  })

  it("shows the error with its request id, and retries", async () => {
    const load = vi
      .fn<() => Promise<string[]>>()
      .mockRejectedValueOnce(
        new ApiError({
          status: 500,
          code: "internal_error",
          message: "The server failed.",
          requestId: "req-9",
        }),
      )
      .mockResolvedValueOnce(["Dune"])
    renderWithProviders(<BookList load={load} />)

    expect(await screen.findByRole("alert")).toHaveTextContent("The server failed.")
    expect(screen.getByText("req-9")).toBeInTheDocument()

    await userEvent.click(screen.getByRole("button", { name: "Try again" }))
    expect(await screen.findByText("Dune")).toBeInTheDocument()
  })
})

function Crash(): never {
  throw new Error("render failed")
}

function Harness() {
  const [page, setPage] = useState("broken")
  return (
    <>
      <button onClick={() => setPage("healthy")}>Go elsewhere</button>
      <ErrorBoundary resetKey={page}>{page === "broken" ? <Crash /> : <p>Healthy page</p>}</ErrorBoundary>
    </>
  )
}

describe("ErrorBoundary", () => {
  it("shows a fallback for a crash and clears it when the reset key changes", async () => {
    vi.spyOn(console, "error").mockImplementation(() => {})
    renderWithProviders(<Harness />)

    expect(screen.getByRole("alert")).toHaveTextContent("This page failed to load")

    await userEvent.click(screen.getByRole("button", { name: "Go elsewhere" }))
    expect(screen.getByText("Healthy page")).toBeInTheDocument()
  })
})
