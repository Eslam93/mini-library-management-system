import { z } from "zod"

import type { PickedMember } from "@/features/members/member-schema"
import { addDays, todayDateValue } from "@/lib/dates"

/** The API's default loan period. The dialog proposes it and staff can change it. */
export const LOAN_PERIOD_DAYS = 14
/** The latest due date the API accepts, in days from today. */
export const MAX_LOAN_DAYS = 90

export const borrowSchema = z.object({
  copy_id: z.string().min(1, "Choose an available copy."),
  member: z.custom<PickedMember | null>().transform((member, ctx) => {
    if (!member) {
      ctx.addIssue({ code: "custom", message: "Choose the member who borrows the book." })
      return z.NEVER
    }
    return member
  }),
  due_date: z.string().superRefine((value, ctx) => {
    const today = todayDateValue()
    if (!/^\d{4}-\d{2}-\d{2}$/.test(value)) {
      ctx.addIssue({ code: "custom", message: "Choose a due date." })
    } else if (value <= today) {
      ctx.addIssue({ code: "custom", message: "Choose a due date after today." })
    } else if (value > addDays(today, MAX_LOAN_DAYS)) {
      ctx.addIssue({
        code: "custom",
        message: `Choose a due date at most ${MAX_LOAN_DAYS} days from today.`,
      })
    }
  }),
})

export type BorrowFormValues = z.input<typeof borrowSchema>
export type BorrowFormOutput = z.output<typeof borrowSchema>
