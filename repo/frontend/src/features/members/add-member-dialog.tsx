import { useState } from "react"
import { zodResolver } from "@hookform/resolvers/zod"
import { useForm } from "react-hook-form"
import { toast } from "sonner"
import type { z } from "zod"

import { Field } from "@/components/forms/field"
import { FormAlert } from "@/components/forms/form-alert"
import { PendingButton } from "@/components/forms/pending-button"
import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { Input } from "@/components/ui/input"
import { useCreateMember } from "@/features/members/hooks"
import { createMemberBody, memberSchema } from "@/features/members/member-schema"
import { useDialogSession } from "@/hooks/use-dialog-session"
import { applyServerErrors } from "@/lib/form-errors"

type AddMemberDialogProps = {
  open: boolean
  onOpenChange: (open: boolean) => void
}

export function AddMemberDialog({ open, onOpenChange }: AddMemberDialogProps) {
  const session = useDialogSession(open)
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <AddMemberContent key={session} onClose={() => onOpenChange(false)} />
    </Dialog>
  )
}

function AddMemberContent({ onClose }: { onClose: () => void }) {
  const createMember = useCreateMember()
  const [formError, setFormError] = useState<string | null>(null)
  const {
    register,
    handleSubmit,
    setError,
    formState: { errors, isDirty, isSubmitting },
  } = useForm({
    resolver: zodResolver(memberSchema),
    defaultValues: { full_name: "", email: "" },
  })

  async function save(values: z.output<typeof memberSchema>) {
    setFormError(null)
    try {
      const member = await createMember.mutateAsync(createMemberBody(values))
      toast.success(`Added ${member.full_name} as a member`)
      onClose()
    } catch (error) {
      setFormError(
        applyServerErrors(error, setError, {
          fields: { full_name: "full_name", email: "email" },
          codes: { member_email_taken: "email" },
        }),
      )
    }
  }

  return (
    <DialogContent
      className="sm:max-w-md"
      onInteractOutside={(event) => {
        if (isDirty) event.preventDefault()
      }}
    >
      <DialogHeader>
        <DialogTitle>Add a member</DialogTitle>
        <DialogDescription>A member can borrow books as soon as they are added.</DialogDescription>
      </DialogHeader>
      <form noValidate onSubmit={handleSubmit(save)} className="grid gap-4">
        <FormAlert title="Could not add the member" message={formError} />
        <Field id="member-name" label="Full name" error={errors.full_name?.message}>
          {(control) => <Input {...control} autoComplete="off" {...register("full_name")} />}
        </Field>
        <Field
          id="member-email"
          label="Email"
          optional
          error={errors.email?.message}
          hint="Each member needs a different email address."
        >
          {(control) => <Input {...control} type="email" autoComplete="off" {...register("email")} />}
        </Field>
        <DialogFooter>
          <DialogClose asChild>
            <Button type="button" variant="outline">
              Cancel
            </Button>
          </DialogClose>
          <PendingButton type="submit" pending={isSubmitting} pendingLabel="Adding…">
            Add member
          </PendingButton>
        </DialogFooter>
      </form>
    </DialogContent>
  )
}
