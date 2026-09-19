import { CircleAlert } from "lucide-react"

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"

type FormAlertProps = {
  title: string
  message: string | null
}

/** A form-level error for problems that do not belong to one field. Renders nothing without a message. */
export function FormAlert({ title, message }: FormAlertProps) {
  if (!message) return null
  return (
    <Alert variant="destructive" role="alert">
      <CircleAlert aria-hidden />
      <AlertTitle>{title}</AlertTitle>
      <AlertDescription className="text-destructive/90">{message}</AlertDescription>
    </Alert>
  )
}
