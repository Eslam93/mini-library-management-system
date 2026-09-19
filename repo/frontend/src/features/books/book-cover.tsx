import { useState } from "react"

import { cn } from "@/lib/utils"

/** Open Library's cover sizes: S for lists, M for a book's page. */
type CoverSize = "S" | "M"

const SIZE_CLASSES: Record<CoverSize, string> = {
  S: "w-8 text-sm",
  M: "w-24 text-3xl sm:w-28",
}

type BookCoverProps = {
  book: { title: string; isbn: string | null }
  size: CoverSize
  className?: string
}

/**
 * A book's cover from Open Library by its ISBN. The browser loads it only
 * when it comes into view and sends no referrer, so the cover service never
 * learns which page asked. `default=false` makes the service answer 404 for a
 * book it has no cover for, instead of a blank image; then, or without an
 * ISBN, a plain placeholder shows the title's first letter. The title is
 * always written beside the cover, so the image is decorative.
 */
export function BookCover({ book, size, className }: BookCoverProps) {
  const src = book.isbn
    ? `https://covers.openlibrary.org/b/isbn/${encodeURIComponent(book.isbn)}-${size}.jpg?default=false`
    : null
  // Remembers which address failed, so another book's cover gets its own try.
  const [failedSrc, setFailedSrc] = useState<string | null>(null)
  const frame = cn("aspect-2/3 shrink-0 overflow-hidden rounded-sm bg-muted", SIZE_CLASSES[size], className)

  if (src === null || src === failedSrc) {
    return (
      <div
        aria-hidden
        data-cover="placeholder"
        className={cn(frame, "flex items-center justify-center border font-semibold text-muted-foreground select-none")}
      >
        {initialOf(book.title)}
      </div>
    )
  }
  return (
    <img
      src={src}
      alt=""
      loading="lazy"
      decoding="async"
      referrerPolicy="no-referrer"
      onError={() => setFailedSrc(src)}
      className={cn(frame, "object-cover")}
    />
  )
}

function initialOf(title: string) {
  return (Array.from(title.trim())[0] ?? "").toLocaleUpperCase()
}
