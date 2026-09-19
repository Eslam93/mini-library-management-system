/**
 * The API contract as the frontend sees it. Field names match the JSON the
 * backend sends. Timestamps are ISO 8601 strings; `joined_on` and `due_date`
 * are calendar dates (YYYY-MM-DD).
 */

export type Role = "staff" | "member"

/** The signed-in person. A member user is linked to a member record through member_id. */
export type UserOut = {
  id: string
  display_name: string
  email: string | null
  role: Role
  member_id: string | null
  is_demo: boolean
}

/** Which sign-in methods the API offers. */
export type AuthConfigOut = {
  demo_login: boolean
  google: boolean
}

export type Page<T> = {
  items: T[]
  total: number
  limit: number
  offset: number
}

export type Availability = "available" | "all_borrowed" | "no_copies"

export type BookSummary = {
  id: string
  title: string
  author: string
  isbn: string | null
  category: string | null
  published_year: number | null
  copies_total: number
  copies_available: number
  availability: Availability
}

export type MemberRef = {
  id: string
  full_name: string
}

export type BookRef = {
  id: string
  title: string
  author: string
}

export type CopyRef = {
  id: string
  code: string
}

export type LoanBrief = {
  id: string
  member: MemberRef
  borrowed_at: string
  due_at: string
  is_overdue: boolean
}

export type CopyStatus = "available" | "borrowed"

export type CopyOut = {
  id: string
  code: string
  status: CopyStatus
  /** The active loan's due time. Every role sees it. */
  due_at: string | null
  /** Who has the copy. Always null for members, who never see another member's loans. */
  active_loan: LoanBrief | null
}

export type BookDetail = BookSummary & {
  description: string | null
  has_loan_history: boolean
  archived: boolean
  created_at: string
  updated_at: string
  copies: CopyOut[]
}

export type MemberOut = {
  id: string
  full_name: string
  email: string | null
  joined_on: string
  active_loans: number
}

/** One member's page: the list fields plus how many loans they have ever had. */
export type MemberDetailOut = MemberOut & {
  loans_total: number
}

export type LoanOut = {
  id: string
  copy: CopyRef
  book: BookRef
  member: MemberRef
  borrowed_at: string
  due_at: string
  returned_at: string | null
  is_overdue: boolean
  /** Whole days past the due date. 0 when the loan is not overdue. */
  days_overdue: number
}

/** A copy found by its code at the circulation desk, with its loan when it is out. */
export type CopyLookupOut = {
  copy: CopyRef
  book: BookRef
  status: CopyStatus
  /** The copy or its book is archived, so it cannot be borrowed. */
  archived: boolean
  active_loan: LoanOut | null
}

export type DashboardCounts = {
  titles: number
  copies: number
  available: number
  on_loan: number
  overdue: number
  members: number
  active_members_90d: number
}

/** The staff start page: counts, the loans that need attention, and the latest actions. */
export type DashboardOut = {
  counts: DashboardCounts
  /** At most 8, oldest due date first. */
  overdue: LoanOut[]
  /** Due in the next 3 days and not overdue, soonest first, at most 8. */
  due_soon: LoanOut[]
  recent_activity: ActivityOut[]
}

export type ActivityVia = "ui" | "copilot" | "system"

export type ActivityOut = {
  id: number
  occurred_at: string
  action: string
  entity_type: string
  entity_id: string | null
  summary: string
  via: ActivityVia
  actor: string | null
}

// Request bodies.

export type BookCreate = {
  title: string
  author: string
  isbn?: string | null
  category?: string | null
  published_year?: number | null
  description?: string | null
  copies?: number
}

export type BookUpdate = Partial<Omit<BookCreate, "copies">>

export type DeleteBookResult = {
  outcome: "deleted" | "archived"
}

export type MemberCreate = {
  full_name: string
  email?: string | null
}

export type LoanCreate = {
  copy_id: string
  member_id: string
  due_date?: string
}

export type DemoSignIn = {
  role: Role
}

export type LoanStatus = "active" | "returned"

/** The signed-in member's loans: active ones due soonest first, returned ones newest first. */
export type MyLoansParams = {
  status: LoanStatus
  limit?: number
  offset?: number
}

/** The staff loans list: overdue is the active loans past their due date. */
export type LoanListStatus = "active" | "overdue" | "returned" | "all"

/**
 * Filters for GET /api/loans. q matches the book's title or author, the
 * member's name, or the copy code. Active and overdue loans come due date
 * first, returned ones most recently returned first, all newest borrowed first.
 */
export type LoansParams = {
  status: LoanListStatus
  q?: string
  member_id?: string
  book_id?: string
  limit?: number
  offset?: number
}

/** Paging and search parameters shared by the list endpoints. */
export type ListParams = {
  q?: string
  limit?: number
  offset?: number
}

/**
 * The catalog's orders: by title (the default), by author, newest publication
 * year first, or most recently added to the library first.
 */
export type BookSort = "title" | "author" | "year_desc" | "recent"

/** GET /api/books: the list parameters plus the catalog's filters and order. */
export type BooksParams = ListParams & {
  /** A whole category name; letter case does not matter. */
  category?: string
  /** Only books with at least one copy that is not on loan. */
  available_only?: boolean
  sort?: BookSort
}

/** What GET /api/isbn/{isbn} found. The year is null when the service does not know it. */
export type IsbnLookupOut = {
  isbn: string
  title: string
  author: string
  published_year: number | null
}
