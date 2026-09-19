import { useId } from "react"
import { Loader2, Search, X } from "lucide-react"

import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { cn } from "@/lib/utils"

type SearchFieldProps = {
  /** Read by screen readers; the placeholder shows what can be searched. */
  label: string
  placeholder: string
  value: string
  onChange: (value: string) => void
  onClear: () => void
  /** Shows a spinner while results load. */
  busy?: boolean
  className?: string
}

/** A search box for a list. Escape or the clear button empties it. */
export function SearchField({
  label,
  placeholder,
  value,
  onChange,
  onClear,
  busy = false,
  className,
}: SearchFieldProps) {
  const id = useId()
  const Icon = busy ? Loader2 : Search

  return (
    <div role="search" className={cn("relative w-full max-w-md", className)}>
      <Label htmlFor={id} className="sr-only">
        {label}
      </Label>
      <Icon
        aria-hidden
        className={cn(
          "pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-muted-foreground",
          busy && "animate-spin motion-reduce:animate-none",
        )}
      />
      <Input
        id={id}
        type="search"
        autoComplete="off"
        placeholder={placeholder}
        value={value}
        onChange={(event) => onChange(event.target.value)}
        onKeyDown={(event) => {
          if (event.key === "Escape" && value) {
            event.preventDefault()
            onClear()
          }
        }}
        className="pr-9 pl-9 [&::-webkit-search-cancel-button]:appearance-none"
      />
      {value && (
        <Button
          type="button"
          variant="ghost"
          size="icon-sm"
          className="absolute top-1/2 right-0.5 -translate-y-1/2 text-muted-foreground"
          onClick={onClear}
        >
          <X aria-hidden />
          <span className="sr-only">Clear the search box</span>
        </Button>
      )}
    </div>
  )
}
