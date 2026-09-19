import type { FieldValues, Path, UseFormSetError } from "react-hook-form"

import { ApiError } from "@/lib/api"

type ServerIssue = {
  location: unknown[]
  message: string
}

/** Reads the `errors` list of a 422 response, skipping anything malformed. */
function serverIssues(details: unknown): ServerIssue[] {
  if (typeof details !== "object" || details === null || !("errors" in details)) return []
  const { errors } = details as { errors: unknown }
  if (!Array.isArray(errors)) return []
  return errors.filter(
    (issue): issue is ServerIssue =>
      typeof issue === "object" &&
      issue !== null &&
      Array.isArray((issue as ServerIssue).location) &&
      typeof (issue as ServerIssue).message === "string",
  )
}

/** Custom validators on the server prefix their message with "Value error, ". */
function readableMessage(message: string) {
  return message.replace(/^Value error, /, "")
}

type ServerErrorTargets<T extends FieldValues> = {
  /** Form fields that can show a validation error, keyed by the API field name. */
  fields: Partial<Record<string, Path<T>>>
  /** Error codes that belong to one field, such as `isbn_taken` on the ISBN. */
  codes?: Partial<Record<string, Path<T>>>
}

/**
 * Shows a failed request on the form. Validation errors and known conflicts go
 * on their fields; everything else comes back as one form-level message.
 * Returns that message, or null when every error found its field.
 */
export function applyServerErrors<T extends FieldValues>(
  error: unknown,
  setError: UseFormSetError<T>,
  { fields, codes = {} }: ServerErrorTargets<T>,
): string | null {
  if (!(error instanceof ApiError)) return "Something went wrong. Try again."

  const codeField = codes[error.code]
  if (codeField) {
    setError(codeField, { type: "server", message: error.message }, { shouldFocus: true })
    return null
  }
  if (error.status !== 422) return error.message

  const unplaced: string[] = []
  let placed = 0
  for (const issue of serverIssues(error.details)) {
    const [source, name] = issue.location
    const field = source === "body" && typeof name === "string" ? fields[name] : undefined
    const message = readableMessage(issue.message)
    if (field) {
      setError(field, { type: "server", message }, { shouldFocus: placed === 0 })
      placed += 1
    } else {
      unplaced.push(message)
    }
  }
  if (unplaced.length > 0) return unplaced.join(" ")
  return placed > 0 ? null : error.message
}
