import { ScrollText } from "lucide-react"

import { PageHeader } from "@/components/layout/page-header"
import { EmptyState } from "@/components/states/empty-state"
import { LoadingState } from "@/components/states/loading-state"
import { QueryState } from "@/components/states/query-state"
import { Card } from "@/components/ui/card"
import { ActivityItem } from "@/features/activity/activity-item"
import { useActivity } from "@/features/activity/hooks"
import { useNow } from "@/hooks/use-now"

const ACTIVITY_LIMIT = 50

export function ActivityPage() {
  const activity = useActivity(ACTIVITY_LIMIT)
  const now = useNow(undefined, activity.dataUpdatedAt)

  return (
    <>
      <PageHeader title="Activity" description="A record of every action taken in the library." />
      <QueryState
        query={activity}
        empty={
          <EmptyState
            icon={ScrollText}
            title="No activity yet"
            description="Each borrow, return and catalog change will appear here with when it happened."
          />
        }
        loading={<LoadingState rows={5} label="Loading activity" />}
        errorTitle="Could not load the activity"
      >
        {(events) => (
          <>
            <Card className="gap-0 py-0">
              <ol className="divide-y" aria-label="Actions, newest first">
                {events.map((event) => (
                  <ActivityItem key={event.id} event={event} now={now} />
                ))}
              </ol>
            </Card>
            {events.length >= ACTIVITY_LIMIT && (
              <p className="pt-3 text-sm text-muted-foreground">
                Showing the latest {ACTIVITY_LIMIT} actions.
              </p>
            )}
          </>
        )}
      </QueryState>
    </>
  )
}
