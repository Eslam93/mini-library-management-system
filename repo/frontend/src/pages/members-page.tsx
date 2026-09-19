import { useState } from "react"
import { SearchX, UserPlus, Users } from "lucide-react"
import { useNavigate } from "react-router"

import { PageHeader } from "@/components/layout/page-header"
import { Pager } from "@/components/list/pager"
import { SearchField } from "@/components/list/search-field"
import { EmptyState } from "@/components/states/empty-state"
import { LoadingState } from "@/components/states/loading-state"
import { QueryState } from "@/components/states/query-state"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card } from "@/components/ui/card"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { AddMemberDialog } from "@/features/members/add-member-dialog"
import { useMembers } from "@/features/members/hooks"
import { MemberLink } from "@/features/members/member-link"
import { useUrlSearch } from "@/hooks/use-url-search"
import { formatCalendarDate } from "@/lib/format"
import type { MemberOut } from "@/lib/types"
import { cn } from "@/lib/utils"

const PAGE_SIZE = 20

export function MembersPage() {
  const search = useUrlSearch()
  const [adding, setAdding] = useState(false)
  const offset = (search.page - 1) * PAGE_SIZE
  const members = useMembers({ q: search.q || undefined, limit: PAGE_SIZE, offset })

  const empty = search.q ? (
    <EmptyState
      icon={SearchX}
      title={`No members match "${search.q}"`}
      description="Search looks at names and email addresses, and matches parts of words."
    >
      <Button variant="outline" size="sm" onClick={search.clear}>
        Clear search
      </Button>
    </EmptyState>
  ) : (
    <EmptyState
      icon={Users}
      title="No members yet"
      description="Add a member so they can borrow books. Each member shows here with their active loans."
    >
      <Button variant="outline" size="sm" onClick={() => setAdding(true)}>
        <UserPlus aria-hidden />
        Add member
      </Button>
    </EmptyState>
  )

  return (
    <>
      <PageHeader
        title="Members"
        description="People who borrow books from the library."
        actions={
          <Button onClick={() => setAdding(true)}>
            <UserPlus aria-hidden />
            Add member
          </Button>
        }
      />
      <SearchField
        label="Search members"
        placeholder="Search by name or email"
        value={search.draft}
        onChange={search.changeDraft}
        onClear={search.clear}
        busy={members.isFetching && members.isPlaceholderData}
        className="mb-4"
      />
      <QueryState
        query={members}
        isEmpty={(page) => page.items.length === 0}
        empty={empty}
        loading={<LoadingState rows={5} label="Loading members" />}
        errorTitle="Could not load the members"
      >
        {(page) => (
          <div
            className={cn("transition-opacity", members.isPlaceholderData && "opacity-60")}
            aria-busy={members.isPlaceholderData || undefined}
          >
            <Card className="py-0">
              <MembersTable members={page.items} />
            </Card>
            <Pager
              total={page.total}
              limit={page.limit}
              offset={page.offset}
              noun={["member", "members"]}
              onPageChange={search.setPage}
            />
          </div>
        )}
      </QueryState>
      <AddMemberDialog open={adding} onOpenChange={setAdding} />
    </>
  )
}

/**
 * The member list. The name is the link for keyboard and screen reader users;
 * a click anywhere on the row opens the member too.
 */
function MembersTable({ members }: { members: MemberOut[] }) {
  const navigate = useNavigate()

  return (
    <Table>
      <TableHeader>
        <TableRow className="hover:bg-transparent">
          <TableHead>Name</TableHead>
          <TableHead className="hidden sm:table-cell">Email</TableHead>
          <TableHead className="hidden md:table-cell">Member since</TableHead>
          <TableHead className="text-right">Active loans</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {members.map((member) => (
          <TableRow
            key={member.id}
            className="cursor-pointer"
            onClick={(event) => {
              // The name link navigates by itself.
              if ((event.target as HTMLElement).closest("a")) return
              navigate(`/members/${member.id}`)
            }}
          >
            <TableCell>
              <MemberLink member={member} className="block font-medium" />
              <span className="block text-xs text-muted-foreground sm:hidden">{member.email}</span>
            </TableCell>
            <TableCell className="hidden text-muted-foreground sm:table-cell">{member.email}</TableCell>
            <TableCell className="hidden whitespace-nowrap text-muted-foreground md:table-cell">
              {formatCalendarDate(member.joined_on)}
            </TableCell>
            <TableCell className="text-right">
              {member.active_loans > 0 ? (
                <Badge variant="borrowed">{member.active_loans}</Badge>
              ) : (
                <span className="text-muted-foreground tabular-nums">0</span>
              )}
            </TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  )
}
