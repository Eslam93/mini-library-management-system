/**
 * The Copilot's API contract as the frontend sees it: the config, the chat
 * request, the server-sent events of one turn, and the proposals staff
 * confirm. Field names match the JSON the backend sends.
 */

import type {
  BookDetail,
  BookRef,
  BookSummary,
  CopyLookupOut,
  CopyRef,
  LoanOut,
  MemberOut,
  MemberRef,
} from "@/lib/types"

/** Which assistant the signed-in user gets. The role decides it. */
export type CopilotFace = "member" | "staff"

export type CopilotConfig = {
  /** False when the server has no model configured; `reason` then says why. */
  available: boolean
  face: CopilotFace
  reason: string | null
  /** Prompts suited to the face, offered as chips before the first message. */
  examples: string[]
}

export type CopilotChatRequest = {
  /** Leave out to start a new conversation. */
  conversation_id?: string
  message: string
}

export type ProposalAction = "borrow" | "return"

export type ProposalStatus = "pending" | "confirmed" | "cancelled" | "failed" | "expired"

/**
 * A Borrow or Return the Copilot prepared and the staff user confirms or
 * cancels. Nothing changes until it is confirmed. A pending proposal counts
 * as expired once `expires_at` has passed, even before the server records it.
 */
export type ProposalOut = {
  id: string
  action: ProposalAction
  status: ProposalStatus
  book: BookRef
  copy: CopyRef
  member: MemberRef
  /** A borrow: the due time the loan will get. A return: the loan's due time. */
  due_at: string
  /** A return only. */
  borrowed_at: string | null
  /** A return only; always false for a borrow. */
  is_overdue: boolean
  created_at: string
  expires_at: string
  resolved_at: string | null
  /** After a confirm: the new loan, or the returned one. */
  loan: LoanOut | null
  /** Why a confirm failed. */
  error: { code: string; message: string } | null
}

/** Error codes of a confirm or cancel the server refused because of the proposal's state. */
export const PROPOSAL_ERROR_CODES = {
  expired: "proposal_expired",
  resolved: "proposal_resolved",
} as const

/**
 * How the panel writes a table cell. "points" is a change between two
 * percentages ("+8.2 pts"); "change_percent" is a relative change ("+12.5%").
 */
export type TableColumnFormat = "text" | "count" | "percent" | "points" | "change_percent" | "days"

export type TableColumn = {
  /** The key of this column's value in each row and in the total. */
  key: string
  label: string
  format: TableColumnFormat
}

/** Text for labels, or a raw number the panel formats. null means there is no value, such as a rate with nothing to measure. */
export type TableCell = string | number | null

export type TableRow = Record<string, TableCell>

/** A range shaded between two columns, such as a forecast's likely range. */
export type TableChartBand = {
  /** The column with the bottom of the range in each row. */
  low: string
  /** The column with the top of the range in each row. */
  high: string
  label: string
}

/** The chart the server chose for a table. Its keys are column keys. */
export type TableChart = {
  type: "bar" | "line"
  /** The column that names each bar or point. */
  x: string
  /**
   * One set of bars or one line each: the current values, then the previous
   * ones with a comparison. With a band, the first line is what was measured
   * and the lines after it are projections, such as a forecast.
   */
  series: { key: string; label: string }[]
  /** Line charts only: a range shaded under the lines. */
  band?: TableChartBand | null
}

/** Figures the analyst measured, as a table with an optional chart. */
export type TableDisplay = {
  kind: "table"
  title: string
  /** The period, or "Now", and the comparison when there is one. */
  subtitle: string
  columns: TableColumn[]
  rows: TableRow[]
  /** The figure over the whole scope, measured by the server, never a sum of the rows. */
  total: TableRow | null
  chart: TableChart | null
}

/** What a tool found, shown with the product's own components. */
export type CopilotDisplay =
  | { kind: "books"; items: BookSummary[] }
  | { kind: "book"; book: BookDetail }
  | { kind: "loans"; items: LoanOut[] }
  | { kind: "categories"; items: string[] }
  | { kind: "members"; items: MemberOut[] }
  | { kind: "copy"; lookup: CopyLookupOut }
  | { kind: "proposal"; proposal: ProposalOut }
  | TableDisplay

/** Error codes the server sends in an `error` event or a refusal before the stream. */
export const COPILOT_ERROR_CODES = {
  unavailable: "copilot_unavailable",
  timeout: "copilot_timeout",
  rateLimited: "copilot_rate_limited",
  failed: "copilot_failed",
} as const

/** One turn's events, in the order the server usually sends them. */
export type CopilotEvent =
  | { event: "conversation"; data: { conversation_id: string } }
  | { event: "status"; data: { text: string } }
  | { event: "result"; data: { tool: string; display: CopilotDisplay } }
  | { event: "message"; data: { text: string } }
  | { event: "error"; data: { code: string; message: string } }
  | { event: "done"; data: Record<string, never> }

export type CopilotEventName = CopilotEvent["event"]
