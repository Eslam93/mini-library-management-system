import { useId } from "react"
import { CircleCheck } from "lucide-react"

import { Button } from "@/components/ui/button"
import { Label } from "@/components/ui/label"
import { NativeSelect } from "@/components/ui/native-select"
import { BOOK_SORTS, type CatalogFilters } from "@/features/books/catalog-filters"
import { useBookCategories } from "@/features/books/hooks"
import { cn } from "@/lib/utils"

/**
 * The catalog's availability toggle, category filter and order. The
 * categories come from the API; until they arrive, or if they cannot, the
 * list still works with "All categories".
 */
export function CatalogFilterBar({ filters }: { filters: CatalogFilters }) {
  const sortId = useId()
  const categories = useBookCategories().data ?? []
  // The API matches a category ignoring letter case, so a link may spell it
  // differently; the select shows the catalog's spelling. A category no book
  // has any more, from an old link, stays selectable so the select tells the truth.
  const selected =
    categories.find((name) => name.toLowerCase() === filters.category.toLowerCase()) ?? filters.category
  const options = selected && !categories.includes(selected) ? [selected, ...categories] : categories

  return (
    <div className="flex flex-wrap items-center gap-2">
      <Button
        type="button"
        variant="outline"
        aria-pressed={filters.availableOnly}
        onClick={() => filters.setAvailableOnly(!filters.availableOnly)}
        className="aria-pressed:border-primary/40 aria-pressed:bg-accent aria-pressed:text-accent-foreground"
      >
        <CircleCheck aria-hidden className={cn(filters.availableOnly ? "text-available" : "text-muted-foreground")} />
        Available now
      </Button>
      <NativeSelect
        aria-label="Category"
        value={selected}
        onChange={(event) => filters.setCategory(event.target.value)}
        className="w-auto max-w-56"
      >
        <option value="">All categories</option>
        {options.map((name) => (
          <option key={name} value={name}>
            {name}
          </option>
        ))}
      </NativeSelect>
      <div className="flex items-center gap-2">
        <Label htmlFor={sortId} className="font-normal whitespace-nowrap text-muted-foreground">
          Sort by
        </Label>
        <NativeSelect
          id={sortId}
          value={filters.sort}
          onChange={(event) => {
            const next = BOOK_SORTS.find((sort) => sort.value === event.target.value)
            if (next) filters.setSort(next.value)
          }}
          className="w-auto"
        >
          {BOOK_SORTS.map((sort) => (
            <option key={sort.value} value={sort.value}>
              {sort.label}
            </option>
          ))}
        </NativeSelect>
      </div>
    </div>
  )
}
