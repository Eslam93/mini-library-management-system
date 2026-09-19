import { NavLink, useLocation } from "react-router"

import type { NavItem } from "@/lib/navigation"
import { cn } from "@/lib/utils"

type SidebarNavProps = {
  items: readonly NavItem[]
  /** Accessible name of the navigation landmark. */
  label: string
  /** Called after a link is clicked, for example to close the mobile menu. */
  onNavigate?: () => void
}

function isUnder(pathname: string, base: string) {
  return pathname === base || pathname.startsWith(`${base}/`)
}

export function SidebarNav({ items, label, onNavigate }: SidebarNavProps) {
  const { pathname } = useLocation()

  return (
    <nav aria-label={label} className="px-3">
      <ul className="space-y-1">
        {items.map(({ label: itemLabel, to, icon: Icon, alsoActiveOn = [] }) => {
          const inSection = alsoActiveOn.some((base) => isUnder(pathname, base))
          return (
            <li key={to}>
              <NavLink
                to={to}
                end={to === "/"}
                onClick={onNavigate}
                className={({ isActive }) =>
                  cn(
                    "flex items-center gap-3 rounded-md px-3 py-2 text-sm font-medium text-muted-foreground transition-colors outline-none hover:bg-accent hover:text-accent-foreground focus-visible:ring-3 focus-visible:ring-ring/50",
                    (isActive || inSection) && "bg-accent text-accent-foreground",
                  )
                }
              >
                <Icon className="size-4 shrink-0" aria-hidden />
                {itemLabel}
              </NavLink>
            </li>
          )
        })}
      </ul>
    </nav>
  )
}
