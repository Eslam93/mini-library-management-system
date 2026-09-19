import { SearchX } from "lucide-react"
import { Link } from "react-router"

import { PageHeader } from "@/components/layout/page-header"
import { EmptyState } from "@/components/states/empty-state"
import { Button } from "@/components/ui/button"

export function NotFoundPage() {
  return (
    <>
      <PageHeader title="Page not found" />
      <EmptyState
        icon={SearchX}
        title="This page does not exist"
        description="The link may be old or mistyped."
      >
        <Button asChild variant="outline" size="sm">
          <Link to="/">Go to the start page</Link>
        </Button>
      </EmptyState>
    </>
  )
}
