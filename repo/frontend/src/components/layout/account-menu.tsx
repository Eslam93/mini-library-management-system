import { ChevronDown, LogOut } from "lucide-react"
import { toast } from "sonner"

import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import { useCurrentUser } from "@/features/auth/current-user"
import { useSignOut } from "@/features/auth/hooks"
import { ApiError } from "@/lib/api"
import { roleLabels } from "@/lib/navigation"

/** Up to two letters from the name, for the avatar. */
function initials(name: string) {
  const words = name.trim().split(/\s+/).filter(Boolean)
  return words
    .slice(0, 2)
    .map((word) => word[0].toUpperCase())
    .join("")
}

/** Who is signed in, with which role, and the way out. */
export function AccountMenu() {
  const user = useCurrentUser()
  const signOut = useSignOut()

  function handleSignOut() {
    signOut.mutate(undefined, {
      onError: (error) =>
        toast.error("Could not sign out", {
          description: error instanceof ApiError ? error.message : "Something went wrong. Try again.",
        }),
    })
  }

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button variant="ghost" size="sm" aria-label={`Account menu, ${user.display_name}`} className="px-1.5">
          <span
            aria-hidden
            className="flex size-7 items-center justify-center rounded-full bg-accent text-xs font-semibold text-accent-foreground"
          >
            {initials(user.display_name)}
          </span>
          <span className="hidden max-w-40 truncate sm:inline">{user.display_name}</span>
          {user.is_demo && (
            <Badge variant="secondary" className="hidden sm:inline-flex">
              Demo
            </Badge>
          )}
          <ChevronDown aria-hidden className="text-muted-foreground" />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-64">
        <DropdownMenuLabel className="space-y-1">
          <span className="block truncate font-medium">{user.display_name}</span>
          {user.email && (
            <span className="block truncate text-xs text-muted-foreground">{user.email}</span>
          )}
          <span className="flex items-center gap-1.5 pt-1">
            <Badge variant="outline">{roleLabels[user.role]}</Badge>
            {user.is_demo && <Badge variant="secondary">Demo</Badge>}
          </span>
        </DropdownMenuLabel>
        <DropdownMenuSeparator />
        <DropdownMenuItem disabled={signOut.isPending} onSelect={handleSignOut}>
          <LogOut aria-hidden />
          Sign out
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  )
}
