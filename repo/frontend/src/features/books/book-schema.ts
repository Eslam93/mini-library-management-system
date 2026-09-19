import { z } from "zod"

import { hasIsbnShape, hasValidIsbnChecksum, normalizeIsbn } from "@/features/books/isbn"
import type { BookCreate, BookDetail, BookUpdate } from "@/lib/types"

/** The oldest year the API accepts: printing with movable type in Europe. */
export const FIRST_PUBLISHED_YEAR = 1450
export const MAX_COPIES_PER_REQUEST = 20

export function lastPublishedYear() {
  return new Date().getFullYear() + 1
}

/** Trims a text field and turns an empty one into null. */
const optionalText = z
  .string()
  .trim()
  .transform((value) => value || null)

const isbn = z
  .string()
  .transform(normalizeIsbn)
  .superRefine((value, ctx) => {
    if (value === "") return
    if (!hasIsbnShape(value)) {
      ctx.addIssue({
        code: "custom",
        message: "Enter 10 or 13 digits. An ISBN-10 may end in X.",
      })
    } else if (!hasValidIsbnChecksum(value)) {
      ctx.addIssue({
        code: "custom",
        message: "This ISBN's check digit does not match. Check it for a typo.",
      })
    }
  })
  .transform((value) => value || null)

const publishedYear = z
  .string()
  .trim()
  .superRefine((value, ctx) => {
    if (value === "") return
    const year = Number(value)
    const last = lastPublishedYear()
    if (!/^\d+$/.test(value) || year < FIRST_PUBLISHED_YEAR || year > last) {
      ctx.addIssue({
        code: "custom",
        message: `Enter a year from ${FIRST_PUBLISHED_YEAR} to ${last}.`,
      })
    }
  })
  .transform((value) => (value === "" ? null : Number(value)))

export const bookEditSchema = z.object({
  title: z.string().trim().min(1, "Enter the title."),
  author: z.string().trim().min(1, "Enter the author."),
  isbn,
  category: optionalText,
  published_year: publishedYear,
  description: optionalText,
})

export const copyCountSchema = z
  .string()
  .trim()
  .refine(
    (value) => /^\d+$/.test(value) && Number(value) >= 1 && Number(value) <= MAX_COPIES_PER_REQUEST,
    `Enter a number from 1 to ${MAX_COPIES_PER_REQUEST}.`,
  )
  .transform(Number)

export const bookCreateSchema = bookEditSchema.extend({ copies: copyCountSchema })

/**
 * What the form holds: every field is the text of its input. The edit form
 * uses the same shape and leaves `copies` at its valid default, unshown.
 */
export type BookFormValues = z.input<typeof bookCreateSchema>
export type BookFormOutput = z.output<typeof bookCreateSchema>
export type BookFields = z.output<typeof bookEditSchema>

/** The form fields that can show an API validation error, by API field name. */
export const BOOK_FORM_FIELDS = {
  title: "title",
  author: "author",
  isbn: "isbn",
  category: "category",
  published_year: "published_year",
  description: "description",
  copies: "copies",
} as const satisfies Record<string, keyof BookFormValues>

export function emptyBookForm(): BookFormValues {
  return {
    title: "",
    author: "",
    isbn: "",
    category: "",
    published_year: "",
    description: "",
    copies: "1",
  }
}

export function bookFormFrom(book: BookDetail): BookFormValues {
  return {
    title: book.title,
    author: book.author,
    isbn: book.isbn ?? "",
    category: book.category ?? "",
    published_year: book.published_year === null ? "" : String(book.published_year),
    description: book.description ?? "",
    copies: "1",
  }
}

const BOOK_FIELD_NAMES = [
  "title",
  "author",
  "isbn",
  "category",
  "published_year",
  "description",
] as const satisfies readonly (keyof BookFields)[]

/** The create request: empty optional fields are left out. */
export function createBookBody({ copies, ...fields }: BookFormOutput): BookCreate {
  const body: BookCreate = { title: fields.title, author: fields.author, copies }
  for (const key of BOOK_FIELD_NAMES) {
    if (fields[key] !== null) Object.assign(body, { [key]: fields[key] })
  }
  return body
}

/** Only the fields that differ from the stored book, so an edit sends what the user changed. */
export function changedBookFields(book: BookDetail, values: BookFields): BookUpdate {
  const changes: BookUpdate = {}
  for (const key of BOOK_FIELD_NAMES) {
    if (values[key] !== book[key]) Object.assign(changes, { [key]: values[key] })
  }
  return changes
}
