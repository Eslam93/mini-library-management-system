import { describe, expect, it } from "vitest"

import { authKeys } from "@/features/auth/api"
import { endSession, safeNextPath, signInPath, startSession } from "@/features/auth/session"
import { createQueryClient } from "@/lib/query-client"
import { memberUser, staffUser } from "@/test/fixtures"

describe("safeNextPath", () => {
  it.each([
    ["/catalog", "/catalog"],
    ["/books/book-1?tab=copies#top", "/books/book-1?tab=copies#top"],
    ["/catalog?q=a%20b", "/catalog?q=a%20b"],
  ])("keeps the app path %s", (raw, expected) => {
    expect(safeNextPath(raw)).toBe(expected)
  })

  it.each([
    [null],
    [""],
    ["catalog"],
    ["https://evil.example/"],
    ["//evil.example/page"],
    ["/\\evil.example"],
    ["/.//evil.example"],
    ["/\t/evil.example"],
    ["javascript:alert(1)"],
    ["/sign-in"],
    ["/sign-in?next=/catalog"],
  ])("refuses %j", (raw) => {
    expect(safeNextPath(raw)).toBeNull()
  })
})

describe("signInPath", () => {
  it("carries the page to come back to", () => {
    expect(signInPath("/catalog?q=dune")).toBe("/sign-in?next=%2Fcatalog%3Fq%3Ddune")
  })

  it("leaves next out for the start page", () => {
    expect(signInPath("/")).toBe("/sign-in")
  })
})

describe("session changes", () => {
  it("ends a session once, however many requests are refused", () => {
    const queryClient = createQueryClient()
    queryClient.setQueryData(authKeys.me(), staffUser())
    const updates: unknown[] = []
    queryClient.getQueryCache().subscribe((event) => {
      if (event.type === "updated") updates.push(event.query.state.data)
    })

    endSession(queryClient)
    endSession(queryClient)

    expect(queryClient.getQueryData(authKeys.me())).toBeNull()
    expect(updates).toEqual([null])
  })

  it("starts a new session from an empty cache", () => {
    const queryClient = createQueryClient()
    queryClient.setQueryData(["books", "detail", "book-1"], { title: "Dune" })

    startSession(queryClient, memberUser())

    expect(queryClient.getQueryData(["books", "detail", "book-1"])).toBeUndefined()
    expect(queryClient.getQueryData(authKeys.me())).toEqual(memberUser())
  })
})
