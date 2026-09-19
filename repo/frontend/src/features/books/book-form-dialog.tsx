import { useState } from "react"
import { zodResolver } from "@hookform/resolvers/zod"
import { useForm } from "react-hook-form"
import { useNavigate } from "react-router"
import { toast } from "sonner"

import { Field } from "@/components/forms/field"
import { FormAlert } from "@/components/forms/form-alert"
import { PendingButton } from "@/components/forms/pending-button"
import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { Input } from "@/components/ui/input"
import { Textarea } from "@/components/ui/textarea"
import {
  BOOK_FORM_FIELDS,
  bookCreateSchema,
  bookFormFrom,
  changedBookFields,
  createBookBody,
  emptyBookForm,
  FIRST_PUBLISHED_YEAR,
  MAX_COPIES_PER_REQUEST,
  type BookFormOutput,
} from "@/features/books/book-schema"
import { useCreateBook, useIsbnLookup, useUpdateBook } from "@/features/books/hooks"
import { normalizeIsbn } from "@/features/books/isbn"
import { useDialogSession } from "@/hooks/use-dialog-session"
import { ApiError } from "@/lib/api"
import { applyServerErrors } from "@/lib/form-errors"
import { plural } from "@/lib/format"
import type { BookDetail } from "@/lib/types"

type BookFormDialogProps = {
  open: boolean
  onOpenChange: (open: boolean) => void
  /** The book to edit. Without it the dialog adds a new book. */
  book?: BookDetail
}

/** Adds a book, then opens its page; or edits one in place. */
export function BookFormDialog({ open, onOpenChange, book }: BookFormDialogProps) {
  const session = useDialogSession(open)
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <BookFormContent key={session} book={book} onClose={() => onOpenChange(false)} />
    </Dialog>
  )
}

type BookFormContentProps = {
  book?: BookDetail
  onClose: () => void
}

function BookFormContent({ book, onClose }: BookFormContentProps) {
  const navigate = useNavigate()
  const createBook = useCreateBook()
  const updateBook = useUpdateBook(book?.id ?? "")
  const isbnLookup = useIsbnLookup()
  const [formError, setFormError] = useState<string | null>(null)
  const [lookupNote, setLookupNote] = useState("")
  const {
    register,
    handleSubmit,
    setError,
    setValue,
    getValues,
    trigger,
    formState: { errors, isDirty, isSubmitting },
  } = useForm({
    resolver: zodResolver(bookCreateSchema),
    defaultValues: book ? bookFormFrom(book) : emptyBookForm(),
  })

  /**
   * Fills title, author and year from the ISBN. The category stays manual,
   * because the service's subjects are not the library's categories. Every
   * failure leaves the form as it was, to be filled in by hand.
   */
  async function lookUpIsbn() {
    setLookupNote("")
    const isbn = normalizeIsbn(getValues("isbn"))
    if (isbn === "") {
      setError("isbn", { type: "lookup", message: "Enter an ISBN to look it up." }, { shouldFocus: true })
      return
    }
    // The same checks as saving, so a typo is caught here and not sent.
    if (!(await trigger("isbn", { shouldFocus: true }))) return
    try {
      const found = await isbnLookup.mutateAsync(isbn)
      // The ISBN was changed while the answer was on its way: it belongs to another book.
      if (normalizeIsbn(getValues("isbn")) !== isbn) return
      const fill = { shouldDirty: true, shouldValidate: true }
      setValue("title", found.title, fill)
      setValue("author", found.author, fill)
      if (found.published_year !== null) setValue("published_year", String(found.published_year), fill)
      setLookupNote(`Found ${found.title} by ${found.author}. Check the details before adding the book.`)
    } catch (error) {
      if (error instanceof ApiError && error.status === 404) {
        setLookupNote("No book found for this ISBN. Fill in the details by hand.")
      } else if (error instanceof ApiError && error.status === 422) {
        setError("isbn", { type: "server", message: "This ISBN is not valid. Check it for a typo." }, { shouldFocus: true })
      } else {
        setLookupNote("The ISBN lookup service is unavailable right now. Fill in the details by hand.")
      }
    }
  }

  async function save(values: BookFormOutput) {
    setFormError(null)
    try {
      if (book) {
        const changes = changedBookFields(book, values)
        if (Object.keys(changes).length > 0) {
          const saved = await updateBook.mutateAsync(changes)
          toast.success(`Saved changes to ${saved.title}`)
        }
        onClose()
      } else {
        const created = await createBook.mutateAsync(createBookBody(values))
        toast.success(`Added ${created.title} with ${plural(created.copies_total, "copy", "copies")}`)
        onClose()
        navigate(`/books/${created.id}`)
      }
    } catch (error) {
      setFormError(
        applyServerErrors(error, setError, {
          fields: BOOK_FORM_FIELDS,
          codes: { isbn_taken: "isbn" },
        }),
      )
    }
  }

  return (
    <DialogContent
      className="sm:max-w-2xl"
      // A click beside the dialog should not throw away typed changes.
      onInteractOutside={(event) => {
        if (isDirty) event.preventDefault()
      }}
    >
      <DialogHeader>
        <DialogTitle>{book ? "Edit book" : "Add a book"}</DialogTitle>
        <DialogDescription>
          {book
            ? "Correct or update the book's details. Copies are managed on the book's page."
            : "Title and author are required. The book is added with its first copies."}
        </DialogDescription>
      </DialogHeader>

      <form noValidate onSubmit={handleSubmit(save)} className="grid gap-4">
        <FormAlert title={book ? "Could not save the book" : "Could not add the book"} message={formError} />

        <Field id="book-title" label="Title" error={errors.title?.message}>
          {(control) => <Input {...control} autoComplete="off" {...register("title")} />}
        </Field>
        <Field id="book-author" label="Author" error={errors.author?.message}>
          {(control) => <Input {...control} autoComplete="off" {...register("author")} />}
        </Field>

        <div className="grid gap-4 sm:grid-cols-2">
          <Field
            id="book-isbn"
            label="ISBN"
            optional
            error={errors.isbn?.message}
            hint="ISBN-10 or ISBN-13. Hyphens are fine."
          >
            {(control) => (
              <>
                <div className="flex gap-2">
                  <Input {...control} inputMode="text" autoComplete="off" {...register("isbn")} />
                  {!book && (
                    <PendingButton
                      type="button"
                      variant="outline"
                      pending={isbnLookup.isPending}
                      pendingLabel="Looking up…"
                      onClick={() => void lookUpIsbn()}
                    >
                      Look up
                    </PendingButton>
                  )}
                </div>
                {/* Always present, so screen readers announce what the lookup found; empty, it takes no space. */}
                {!book && (
                  <p role="status" className="text-sm text-muted-foreground empty:sr-only">
                    {lookupNote || null}
                  </p>
                )}
              </>
            )}
          </Field>
          <Field id="book-category" label="Category" optional error={errors.category?.message}>
            {(control) => <Input {...control} autoComplete="off" {...register("category")} />}
          </Field>
          <Field
            id="book-year"
            label="Year published"
            optional
            error={errors.published_year?.message}
            hint={`From ${FIRST_PUBLISHED_YEAR}.`}
          >
            {(control) => (
              <Input {...control} inputMode="numeric" autoComplete="off" {...register("published_year")} />
            )}
          </Field>
          {!book && (
            <Field
              id="book-copies"
              label="Copies"
              error={errors.copies?.message}
              hint={`How many physical copies to add now, 1 to ${MAX_COPIES_PER_REQUEST}.`}
            >
              {(control) => (
                <Input
                  {...control}
                  type="number"
                  min={1}
                  max={MAX_COPIES_PER_REQUEST}
                  {...register("copies")}
                />
              )}
            </Field>
          )}
        </div>

        <Field id="book-description" label="Description" optional error={errors.description?.message}>
          {(control) => <Textarea {...control} rows={3} {...register("description")} />}
        </Field>

        <DialogFooter>
          <DialogClose asChild>
            <Button type="button" variant="outline">
              Cancel
            </Button>
          </DialogClose>
          <PendingButton
            type="submit"
            pending={isSubmitting}
            pendingLabel={book ? "Saving…" : "Adding…"}
            disabled={Boolean(book) && !isDirty}
          >
            {book ? "Save changes" : "Add book"}
          </PendingButton>
        </DialogFooter>
      </form>
    </DialogContent>
  )
}
