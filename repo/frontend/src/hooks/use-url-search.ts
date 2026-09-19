import { useEffect, useRef, useState } from "react"
import { useSearchParams } from "react-router"

const SEARCH_DELAY_MS = 300

function updateParams(update: (params: URLSearchParams) => void) {
  return (previous: URLSearchParams) => {
    const next = new URLSearchParams(previous)
    update(next)
    return next
  }
}

/**
 * A list search bound to the URL: the "q" parameter holds the search and
 * "page" the page number. Typing shows in the box at once and reaches the URL
 * after a short pause; a new search starts again at page 1. Back and forward
 * in the browser bring the box along.
 */
export function useUrlSearch() {
  const [searchParams, setSearchParams] = useSearchParams()
  const q = searchParams.get("q") ?? ""
  const page = Math.max(1, Number.parseInt(searchParams.get("page") ?? "", 10) || 1)

  const [draft, setDraft] = useState(q)
  const [syncedQ, setSyncedQ] = useState(q)
  // The URL changed without typing, for example with the back button.
  if (q !== syncedQ) {
    setSyncedQ(q)
    setDraft(q)
  }

  const timer = useRef<ReturnType<typeof setTimeout>>(undefined)
  useEffect(() => () => clearTimeout(timer.current), [])

  function commit(value: string) {
    clearTimeout(timer.current)
    const next = value.trim()
    setSyncedQ(next)
    setSearchParams(
      updateParams((params) => {
        if (next) params.set("q", next)
        else params.delete("q")
        params.delete("page")
      }),
      { replace: true },
    )
  }

  function changeDraft(value: string) {
    setDraft(value)
    clearTimeout(timer.current)
    timer.current = setTimeout(() => commit(value), SEARCH_DELAY_MS)
  }

  function clear() {
    setDraft("")
    commit("")
  }

  function setPage(next: number) {
    setSearchParams(
      updateParams((params) => {
        if (next > 1) params.set("page", String(next))
        else params.delete("page")
      }),
    )
  }

  /**
   * Empties the search and removes other parameters, such as a list's filters,
   * in one step. Two separate URL updates in a row would each start from the
   * same URL, so the second would put back what the first removed.
   */
  function reset(otherKeys: readonly string[]) {
    clearTimeout(timer.current)
    setDraft("")
    setSyncedQ("")
    setSearchParams(
      updateParams((params) => {
        for (const key of ["q", "page", ...otherKeys]) params.delete(key)
      }),
    )
  }

  return { q, page, draft, changeDraft, clear, setPage, reset }
}
