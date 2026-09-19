import { describe, expect, it, vi } from "vitest"

import { ApiError } from "@/lib/api"
import { applyServerErrors } from "@/lib/form-errors"

type Values = { title: string; member: string }

function validationError(errors: unknown[]) {
  return new ApiError({
    status: 422,
    code: "validation_failed",
    message: "The request is not valid.",
    details: { errors },
  })
}

describe("applyServerErrors", () => {
  it("puts body errors on their fields, renamed where needed, and focuses the first", () => {
    const setError = vi.fn()

    const message = applyServerErrors<Values>(
      validationError([
        { location: ["body", "title"], message: "Field required", type: "missing" },
        { location: ["body", "member_id"], message: "Value error, Unknown member.", type: "value_error" },
      ]),
      setError,
      { fields: { title: "title", member_id: "member" } },
    )

    expect(message).toBeNull()
    expect(setError).toHaveBeenNthCalledWith(
      1,
      "title",
      { type: "server", message: "Field required" },
      { shouldFocus: true },
    )
    expect(setError).toHaveBeenNthCalledWith(
      2,
      "member",
      { type: "server", message: "Unknown member." },
      { shouldFocus: false },
    )
  })

  it("returns what has no field as a form-level message", () => {
    const setError = vi.fn()

    const message = applyServerErrors<Values>(
      validationError([{ location: ["query", "limit"], message: "Too large", type: "le" }]),
      setError,
      { fields: { title: "title" } },
    )

    expect(message).toBe("Too large")
    expect(setError).not.toHaveBeenCalled()
  })

  it("puts a known conflict code on its field and shows other errors as sent", () => {
    const setError = vi.fn()
    const conflict = new ApiError({ status: 409, code: "isbn_taken", message: "ISBN in use." })
    const outage = new ApiError({ status: 503, code: "unavailable", message: "Try later." })

    expect(applyServerErrors(conflict, setError, { fields: {}, codes: { isbn_taken: "title" } })).toBeNull()
    expect(setError).toHaveBeenCalledWith("title", { type: "server", message: "ISBN in use." }, { shouldFocus: true })
    expect(applyServerErrors(outage, setError, { fields: {} })).toBe("Try later.")
    expect(applyServerErrors(new Error("boom"), setError, { fields: {} })).toBe(
      "Something went wrong. Try again.",
    )
  })
})
