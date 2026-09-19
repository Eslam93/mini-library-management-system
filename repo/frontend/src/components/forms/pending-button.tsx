import type * as React from "react"
import { Loader2 } from "lucide-react"

import { Button } from "@/components/ui/button"

type PendingButtonProps = React.ComponentProps<typeof Button> & {
  pending: boolean
  /** Shown while the request runs, such as "Saving…". */
  pendingLabel: string
}

/** A button that shows a spinner and stays disabled while its request runs. */
export function PendingButton({
  pending,
  pendingLabel,
  disabled,
  children,
  ...props
}: PendingButtonProps) {
  return (
    <Button disabled={pending || disabled} aria-busy={pending || undefined} {...props}>
      {pending ? (
        <>
          <Loader2 className="animate-spin motion-reduce:animate-none" aria-hidden />
          {pendingLabel}
        </>
      ) : (
        children
      )}
    </Button>
  )
}
