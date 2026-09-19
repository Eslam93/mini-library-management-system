import { z } from "zod"

import type { MemberCreate, MemberOut } from "@/lib/types"

/** A member chosen in a picker: enough to show and to send. */
export type PickedMember = Pick<MemberOut, "id" | "full_name" | "email">

export const memberSchema = z.object({
  full_name: z.string().trim().min(1, "Enter the member's full name."),
  email: z
    .string()
    .trim()
    .refine((value) => value === "" || z.email().safeParse(value).success, "Enter a valid email address, such as name@example.com.")
    .transform((value) => value || null),
})

export type MemberFormValues = z.input<typeof memberSchema>

export function createMemberBody({ full_name, email }: z.output<typeof memberSchema>): MemberCreate {
  return email ? { full_name, email } : { full_name }
}
