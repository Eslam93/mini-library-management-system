/**
 * ISBN rules, the same as the API's: spaces and hyphens are dropped, a final
 * "x" becomes "X", and the result must be a valid ISBN-10 or ISBN-13.
 */

export function normalizeIsbn(value: string): string {
  return value.replace(/[\s-]/g, "").toUpperCase()
}

/** True when a normalized value has the shape of an ISBN-10 or ISBN-13. */
export function hasIsbnShape(isbn: string): boolean {
  return /^\d{9}[\dX]$/.test(isbn) || /^\d{13}$/.test(isbn)
}

/** True when a normalized ISBN-10 or ISBN-13 has a correct check digit. */
export function hasValidIsbnChecksum(isbn: string): boolean {
  const digits = [...isbn].map((char) => (char === "X" ? 10 : Number(char)))
  if (/^\d{9}[\dX]$/.test(isbn)) {
    // Weights 10 down to 1; the sum is a multiple of 11.
    return digits.reduce((sum, digit, index) => sum + digit * (10 - index), 0) % 11 === 0
  }
  if (/^\d{13}$/.test(isbn)) {
    // Weights alternate 1 and 3; the sum is a multiple of 10.
    return digits.reduce((sum, digit, index) => sum + digit * (index % 2 ? 3 : 1), 0) % 10 === 0
  }
  return false
}
