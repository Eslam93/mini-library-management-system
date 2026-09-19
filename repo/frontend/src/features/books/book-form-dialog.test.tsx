import { screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { Route, Routes } from "react-router"
import { toast } from "sonner"
import { describe, expect, it, vi } from "vitest"

import { BookFormDialog } from "@/features/books/book-form-dialog"
import { errorResponse, requestsTo, stubApi } from "@/test/api-stub"
import { bookDetail } from "@/test/fixtures"
import { jsonResponse, renderWithProviders } from "@/test/render"
import type { BookDetail } from "@/lib/types"

function renderDialog(book?: BookDetail) {
  return renderWithProviders(
    <Routes>
      <Route path="/" element={<BookFormDialog open onOpenChange={vi.fn()} book={book} />} />
      <Route path="/books/:bookId" element={<p>Book page</p>} />
    </Routes>,
  )
}

const field = (name: RegExp) => screen.getByRole("textbox", { name })

describe("BookFormDialog", () => {
  it("shows the client rules inline and sends nothing", async () => {
    const fetchMock = stubApi({})
    const user = userEvent.setup()
    renderDialog()

    await user.click(screen.getByRole("button", { name: "Add book" }))

    expect(await screen.findByText("Enter the title.")).toBeInTheDocument()
    expect(screen.getByText("Enter the author.")).toBeInTheDocument()
    expect(field(/^Title/)).toHaveAttribute("aria-invalid", "true")

    await user.type(field(/^ISBN/), "12345")
    await user.type(field(/^Year published/), "1200")
    await user.click(screen.getByRole("button", { name: "Add book" }))
    expect(await screen.findByText("Enter 10 or 13 digits. An ISBN-10 may end in X.")).toBeInTheDocument()
    expect(screen.getByText(/^Enter a year from 1450 to \d{4}\.$/)).toBeInTheDocument()

    // Right shape, wrong check digit (the real one ends in 9).
    await user.clear(field(/^ISBN/))
    await user.type(field(/^ISBN/), "978-0-441-17271-8")
    expect(
      await screen.findByText("This ISBN's check digit does not match. Check it for a typo."),
    ).toBeInTheDocument()

    expect(fetchMock).not.toHaveBeenCalled()
  })

  it("maps a server 422 onto the matching fields and shows the rest above the form", async () => {
    stubApi({
      "POST /api/books": () =>
        errorResponse(422, "validation_failed", "The request is not valid.", {
          errors: [
            {
              location: ["body", "title"],
              message: "String should have at most 300 characters",
              type: "string_too_long",
            },
            {
              location: ["body", "isbn"],
              message: "Value error, Not a valid ISBN.",
              type: "value_error",
            },
            { location: ["body"], message: "The book could not be read.", type: "model" },
          ],
        }),
    })
    const user = userEvent.setup()
    renderDialog()

    await user.type(field(/^Title/), "Dune")
    await user.type(field(/^Author/), "Frank Herbert")
    await user.click(screen.getByRole("button", { name: "Add book" }))

    expect(await screen.findByText("String should have at most 300 characters")).toBeInTheDocument()
    expect(field(/^Title/)).toHaveAttribute("aria-invalid", "true")
    expect(field(/^Title/)).toHaveAccessibleDescription(
      "String should have at most 300 characters",
    )
    expect(screen.getByText("Not a valid ISBN.")).toBeInTheDocument()
    expect(screen.getByRole("alert")).toHaveTextContent("The book could not be read.")
  })

  it("puts isbn_taken on the ISBN field", async () => {
    stubApi({
      "POST /api/books": () =>
        errorResponse(409, "isbn_taken", "Another book in the catalog has this ISBN."),
    })
    const user = userEvent.setup()
    renderDialog()

    await user.type(field(/^Title/), "Dune")
    await user.type(field(/^Author/), "Frank Herbert")
    await user.type(field(/^ISBN/), "0-441-17271-7")
    await user.click(screen.getByRole("button", { name: "Add book" }))

    expect(await screen.findByText("Another book in the catalog has this ISBN.")).toBeInTheDocument()
    expect(field(/^ISBN/)).toHaveAttribute("aria-invalid", "true")
    expect(screen.queryByRole("alert")).not.toBeInTheDocument()
  })

  it("adds a book with a normalized ISBN, confirms it, and opens its page", async () => {
    const success = vi.spyOn(toast, "success")
    const fetchMock = stubApi({
      "POST /api/books": () => jsonResponse(bookDetail({ id: "book-7" }), 201),
    })
    const user = userEvent.setup()
    renderDialog()

    await user.type(field(/^Title/), "  Dune ")
    await user.type(field(/^Author/), "Frank Herbert")
    await user.type(field(/^ISBN/), "978-0-441-17271-9")
    await user.clear(screen.getByRole("spinbutton", { name: "Copies" }))
    await user.type(screen.getByRole("spinbutton", { name: "Copies" }), "3")
    await user.click(screen.getByRole("button", { name: "Add book" }))

    expect(await screen.findByText("Book page")).toBeInTheDocument()
    expect(requestsTo(fetchMock, "POST /api/books")[0].body).toEqual({
      title: "Dune",
      author: "Frank Herbert",
      isbn: "9780441172719",
      copies: 3,
    })
    expect(success).toHaveBeenCalledWith("Added Dune with 3 copies")
  })

  it("prefills the edit form and sends only the changed fields", async () => {
    const book = bookDetail()
    const fetchMock = stubApi({
      "PATCH /api/books/book-1": () => bookDetail({ category: null }),
    })
    const user = userEvent.setup()
    renderDialog(book)

    expect(field(/^Title/)).toHaveValue("Dune")
    expect(field(/^ISBN/)).toHaveValue("9780441172719")
    expect(screen.queryByRole("spinbutton", { name: "Copies" })).not.toBeInTheDocument()
    expect(screen.getByRole("button", { name: "Save changes" })).toBeDisabled()

    await user.clear(field(/^Category/))
    await user.click(screen.getByRole("button", { name: "Save changes" }))

    await waitFor(() =>
      expect(requestsTo(fetchMock, "PATCH /api/books/book-1")[0]?.body).toEqual({ category: null }),
    )
  })
})

describe("BookFormDialog ISBN lookup", () => {
  const found = { isbn: "9780441172719", title: "Dune", author: "Frank Herbert", published_year: 1965 }

  it("fills title, author and year from the ISBN with a spinner meanwhile, and leaves the category alone", async () => {
    let answer: (value: unknown) => void = () => {}
    const fetchMock = stubApi({
      "GET /api/isbn/9780441172719": () =>
        new Promise((resolve) => {
          answer = resolve
        }),
    })
    const user = userEvent.setup()
    renderDialog()

    await user.type(field(/^Category/), "Classics")
    await user.type(field(/^ISBN/), "978-0-441-17271-9")
    await user.click(screen.getByRole("button", { name: "Look up" }))

    expect(await screen.findByRole("button", { name: "Looking up…" })).toBeDisabled()
    answer(found)

    expect(
      await screen.findByText("Found Dune by Frank Herbert. Check the details before adding the book."),
    ).toBeInTheDocument()
    expect(screen.getByRole("status")).toHaveTextContent("Found Dune by Frank Herbert.")
    expect(field(/^Title/)).toHaveValue("Dune")
    expect(field(/^Author/)).toHaveValue("Frank Herbert")
    expect(field(/^Year published/)).toHaveValue("1965")
    expect(field(/^Category/)).toHaveValue("Classics")
    expect(requestsTo(fetchMock, "GET /api/isbn/9780441172719")).toHaveLength(1)
  })

  it("says when no book has the ISBN, and the form still adds the book by hand", async () => {
    const fetchMock = stubApi({
      "GET /api/isbn/9780441172719": () =>
        errorResponse(404, "isbn_not_found", "No book is known for this ISBN."),
      "POST /api/books": () => jsonResponse(bookDetail({ id: "book-7" }), 201),
    })
    const user = userEvent.setup()
    renderDialog()

    await user.type(field(/^ISBN/), "9780441172719")
    await user.click(screen.getByRole("button", { name: "Look up" }))

    expect(
      await screen.findByText("No book found for this ISBN. Fill in the details by hand."),
    ).toBeInTheDocument()
    expect(field(/^Title/)).toHaveValue("")

    await user.type(field(/^Title/), "Dune")
    await user.type(field(/^Author/), "Frank Herbert")
    await user.click(screen.getByRole("button", { name: "Add book" }))

    expect(await screen.findByText("Book page")).toBeInTheDocument()
    expect(requestsTo(fetchMock, "POST /api/books")[0].body).toMatchObject({ isbn: "9780441172719" })
  })

  it("says the lookup service is unavailable and leaves the fields to fill by hand", async () => {
    stubApi({
      "GET /api/isbn/9780441172719": () =>
        errorResponse(503, "isbn_lookup_unavailable", "The ISBN lookup service did not answer."),
    })
    const user = userEvent.setup()
    renderDialog()

    await user.type(field(/^Title/), "My own title")
    await user.type(field(/^ISBN/), "9780441172719")
    await user.click(screen.getByRole("button", { name: "Look up" }))

    expect(
      await screen.findByText("The ISBN lookup service is unavailable right now. Fill in the details by hand."),
    ).toBeInTheDocument()
    expect(field(/^Title/)).toHaveValue("My own title")
    expect(screen.getByRole("button", { name: "Look up" })).toBeEnabled()
  })

  it("checks the ISBN before asking, so a missing or mistyped one sends nothing", async () => {
    const fetchMock = stubApi({})
    const user = userEvent.setup()
    renderDialog()

    await user.click(screen.getByRole("button", { name: "Look up" }))
    expect(await screen.findByText("Enter an ISBN to look it up.")).toBeInTheDocument()

    await user.type(field(/^ISBN/), "978-0-441-17271-8")
    await user.click(screen.getByRole("button", { name: "Look up" }))
    expect(
      await screen.findByText("This ISBN's check digit does not match. Check it for a typo."),
    ).toBeInTheDocument()

    expect(fetchMock).not.toHaveBeenCalled()
  })

  it("is offered only when adding a book", () => {
    stubApi({})
    renderDialog(bookDetail())

    expect(screen.queryByRole("button", { name: "Look up" })).not.toBeInTheDocument()
    expect(screen.queryByRole("status")).not.toBeInTheDocument()
  })
})
