import { useState, type ReactNode } from "react"
import {
  AlarmClock,
  ArrowRight,
  BookCheck,
  BookOpen,
  BookUp,
  CalendarCheck,
  CircleCheckBig,
  Copy,
  ScrollText,
  UserCheck,
  Users,
  type LucideIcon,
} from "lucide-react"
import { Link } from "react-router"

import { PageHeader } from "@/components/layout/page-header"
import { EmptyState } from "@/components/states/empty-state"
import { QueryState } from "@/components/states/query-state"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card } from "@/components/ui/card"
import { Skeleton } from "@/components/ui/skeleton"
import { ActivityItem } from "@/features/activity/activity-item"
import { useDashboard } from "@/features/dashboard/hooks"
import { BookLink } from "@/features/loans/book-link"
import { ReturnDialog } from "@/features/loans/return-dialog"
import { MemberLink } from "@/features/members/member-link"
import { useNow } from "@/hooks/use-now"
import { daysUntilDue } from "@/lib/dates"
import { formatCount, formatDueDate, formatDueIn, formatOverdue } from "@/lib/format"
import type { ActivityOut, DashboardCounts, LoanOut } from "@/lib/types"
import { cn } from "@/lib/utils"

type CountCard = {
  key: keyof DashboardCounts
  label: string
  hint: string
  to: string
  icon: LucideIcon
}

/** Each count links to the page where staff act on it. */
const countCards: readonly CountCard[] = [
  { key: "titles", label: "Titles", hint: "Books in the catalog", to: "/catalog", icon: BookOpen },
  { key: "copies", label: "Copies", hint: "Physical copies to lend", to: "/catalog", icon: Copy },
  { key: "available", label: "Available now", hint: "Copies ready to borrow", to: "/catalog", icon: BookCheck },
  { key: "on_loan", label: "On loan", hint: "Copies out with members", to: "/circulation", icon: BookUp },
  {
    key: "overdue",
    label: "Overdue",
    hint: "Loans past their due date",
    to: "/circulation?status=overdue",
    icon: AlarmClock,
  },
  { key: "members", label: "Members", hint: "People who can borrow", to: "/members", icon: Users },
  {
    key: "active_members_90d",
    label: "Active in 90 days",
    hint: "Members with a loan in the last 90 days",
    to: "/members",
    icon: UserCheck,
  },
]

const COUNT_GRID = "grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4"

/** The staff start page: the library in numbers, the loans that need attention, and the latest actions. */
export function DashboardPage() {
  const dashboard = useDashboard()
  const now = useNow(undefined, dashboard.dataUpdatedAt)
  // The dialog keeps its loan while closing, so the closing animation shows it.
  const [returning, setReturning] = useState<{ open: boolean; loan: LoanOut | null }>({
    open: false,
    loan: null,
  })
  const startReturn = (loan: LoanOut) => setReturning({ open: true, loan })

  return (
    <>
      <PageHeader title="Dashboard" description="The state of the library at a glance." />
      <QueryState
        query={dashboard}
        isEmpty={() => false}
        loading={<DashboardSkeleton />}
        errorTitle="Could not load the dashboard"
      >
        {(data) => (
          <div className="space-y-6">
            <CountCards counts={data.counts} />
            <div className="grid gap-6 lg:grid-cols-2">
              <LoanListSection
                id="overdue-heading"
                title="Overdue"
                description={
                  data.counts.overdue > 0
                    ? `${formatCount(data.counts.overdue)} in all, oldest due date first.`
                    : "Loans past their due date, oldest first."
                }
                loans={data.overdue}
                link={{ to: "/circulation?status=overdue", label: "All overdue loans" }}
                empty={
                  <EmptyState
                    icon={CircleCheckBig}
                    title="No overdue loans"
                    description="Good news: every copy on loan is within its due date."
                    className="border-0 bg-transparent py-8"
                  />
                }
                renderState={(loan) => (
                  <>
                    <Badge variant="overdue">{formatOverdue(loan.days_overdue)}</Badge>
                    <span>was due {formatDueDate(loan.due_at)}</span>
                  </>
                )}
                onReturn={startReturn}
              />
              <LoanListSection
                id="due-soon-heading"
                title="Due in the next 3 days"
                description="Soonest first."
                loans={data.due_soon}
                link={{ to: "/circulation", label: "All active loans" }}
                empty={
                  <EmptyState
                    icon={CalendarCheck}
                    title="Nothing due in the next 3 days"
                    description="No active loan comes due before then."
                    className="border-0 bg-transparent py-8"
                  />
                }
                renderState={(loan) => (
                  <>
                    <Badge variant="borrowed">{formatDueIn(daysUntilDue(loan.due_at, now))}</Badge>
                    <span>{formatDueDate(loan.due_at)}</span>
                  </>
                )}
                onReturn={startReturn}
              />
            </div>
            <RecentActivity events={data.recent_activity} now={now} />
          </div>
        )}
      </QueryState>
      <ReturnDialog
        loan={returning.loan}
        open={returning.open}
        onOpenChange={(open) => setReturning((current) => ({ ...current, open }))}
      />
    </>
  )
}

function CountCards({ counts }: { counts: DashboardCounts }) {
  return (
    <ul aria-label="Library counts" className={COUNT_GRID}>
      {countCards.map(({ key, label, hint, to, icon: Icon }) => {
        const alarming = key === "overdue" && counts.overdue > 0
        return (
          <li key={key} className="min-w-0">
            <Link
              to={to}
              className={cn(
                "flex h-full flex-col gap-1 rounded-xl border bg-card p-4 shadow-xs transition-colors outline-none hover:bg-accent/60 focus-visible:ring-3 focus-visible:ring-ring/50",
                alarming && "border-overdue/40 bg-overdue-surface/40",
              )}
            >
              <span className="flex items-start justify-between gap-2 text-sm font-medium text-muted-foreground">
                <span className="min-w-0">{label}</span>
                <Icon className="mt-0.5 size-4 shrink-0" aria-hidden />
              </span>
              <span
                className={cn(
                  "text-2xl font-semibold tracking-tight tabular-nums",
                  alarming && "text-overdue-foreground",
                )}
              >
                {formatCount(counts[key])}
              </span>
              <span className="text-xs text-muted-foreground">{hint}</span>
            </Link>
          </li>
        )
      })}
    </ul>
  )
}

type LoanListSectionProps = {
  id: string
  title: string
  description: string
  loans: LoanOut[]
  link: { to: string; label: string }
  empty: ReactNode
  /** The loan's due state, under its book, copy and member. */
  renderState: (loan: LoanOut) => ReactNode
  onReturn: (loan: LoanOut) => void
}

function LoanListSection({
  id,
  title,
  description,
  loans,
  link,
  empty,
  renderState,
  onReturn,
}: LoanListSectionProps) {
  return (
    <section aria-labelledby={id} className="min-w-0">
      <Card className="h-full gap-0 py-0">
        <SectionHeader id={id} title={title} description={description} link={link} />
        {loans.length === 0 ? (
          empty
        ) : (
          <ul className="divide-y border-t">
            {loans.map((loan) => (
              <li key={loan.id} className="flex items-start justify-between gap-3 px-4 py-3">
                <div className="min-w-0 space-y-1 text-sm">
                  <BookLink book={loan.book} />
                  <p className="truncate text-xs text-muted-foreground">
                    <span className="font-mono">{loan.copy.code}</span>
                    {" · "}
                    <MemberLink member={loan.member} className="text-foreground" />
                  </p>
                  <p className="flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-muted-foreground">
                    {renderState(loan)}
                  </p>
                </div>
                <Button
                  variant="outline"
                  size="sm"
                  aria-label={`Return ${loan.copy.code}`}
                  onClick={() => onReturn(loan)}
                >
                  Return
                </Button>
              </li>
            ))}
          </ul>
        )}
      </Card>
    </section>
  )
}

type SectionHeaderProps = {
  id: string
  title: string
  description: string
  link: { to: string; label: string }
}

function SectionHeader({ id, title, description, link }: SectionHeaderProps) {
  return (
    <div className="flex flex-wrap items-start justify-between gap-x-4 gap-y-2 px-4 py-4">
      <div className="min-w-0 space-y-1">
        <h2 id={id} className="leading-none font-semibold">
          {title}
        </h2>
        <p className="text-sm text-muted-foreground">{description}</p>
      </div>
      <Button asChild variant="ghost" size="sm" className="-mr-2">
        <Link to={link.to}>
          {link.label}
          <ArrowRight aria-hidden />
        </Link>
      </Button>
    </div>
  )
}

function RecentActivity({ events, now }: { events: ActivityOut[]; now: number }) {
  return (
    <section aria-labelledby="recent-activity-heading">
      <Card className="gap-0 py-0">
        <SectionHeader
          id="recent-activity-heading"
          title="Recent activity"
          description="The latest actions in the library."
          link={{ to: "/activity", label: "All activity" }}
        />
        {events.length === 0 ? (
          <EmptyState
            icon={ScrollText}
            title="No activity yet"
            description="Each borrow, return and catalog change will appear here."
            className="border-0 bg-transparent py-8"
          />
        ) : (
          <ol className="divide-y border-t" aria-label="Recent actions, newest first">
            {events.map((event) => (
              <ActivityItem key={event.id} event={event} now={now} />
            ))}
          </ol>
        )}
      </Card>
    </section>
  )
}

/** The dashboard's shape while it loads, so nothing jumps when the numbers arrive. */
function DashboardSkeleton() {
  return (
    <div role="status" className="space-y-6">
      <span className="sr-only">Loading the dashboard</span>
      <div className={COUNT_GRID}>
        {countCards.map(({ key }) => (
          <div key={key} className="space-y-2 rounded-xl border bg-card p-4">
            <Skeleton className="h-4 w-2/3" />
            <Skeleton className="h-7 w-1/2" />
            <Skeleton className="h-3 w-full" />
          </div>
        ))}
      </div>
      <div className="grid gap-6 lg:grid-cols-2">
        {[0, 1].map((panel) => (
          <div key={panel} className="space-y-4 rounded-xl border bg-card p-4">
            <Skeleton className="h-4 w-1/3" />
            {[0, 1, 2].map((row) => (
              <div key={row} className="space-y-2">
                <Skeleton className="h-4 w-3/4" />
                <Skeleton className="h-3 w-1/2" />
              </div>
            ))}
          </div>
        ))}
      </div>
    </div>
  )
}
