import { render, screen } from "@testing-library/react"
import { describe, expect, it } from "vitest"

import { RichText } from "@/features/copilot/rich-text"

describe("RichText", () => {
  it("renders paragraphs, lists and bold text", () => {
    const { container } = render(
      <RichText
        text={"I found **two** books.\n\n- Dune\n- Hyperion\n\n1. Search\n2. Borrow at the desk\n\nThat is all."}
      />,
    )

    expect(container.querySelectorAll("p")).toHaveLength(2)
    expect(screen.getByText("two").tagName).toBe("STRONG")
    const [bullets, steps] = screen.getAllByRole("list")
    expect(bullets.tagName).toBe("UL")
    expect(steps.tagName).toBe("OL")
    expect(screen.getAllByRole("listitem").map((item) => item.textContent)).toEqual([
      "Dune",
      "Hyperion",
      "Search",
      "Borrow at the desk",
    ])
  })

  it("renders *italic* titles, and leaves a lone asterisk as it is", () => {
    const { container } = render(
      <RichText text={"The loan of *The Hobbit* for **Maya Hassan** is ready. 2 * 3 stays."} />,
    )

    expect(screen.getByText("The Hobbit").tagName).toBe("EM")
    expect(screen.getByText("Maya Hassan").tagName).toBe("STRONG")
    expect(container).toHaveTextContent("The loan of The Hobbit for Maya Hassan is ready. 2 * 3 stays.")
  })

  it("renders bold italic, and italic inside bold, without stray asterisks", () => {
    const { container } = render(
      <RichText text={"***Dune*** is in.\n\n***The Hobbit* by J.R.R. Tolkien** is out."} />,
    )

    const dune = screen.getByText("Dune")
    expect(dune.tagName).toBe("EM")
    expect(dune.parentElement?.tagName).toBe("STRONG")
    const hobbit = screen.getByText("The Hobbit")
    expect(hobbit.tagName).toBe("EM")
    expect(hobbit.parentElement?.tagName).toBe("STRONG")
    expect(container.textContent).not.toContain("*")
  })

  it("shows markup as plain text instead of reading it as HTML", () => {
    const { container } = render(<RichText text={'<img src=x onerror="alert(1)"> <b>bold</b>'} />)

    expect(container.querySelector("img")).toBeNull()
    expect(container.querySelector("b")).toBeNull()
    expect(container).toHaveTextContent('<img src=x onerror="alert(1)"> <b>bold</b>')
  })
})
