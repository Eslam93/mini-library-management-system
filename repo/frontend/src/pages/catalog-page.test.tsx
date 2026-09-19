import { screen, waitFor, within } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { Route, Routes } from "react-router"
import { describe, expect, it } from "vitest"

import type { UserOut } from "@/lib/types"
import { CatalogPage } from "@/pages/catalog-page"
import { errorResponse, requestsTo, stubApi } from "@/test/api-stub"
import { bookSummary, memberUser, page, staffUser } from "@/test/fixtures"
import { renderWithProviders } from "@/test/render"

const books = [
  bookSummary(),
  bookSummary({
    id: "book-2",
    title: "Emma",
    author: "Jane Austen",
    copies_total: 2,
    copies_available: 0,
    availability: "all_borrowed",
  }),
  bookSummary({
    id: "book-3",
    title: "Middlemarch",
    author: "George Eliot",
    copies_total: 0,
    copies_available: 0,
    availability: "no_copies",
  }),
]

const categories = () => ["Fiction", "Poetry", "Science fiction"]

function currentLocation() {
  return screen.getByTestId("location").textContent
}

/** The query of each catalog request, as an object. */
function bookRequests(fetchMock: ReturnType<typeof stubApi>) {
  return requestsTo(fetchMock, "GET /api/books").map(({ search }) => Object.fromEntries(search))
}

function renderCatalog(route = "/catalog", user: UserOut = staffUser()) {
  return renderWithProviders(
    <Routes>
      <Route path="/catalog" element={<CatalogPage />} />
      <Route path="/books/:bookId" element={<p>Book page</p>} />
    </Routes>,
    { route, user },
  )
}

describe("CatalogPage", () => {
  it("shows each book with its availability", async () => {
    stubApi({ "GET /api/books": () => page(books) })

    renderCatalog()

    const dune = (await screen.findByRole("link", { name: "Dune" })).closest("tr")
    expect(dune).not.toBeNull()
    expect(within(dune as HTMLElement).getByText("2 of 3 available")).toBeInTheDocument()
    expect(screen.getByText("All copies borrowed")).toBeInTheDocument()
    expect(screen.getByText("No copies")).toBeInTheDocument()
    expect(screen.getByText("3 books")).toBeInTheDocument()
  })

  it("opens a book when its row is clicked", async () => {
    stubApi({ "GET /api/books": () => page(books) })
    const user = userEvent.setup()
    renderCatalog()

    await screen.findByRole("link", { name: "Emma" })
    await user.click(screen.getByRole("cell", { name: "Jane Austen" }))

    expect(await screen.findByText("Book page")).toBeInTheDocument()
  })

  it("searches after typing stops and sends the search as q", async () => {
    const fetchMock = stubApi({
      "GET /api/books": ({ search }) =>
        search.get("q") === "herb" ? page([books[0]]) : page(books),
    })
    const user = userEvent.setup()
    renderCatalog()
    await screen.findByText("Emma")

    await user.type(screen.getByRole("searchbox", { name: "Search the catalog" }), "herb")

    expect(await screen.findByText("1 book")).toBeInTheDocument()
    expect(screen.queryByText("Emma")).not.toBeInTheDocument()
    const searches = requestsTo(fetchMock, "GET /api/books").map(({ search }) => search.get("q"))
    expect(searches).toEqual([null, "herb"])
  })

  it("shows a no-results state for the search in the URL, and clears it", async () => {
    stubApi({
      "GET /api/books": ({ search }) => (search.get("q") ? page([]) : page(books)),
    })
    const user = userEvent.setup()
    renderCatalog("/catalog?q=zzz")

    expect(
      await screen.findByRole("heading", { name: 'No books match "zzz"' }),
    ).toBeInTheDocument()
    expect(screen.getByRole("searchbox", { name: "Search the catalog" })).toHaveValue("zzz")

    await user.click(screen.getByRole("button", { name: "Clear search" }))

    expect(await screen.findByRole("link", { name: "Dune" })).toBeInTheDocument()
    expect(screen.getByRole("searchbox", { name: "Search the catalog" })).toHaveValue("")
  })

  it("filters by availability and category and changes the order, keeping each choice in the URL", async () => {
    const fetchMock = stubApi({
      "GET /api/books": () => page(books, { total: 45 }),
      "GET /api/books/categories": categories,
    })
    const user = userEvent.setup()
    renderCatalog("/catalog?page=2")
    await screen.findByRole("link", { name: "Dune" })
    expect(screen.queryByRole("button", { name: "Clear all" })).not.toBeInTheDocument()

    await user.click(screen.getByRole("button", { name: "Available now" }))
    expect(screen.getByRole("button", { name: "Available now" })).toHaveAttribute("aria-pressed", "true")
    expect(currentLocation()).toBe("/catalog?available_only=true")

    await screen.findByRole("option", { name: "Poetry" })
    await user.selectOptions(screen.getByRole("combobox", { name: "Category" }), "Poetry")
    expect(currentLocation()).toBe("/catalog?available_only=true&category=Poetry")

    await user.selectOptions(screen.getByRole("combobox", { name: "Sort by" }), "Recently added")
    expect(currentLocation()).toBe("/catalog?available_only=true&category=Poetry&sort=recent")

    await waitFor(() => expect(bookRequests(fetchMock)).toHaveLength(4))
    expect(bookRequests(fetchMock)).toEqual([
      { limit: "20", offset: "20" },
      { available_only: "true", limit: "20", offset: "0" },
      { category: "Poetry", available_only: "true", limit: "20", offset: "0" },
      { category: "Poetry", available_only: "true", sort: "recent", limit: "20", offset: "0" },
    ])
    expect(screen.getByRole("button", { name: "Clear all" })).toBeInTheDocument()
  })

  it("reads the search, filters and order from the URL and sends them together", async () => {
    const fetchMock = stubApi({
      "GET /api/books": () => page(books, { total: 45, offset: 20 }),
      "GET /api/books/categories": categories,
    })

    renderCatalog("/catalog?q=dune&category=poetry&available_only=true&sort=year_desc&page=2")

    await screen.findByRole("link", { name: "Dune" })
    expect(screen.getByRole("searchbox", { name: "Search the catalog" })).toHaveValue("dune")
    expect(screen.getByRole("button", { name: "Available now" })).toHaveAttribute("aria-pressed", "true")
    // The link spells the category in lower case; the select shows the catalog's spelling.
    await waitFor(() => expect(screen.getByRole("combobox", { name: "Category" })).toHaveValue("Poetry"))
    expect(screen.getByRole("combobox", { name: "Sort by" })).toHaveValue("year_desc")
    expect(bookRequests(fetchMock)).toEqual([
      { q: "dune", category: "poetry", available_only: "true", sort: "year_desc", limit: "20", offset: "20" },
    ])
  })

  it("keeps a category from an old link selectable when no book has it any more", async () => {
    stubApi({
      "GET /api/books": () => page([]),
      "GET /api/books/categories": categories,
    })

    renderCatalog("/catalog?category=Atlases")

    await screen.findByRole("option", { name: "Poetry" })
    const select = screen.getByRole("combobox", { name: "Category" })
    expect(select).toHaveValue("Atlases")
    expect(within(select).getAllByRole("option").map((option) => option.textContent)).toEqual([
      "All categories",
      "Atlases",
      "Fiction",
      "Poetry",
      "Science fiction",
    ])
  })

  it("clears the search, the filters and the order in one step", async () => {
    const fetchMock = stubApi({
      "GET /api/books": () => page(books),
      "GET /api/books/categories": categories,
    })
    const user = userEvent.setup()
    renderCatalog("/catalog?q=dune&category=Poetry&available_only=true&sort=author&page=2")
    await screen.findByRole("link", { name: "Dune" })

    await user.click(screen.getByRole("button", { name: "Clear all" }))

    expect(currentLocation()).toBe("/catalog")
    expect(screen.getByRole("searchbox", { name: "Search the catalog" })).toHaveValue("")
    expect(screen.getByRole("button", { name: "Available now" })).toHaveAttribute("aria-pressed", "false")
    expect(screen.getByRole("combobox", { name: "Category" })).toHaveValue("")
    expect(screen.getByRole("combobox", { name: "Sort by" })).toHaveValue("title")
    expect(screen.queryByRole("button", { name: "Clear all" })).not.toBeInTheDocument()
    await waitFor(() => expect(bookRequests(fetchMock).at(-1)).toEqual({ limit: "20", offset: "0" }))
  })

  it("shows a no-results state for the filters, and clears only the filters", async () => {
    stubApi({
      "GET /api/books": ({ search }) => (search.get("available_only") ? page([]) : page(books)),
      "GET /api/books/categories": categories,
    })
    const user = userEvent.setup()
    renderCatalog("/catalog?q=e&available_only=true&sort=author")

    expect(
      await screen.findByRole("heading", { name: 'No books match "e" with these filters' }),
    ).toBeInTheDocument()

    await user.click(screen.getByRole("button", { name: "Clear filters" }))

    expect(await screen.findByRole("link", { name: "Dune" })).toBeInTheDocument()
    expect(currentLocation()).toBe("/catalog?q=e&sort=author")
  })

  it("shows an empty catalog with a way to add the first book", async () => {
    stubApi({ "GET /api/books": () => page([]) })

    renderCatalog()

    expect(await screen.findByRole("heading", { name: "No books yet" })).toBeInTheDocument()
    expect(screen.getAllByRole("button", { name: "Add book" })).toHaveLength(2)
  })

  it("shows an error with a retry", async () => {
    let calls = 0
    stubApi({
      "GET /api/books": () => {
        calls += 1
        return calls === 1 ? errorResponse(500, "internal_error", "The server failed.") : page(books)
      },
    })
    const user = userEvent.setup()
    renderCatalog()

    expect(await screen.findByRole("alert")).toHaveTextContent("The server failed.")
    await user.click(screen.getByRole("button", { name: "Try again" }))

    expect(await screen.findByRole("link", { name: "Dune" })).toBeInTheDocument()
  })

  it("pages through a long catalog", async () => {
    const fetchMock = stubApi({
      "GET /api/books": ({ search }) =>
        page(books, { total: 45, offset: Number(search.get("offset") ?? 0) }),
    })
    const user = userEvent.setup()
    renderCatalog()

    expect(await screen.findByText("Showing 1–20 of 45 books")).toBeInTheDocument()
    expect(screen.getByRole("button", { name: "Previous" })).toBeDisabled()

    await user.click(screen.getByRole("button", { name: "Next" }))

    expect(await screen.findByText("Showing 21–40 of 45 books")).toBeInTheDocument()
    const offsets = requestsTo(fetchMock, "GET /api/books").map(({ search }) => search.get("offset"))
    expect(offsets).toEqual(["0", "20"])
  })

  it("shows members the catalog without Add book", async () => {
    stubApi({ "GET /api/books": () => page(books) })

    renderCatalog("/catalog", memberUser())

    expect(await screen.findByRole("link", { name: "Dune" })).toBeInTheDocument()
    expect(screen.queryByRole("button", { name: "Add book" })).not.toBeInTheDocument()
  })

  it("shows members an empty catalog without a way to add books", async () => {
    stubApi({ "GET /api/books": () => page([]) })

    renderCatalog("/catalog", memberUser())

    expect(await screen.findByRole("heading", { name: "No books yet" })).toBeInTheDocument()
    expect(screen.queryByRole("button", { name: "Add book" })).not.toBeInTheDocument()
  })
})
