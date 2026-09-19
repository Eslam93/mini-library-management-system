import {
  ArrowLeftRight,
  BookMarked,
  BookOpen,
  History,
  LayoutDashboard,
  ScrollText,
  Users,
  type LucideIcon,
} from "lucide-react"

import type { Role } from "@/lib/types"

export type NavItem = {
  label: string
  to: string
  icon: LucideIcon
  /** Other paths that belong to this section, such as a book's page under Catalog. */
  alsoActiveOn?: readonly string[]
}

/** Sidebar entries for each role. The shell shows the list for the signed-in user's role. */
export const navigation: Record<Role, readonly NavItem[]> = {
  staff: [
    { label: "Dashboard", to: "/dashboard", icon: LayoutDashboard },
    { label: "Catalog", to: "/catalog", icon: BookOpen, alsoActiveOn: ["/books"] },
    { label: "Circulation", to: "/circulation", icon: ArrowLeftRight },
    { label: "Members", to: "/members", icon: Users },
    { label: "Activity", to: "/activity", icon: ScrollText },
  ],
  member: [
    { label: "Catalog", to: "/catalog", icon: BookOpen, alsoActiveOn: ["/books"] },
    { label: "My loans", to: "/my-loans", icon: BookMarked },
    { label: "History", to: "/history", icon: History },
  ],
}

/** Where each role starts: after sign-in, and at "/". */
export const homePaths: Record<Role, string> = {
  staff: "/dashboard",
  member: "/catalog",
}

export const roleLabels: Record<Role, string> = {
  staff: "Staff",
  member: "Member",
}
