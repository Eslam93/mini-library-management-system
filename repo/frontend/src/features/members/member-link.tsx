import { Link } from "react-router"

import type { MemberRef } from "@/lib/types"
import { cn } from "@/lib/utils"

type MemberLinkProps = {
  member: MemberRef
  className?: string
  /** Called as the link is followed, such as to close the panel it sits in. */
  onClick?: () => void
}

/** A member's name, linking to the member's page. */
export function MemberLink({ member, className, onClick }: MemberLinkProps) {
  return (
    <Link
      to={`/members/${member.id}`}
      onClick={onClick}
      className={cn(
        "rounded-sm underline-offset-4 outline-none hover:underline focus-visible:ring-3 focus-visible:ring-ring/50",
        className,
      )}
    >
      {member.full_name}
    </Link>
  )
}
