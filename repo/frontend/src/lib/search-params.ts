/** Appends the defined, non-empty values as a query string: withSearchParams("/api/books", { q: "dune" }). */
export function withSearchParams(
  path: string,
  params: Record<string, string | number | boolean | undefined>,
): string {
  const search = new URLSearchParams()
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== "") search.set(key, String(value))
  }
  const query = search.toString()
  return query ? `${path}?${query}` : path
}
