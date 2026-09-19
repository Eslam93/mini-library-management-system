import { ShieldX } from "lucide-react"
import { Link, Navigate, Outlet } from "react-router"

import { PageHeader } from "@/components/layout/page-header"
import { EmptyState } from "@/components/states/empty-state"
import { Button } from "@/components/ui/button"
import { useCurrentUser } from "@/features/auth/current-user"
import { homePaths } from "@/lib/navigation"
import type { Role } from "@/lib/types"

const audience: Record<Role, string> = {
  staff: "library staff",
  member: "members",
}

const signedInAs: Record<Role, string> = {
  staff: "staff",
  member: "a member",
}

/**
 * Shows the routes under it only to one role. Others get an explanation
 * instead of a page whose requests the API would refuse.
 */
export function RequireRole({ role }: { role: Role }) {
  const user = useCurrentUser()
  if (user.role === role) return <Outlet />

  return (
    <>
      <PageHeader title="Not available for your role" />
      <EmptyState
        icon={ShieldX}
        title={`This page is for ${audience[role]}`}
        description={`You are signed in as ${signedInAs[user.role]}. The menu lists the pages you can use.`}
      >
        <Button asChild variant="outline" size="sm">
          <Link to={homePaths[user.role]}>Go to the start page</Link>
        </Button>
      </EmptyState>
    </>
  )
}

/** "/" opens the signed-in user's start page. */
export function RoleHome() {
  const user = useCurrentUser()
  return <Navigate to={homePaths[user.role]} replace />
}
