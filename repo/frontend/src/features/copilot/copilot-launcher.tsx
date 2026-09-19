import { useState } from "react"
import { Sparkles } from "lucide-react"

import { Button } from "@/components/ui/button"
import { Sheet, SheetContent, SheetTrigger } from "@/components/ui/sheet"
import { useCurrentUser } from "@/features/auth/current-user"
import { CopilotPanel } from "@/features/copilot/copilot-panel"
import { useCopilotChat, useCopilotConfig } from "@/features/copilot/hooks"

/**
 * The Copilot button in the top bar and the panel it opens: from the right
 * on wide screens, the whole screen on phones. The conversation lives here,
 * outside the panel, so closing the panel or changing page does not end a
 * turn. The config is fetched when the panel opens, so pages never wait on it.
 */
export function CopilotLauncher() {
  const user = useCurrentUser()
  const [open, setOpen] = useState(false)
  const chat = useCopilotChat(user.id)
  const config = useCopilotConfig({ enabled: open })

  return (
    <Sheet open={open} onOpenChange={setOpen}>
      <SheetTrigger asChild>
        <Button variant="outline" size="sm" className="relative">
          <Sparkles aria-hidden className="text-primary" />
          <span className="sr-only sm:not-sr-only">Copilot</span>
          {chat.running && !open && (
            <span aria-hidden className="absolute -top-0.5 -right-0.5 size-2 animate-pulse rounded-full bg-primary" />
          )}
        </Button>
      </SheetTrigger>
      <SheetContent side="right" className="w-full gap-0 p-0 sm:max-w-md">
        <CopilotPanel
          face={config.data?.face ?? user.role}
          config={config.data}
          configFailed={config.isError}
          onRetryConfig={() => void config.refetch()}
          chat={chat}
          onNavigate={() => setOpen(false)}
        />
      </SheetContent>
    </Sheet>
  )
}
