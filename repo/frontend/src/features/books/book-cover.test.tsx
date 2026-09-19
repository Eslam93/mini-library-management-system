import { fireEvent, render } from "@testing-library/react"
import { describe, expect, it } from "vitest"

import { BookCover } from "@/features/books/book-cover"

const dune = { title: "Dune", isbn: "9780441172719" }

describe("BookCover", () => {
  it("loads the cover for the ISBN lazily, without a referrer, and asks for a 404 when there is none", () => {
    const { container } = render(<BookCover book={dune} size="S" />)

    const image = container.querySelector("img")
    expect(image).toHaveAttribute(
      "src",
      "https://covers.openlibrary.org/b/isbn/9780441172719-S.jpg?default=false",
    )
    expect(image).toHaveAttribute("loading", "lazy")
    expect(image).toHaveAttribute("referrerpolicy", "no-referrer")
    // The title is written beside every cover, so the image adds nothing for screen readers.
    expect(image).toHaveAttribute("alt", "")
  })

  it("asks for the medium size on a book's page", () => {
    const { container } = render(<BookCover book={dune} size="M" />)

    expect(container.querySelector("img")?.getAttribute("src")).toContain("/9780441172719-M.jpg")
  })

  it("shows the title's first letter when the book has no ISBN", () => {
    const { container } = render(<BookCover book={{ title: " the hobbit", isbn: null }} size="S" />)

    expect(container.querySelector("img")).toBeNull()
    const placeholder = container.querySelector("[data-cover='placeholder']")
    expect(placeholder).toHaveTextContent("T")
    expect(placeholder).toHaveAttribute("aria-hidden", "true")
  })

  it("falls back to the first letter when the cover cannot be loaded, and tries again for another book", () => {
    const { container, rerender } = render(<BookCover book={dune} size="S" />)

    fireEvent.error(container.querySelector("img") as HTMLImageElement)

    expect(container.querySelector("img")).toBeNull()
    expect(container.querySelector("[data-cover='placeholder']")).toHaveTextContent("D")

    rerender(<BookCover book={{ title: "Emma", isbn: "9780141439587" }} size="S" />)

    expect(container.querySelector("img")?.getAttribute("src")).toContain("/9780141439587-S.jpg")
  })
})
