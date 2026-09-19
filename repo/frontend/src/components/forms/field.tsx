import type { ReactNode } from "react"

import { Label } from "@/components/ui/label"
import { cn } from "@/lib/utils"

/** Props that tie a control to its label, hint and error message. */
export type FieldControlProps = {
  id: string
  "aria-invalid"?: true
  "aria-describedby"?: string
}

type FieldProps = {
  id: string
  label: string
  error?: string
  hint?: ReactNode
  optional?: boolean
  className?: string
  children: (control: FieldControlProps) => ReactNode
}

/** A labelled form control with an optional hint and an inline error below it. */
export function Field({ id, label, error, hint, optional, className, children }: FieldProps) {
  const hintId = hint ? `${id}-hint` : undefined
  const errorId = error ? `${id}-error` : undefined
  const describedBy = [errorId, hintId].filter(Boolean).join(" ") || undefined

  return (
    <div className={cn("grid content-start gap-2", className)}>
      <Label htmlFor={id}>
        {label}
        {optional && (
          <>
            {" "}
            <span className="font-normal text-muted-foreground">(optional)</span>
          </>
        )}
      </Label>
      {children({ id, "aria-invalid": error ? true : undefined, "aria-describedby": describedBy })}
      {error && (
        <p id={errorId} className="text-sm text-destructive">
          {error}
        </p>
      )}
      {hint && (
        <p id={hintId} className="text-xs text-muted-foreground">
          {hint}
        </p>
      )}
    </div>
  )
}
