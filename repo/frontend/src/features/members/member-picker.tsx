import { useState, type KeyboardEvent } from "react"
import { Search } from "lucide-react"

import type { FieldControlProps } from "@/components/forms/field"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { useMembers } from "@/features/members/hooks"
import type { PickedMember } from "@/features/members/member-schema"
import { useDebouncedValue } from "@/hooks/use-debounced-value"
import { plural } from "@/lib/format"
import { cn } from "@/lib/utils"

const RESULT_LIMIT = 8
const SEARCH_DELAY_MS = 250

type MemberPickerProps = FieldControlProps & {
  value: PickedMember | null
  onChange: (member: PickedMember | null) => void
  onBlur?: () => void
  autoFocus?: boolean
}

/**
 * Chooses a member by typing part of a name or email. The results list
 * follows the combobox pattern: arrow keys move, Enter chooses.
 */
export function MemberPicker({
  id,
  value,
  onChange,
  onBlur,
  autoFocus = false,
  ...aria
}: MemberPickerProps) {
  const [search, setSearch] = useState("")
  const [active, setActive] = useState(0)
  const [focusSearch, setFocusSearch] = useState(autoFocus)
  const q = useDebouncedValue(search.trim(), SEARCH_DELAY_MS)
  const members = useMembers({ q: q || undefined, limit: RESULT_LIMIT }, { enabled: value === null })

  if (value) {
    return (
      <div className="flex items-center justify-between gap-3 rounded-md border bg-muted/40 px-3 py-2">
        <div className="min-w-0 text-sm">
          <p className="truncate font-medium">{value.full_name}</p>
          {value.email && <p className="truncate text-xs text-muted-foreground">{value.email}</p>}
        </div>
        <Button
          type="button"
          variant="outline"
          size="sm"
          aria-label="Change member"
          onClick={() => {
            setFocusSearch(true)
            onChange(null)
          }}
        >
          Change
        </Button>
      </div>
    )
  }

  const items = members.data?.items ?? []
  const activeIndex = Math.min(active, items.length - 1)
  const listId = `${id}-results`
  const optionId = (memberId: string) => `${id}-option-${memberId}`

  function choose(member: PickedMember) {
    onChange({ id: member.id, full_name: member.full_name, email: member.email })
    setSearch("")
    setActive(0)
  }

  function moveTo(index: number) {
    setActive(index)
    document.getElementById(optionId(items[index].id))?.scrollIntoView?.({ block: "nearest" })
  }

  function handleKeyDown(event: KeyboardEvent<HTMLInputElement>) {
    if (event.key === "ArrowDown" && items.length > 0) {
      event.preventDefault()
      moveTo((activeIndex + 1) % items.length)
    } else if (event.key === "ArrowUp" && items.length > 0) {
      event.preventDefault()
      moveTo((activeIndex - 1 + items.length) % items.length)
    } else if (event.key === "Enter") {
      // Enter chooses; it never submits the form from here.
      event.preventDefault()
      if (items[activeIndex]) choose(items[activeIndex])
    }
  }

  let status: string
  if (members.isError) status = "Could not load members. Close the dialog and try again."
  else if (!members.data) status = "Loading members…"
  else if (items.length === 0) status = q ? `No member matches "${q}".` : "There are no members yet."
  else if (members.data.total > items.length)
    status = `Showing ${items.length} of ${members.data.total} members. Type to narrow the list.`
  else status = plural(items.length, "member", "members")

  return (
    <div className="grid gap-2">
      <div className="relative">
        <Search
          aria-hidden
          className="pointer-events-none absolute top-1/2 left-2.5 size-4 -translate-y-1/2 text-muted-foreground"
        />
        <Input
          {...aria}
          id={id}
          role="combobox"
          aria-autocomplete="list"
          aria-expanded={items.length > 0}
          aria-controls={items.length > 0 ? listId : undefined}
          aria-activedescendant={items[activeIndex] ? optionId(items[activeIndex].id) : undefined}
          // Focus comes here when the dialog opens and after "Change".
          autoFocus={focusSearch}
          autoComplete="off"
          placeholder="Search by name or email"
          className="pl-8"
          value={search}
          onChange={(event) => {
            setSearch(event.target.value)
            setActive(0)
          }}
          onKeyDown={handleKeyDown}
          onBlur={onBlur}
        />
      </div>
      {items.length > 0 && (
        <ul
          id={listId}
          role="listbox"
          aria-label="Members"
          className="max-h-52 overflow-y-auto rounded-md border bg-card p-1"
        >
          {items.map((member, index) => (
            <li
              key={member.id}
              id={optionId(member.id)}
              role="option"
              aria-selected={index === activeIndex}
              className={cn(
                "flex cursor-pointer items-center justify-between gap-3 rounded-sm px-2 py-1.5 text-sm",
                index === activeIndex && "bg-accent text-accent-foreground",
              )}
              // Keep focus in the search box so the keyboard keeps working.
              onMouseDown={(event) => event.preventDefault()}
              onMouseMove={() => setActive(index)}
              onClick={() => choose(member)}
            >
              <span className="min-w-0">
                <span className="block truncate font-medium">{member.full_name}</span>
                {member.email && (
                  <span className="block truncate text-xs text-muted-foreground">{member.email}</span>
                )}
              </span>
              <span className="shrink-0 text-xs text-muted-foreground">
                {plural(member.active_loans, "active loan", "active loans")}
              </span>
            </li>
          ))}
        </ul>
      )}
      <p aria-live="polite" className="text-xs text-muted-foreground">
        {status}
      </p>
    </div>
  )
}
