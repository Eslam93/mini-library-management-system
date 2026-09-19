import {
  ArrowDownLeft,
  ArrowUpRight,
  Archive,
  BookOpen,
  Copy,
  ScrollText,
  Sparkles,
  Trash2,
  UserPlus,
  type LucideIcon,
} from "lucide-react"

import { Badge } from "@/components/ui/badge"
import { formatDateTime, formatRelative } from "@/lib/format"
import type { ActivityOut } from "@/lib/types"

const actionIcons: Partial<Record<string, LucideIcon>> = {
  "book.created": BookOpen,
  "book.updated": BookOpen,
  "book.archived": Archive,
  "book.deleted": Trash2,
  "copy.added": Copy,
  "member.created": UserPlus,
  "loan.borrowed": ArrowUpRight,
  "loan.returned": ArrowDownLeft,
}

/** One action: what happened, when, who did it, and whether through the Copilot. */
export function ActivityItem({ event, now }: { event: ActivityOut; now: number }) {
  const Icon = actionIcons[event.action] ?? ScrollText

  return (
    <li className="flex items-start gap-3 px-4 py-3">
      <span className="mt-0.5 flex size-7 shrink-0 items-center justify-center rounded-full bg-muted text-muted-foreground">
        <Icon className="size-3.5" aria-hidden />
      </span>
      <div className="min-w-0 flex-1 space-y-1">
        <p className="text-sm">{event.summary}</p>
        <div className="flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-muted-foreground">
          <time dateTime={event.occurred_at} title={formatDateTime(event.occurred_at)}>
            {formatRelative(event.occurred_at, now)}
          </time>
          {event.actor && <span>by {event.actor}</span>}
          {event.via === "copilot" && (
            <Badge variant="secondary">
              <Sparkles aria-hidden />
              Copilot
            </Badge>
          )}
        </div>
      </div>
    </li>
  )
}
