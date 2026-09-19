/**
 * Reads what staff type or scan into the copy-code box. "CP-0012", "cp-12",
 * "cp 12" and "12" all mean CP-0012. Returns null for text that is not a
 * copy code, so the page can say so without asking the API.
 */
export function normalizeCopyCode(input: string): string | null {
  const match = /^(?:cp)?[\s-]*(\d+)$/i.exec(input.trim())
  if (!match) return null
  const number = match[1].replace(/^0+(?=\d)/, "")
  return `CP-${number.padStart(4, "0")}`
}
