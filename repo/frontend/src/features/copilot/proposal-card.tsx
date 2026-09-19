import type { ReactNode } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { Check, CircleAlert, CircleCheck, HandHelping, Undo2, type LucideIcon } from "lucide-react"

import { PendingButton } from "@/components/forms/pending-button"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { cancelProposal, confirmProposal, copilotKeys, fetchProposal } from "@/features/copilot/api"
import { BookTitleLink } from "@/features/copilot/book-title-link"
import {
  PROPOSAL_ERROR_CODES,
  type ProposalAction,
  type ProposalOut,
  type ProposalStatus,
} from "@/features/copilot/types"
import { refreshAfterLoanChange } from "@/features/loans/hooks"
import { MemberLink } from "@/features/members/member-link"
import { useNow } from "@/hooks/use-now"
import { ApiError } from "@/lib/api"
import { formatDate, formatDueDate, formatRelative } from "@/lib/format"

/** How often the card reads the clock, so a pending card shows expired soon after its time. */
const CLOCK_TICK_MS = 15_000

const ACTIONS: Record<ProposalAction, { label: string; icon: LucideIcon; failed: string }> = {
  borrow: { label: "Borrow", icon: HandHelping, failed: "Could not borrow" },
  return: { label: "Return", icon: Undo2, failed: "Could not return" },
}

/** A pending proposal past its expiry shows as expired, whether or not the server has recorded it yet. */
function shownStatus(proposal: ProposalOut, now: number): ProposalStatus {
  if (proposal.status === "pending" && Date.parse(proposal.expires_at) <= now) return "expired"
  return proposal.status
}

/** The message for a failed confirm or cancel that leaves the proposal pending. A 409 settles the card instead. */
function problemMessage(error: Error | null): string | null {
  if (!error) return null
  if (error instanceof ApiError) return error.status === 409 ? null : error.message
  return "Something went wrong. Try again."
}

type ProposalCardProps = {
  /** The proposal as its display brought it. The card starts from it. */
  proposal: ProposalOut
  /** A link in the card leads to a page: the panel closes. */
  onNavigate: () => void
}

/**
 * A Borrow or Return the Copilot prepared: what will happen, to which copy
 * and member, with Confirm and Cancel while it waits. Nothing changes until
 * Confirm. The card's state lives in the query cache under the proposal's id,
 * so it survives the panel closing and a change of page.
 */
export function ProposalCard({ proposal: seed, onNavigate }: ProposalCardProps) {
  const queryClient = useQueryClient()
  const now = useNow(CLOCK_TICK_MS)
  const queryKey = copilotKeys.proposal(seed.id)

  const {
    data: proposal,
    error: readError,
    isFetching,
    refetch,
  } = useQuery({
    queryKey,
    queryFn: ({ signal }) => fetchProposal(seed.id, signal),
    initialData: seed,
    // The chat puts a proposal in the cache the moment it arrives, so data
    // dated 0 is a card restored from storage. The proposal may have been
    // confirmed or cancelled since, so that card reads it once on mount.
    // After that, only this card's own actions change it.
    initialDataUpdatedAt: 0,
    staleTime: Infinity,
    refetchOnMount: (query) => (query.state.dataUpdatedAt === 0 ? "always" : false),
    enabled: (query) => shownStatus(query.state.data ?? seed, now) === "pending",
  })

  const update = (change: Partial<ProposalOut>) =>
    queryClient.setQueryData<ProposalOut>(queryKey, (current) => ({ ...(current ?? seed), ...change }))

  // A 409 means the proposal can no longer go ahead, and the card shows why.
  // Any other failure, such as a lost connection, leaves it pending to try again.
  const settleConflict = (error: Error) => {
    if (!(error instanceof ApiError) || error.status !== 409) return
    if (error.code === PROPOSAL_ERROR_CODES.expired) {
      update({ status: "expired" })
    } else if (error.code === PROPOSAL_ERROR_CODES.resolved) {
      // Confirmed or cancelled somewhere else, such as another tab: show how it ended.
      void refetch()
    } else {
      // The Borrow or Return itself was refused: the server marked the proposal
      // failed and changed nothing. The refusal means the pages showed an old
      // state of the copy or the loan, so they load again.
      update({ status: "failed", error: { code: error.code, message: error.message } })
      refreshAfterLoanChange(queryClient, seed.book.id)
    }
  }

  const confirm = useMutation({
    mutationFn: () => confirmProposal(seed.id),
    onSuccess: (confirmed) => {
      queryClient.setQueryData(queryKey, confirmed)
      refreshAfterLoanChange(queryClient, confirmed.book.id)
    },
    onError: settleConflict,
  })
  const cancel = useMutation({
    mutationFn: () => cancelProposal(seed.id),
    onSuccess: () => update({ status: "cancelled" }),
    onError: settleConflict,
  })

  const status = shownStatus(proposal, now)
  const action = ACTIONS[proposal.action]
  const Icon = action.icon
  const dueAt = proposal.loan?.due_at ?? proposal.due_at
  const busy = confirm.isPending || cancel.isPending || isFetching
  const problem = problemMessage(confirm.error) ?? problemMessage(cancel.error) ?? problemMessage(readError)

  let outcome: ReactNode
  switch (status) {
    case "pending":
      outcome = (
        <div className="space-y-2">
          <p className="text-xs text-muted-foreground">
            Nothing changes until you confirm. Expires {formatRelative(proposal.expires_at, now)}.
          </p>
          {problem && (
            <p role="alert" className="text-sm text-destructive">
              {problem}
            </p>
          )}
          <div className="flex flex-wrap gap-2">
            <PendingButton
              size="sm"
              pending={confirm.isPending}
              pendingLabel="Confirming…"
              disabled={busy}
              onClick={() => confirm.mutate()}
            >
              <Check aria-hidden />
              Confirm
            </PendingButton>
            <Button size="sm" variant="outline" disabled={busy} onClick={() => cancel.mutate()}>
              Cancel
            </Button>
          </div>
        </div>
      )
      break
    case "confirmed":
      outcome = (
        <p role="status" className="flex items-center gap-2 text-sm font-medium text-available-foreground">
          <CircleCheck aria-hidden className="size-4 shrink-0" />
          {proposal.action === "borrow" ? `Borrowed, due ${formatDueDate(dueAt)}` : "Returned"}
        </p>
      )
      break
    case "failed":
      outcome = (
        <div role="alert" className="space-y-1 text-sm">
          <p className="flex items-center gap-2 font-medium text-destructive">
            <CircleAlert aria-hidden className="size-4 shrink-0" />
            {action.failed}
          </p>
          <p className="text-muted-foreground">
            {proposal.error?.message ?? "The server refused it."} Nothing changed.
          </p>
        </div>
      )
      break
    case "cancelled":
      outcome = <p className="text-sm text-muted-foreground">Cancelled. Nothing changed.</p>
      break
    case "expired":
      outcome = (
        <p className="text-sm text-muted-foreground">
          This proposal expired, so nothing changed. Ask again to make a new one.
        </p>
      )
      break
  }

  return (
    <article
      aria-label={`Proposed ${action.label.toLowerCase()}`}
      aria-busy={busy || undefined}
      className="rounded-lg border bg-card p-3 shadow-xs"
    >
      <p className="flex items-center gap-1.5 text-xs font-medium text-muted-foreground">
        <Icon aria-hidden className="size-3.5" />
        {action.label}
      </p>
      <div className="mt-1">
        <BookTitleLink book={proposal.book} onNavigate={onNavigate} />
        <p className="text-xs text-muted-foreground">{proposal.book.author}</p>
      </div>
      <dl className="mt-3 space-y-1.5 text-sm">
        <Detail term="Copy">
          <span className="font-mono text-xs font-medium">{proposal.copy.code}</span>
        </Detail>
        <Detail term="Member">
          <MemberLink member={proposal.member} onClick={onNavigate} className="font-medium" />
        </Detail>
        {proposal.borrowed_at && <Detail term="Borrowed">{formatDate(proposal.borrowed_at)}</Detail>}
        <Detail term="Due">
          {formatDueDate(dueAt)}
          {proposal.is_overdue && <Badge variant="overdue">Overdue</Badge>}
        </Detail>
      </dl>
      <div className="mt-3 border-t pt-3">{outcome}</div>
    </article>
  )
}

function Detail({ term, children }: { term: string; children: ReactNode }) {
  return (
    <div className="grid grid-cols-[5rem_1fr] items-baseline gap-2">
      <dt className="text-xs text-muted-foreground">{term}</dt>
      <dd className="flex flex-wrap items-center gap-2">{children}</dd>
    </div>
  )
}
