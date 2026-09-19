import { afterEach, describe, expect, it } from "vitest"

import {
  forgetConversations,
  loadConversation,
  saveConversation,
  withoutSupersededCard,
  withProposal,
  type ChatItem,
  type Conversation,
} from "@/features/copilot/conversation"
import type { CopilotDisplay } from "@/features/copilot/types"
import type { BookSummary } from "@/lib/types"
import { bookDetail, bookSummary, proposal } from "@/test/fixtures"

const conversation: Conversation = {
  conversationId: "conv-1",
  items: [
    { id: "1", kind: "user", text: "Anything overdue?" },
    { id: "2", kind: "status", text: "Checking your loans" },
    { id: "3", kind: "assistant", text: "Nothing is overdue." },
  ],
}

describe("the stored conversation", () => {
  afterEach(() => {
    sessionStorage.clear()
  })

  it("comes back for the same user without the running turn's status lines", () => {
    saveConversation("user-1", conversation)

    expect(loadConversation("user-1")).toEqual({
      conversationId: "conv-1",
      items: [conversation.items[0], conversation.items[2]],
    })
    expect(loadConversation("user-2").items).toEqual([])
  })

  it("reads anything unexpected as an empty conversation", () => {
    sessionStorage.setItem("library.copilot.user-1", "{not json")
    expect(loadConversation("user-1")).toEqual({ conversationId: null, items: [] })

    sessionStorage.setItem("library.copilot.user-1", JSON.stringify({ items: "nope" }))
    expect(loadConversation("user-1")).toEqual({ conversationId: null, items: [] })
  })

  it("is forgotten for every user at sign-out, leaving other keys alone", () => {
    saveConversation("user-1", conversation)
    saveConversation("user-2", conversation)
    sessionStorage.setItem("other", "kept")

    forgetConversations()

    expect(loadConversation("user-1").items).toEqual([])
    expect(loadConversation("user-2").items).toEqual([])
    expect(sessionStorage.getItem("other")).toBe("kept")
  })
})

describe("a book's detail after a search card", () => {
  const dune = bookSummary()
  const emma = bookSummary({ id: "book-2", title: "Emma", author: "Jane Austen" })
  const duneDetail: CopilotDisplay = { kind: "book", book: bookDetail() }

  function searchCard(id: string, books: BookSummary[]): ChatItem {
    return { id, kind: "result", tool: "search_catalog", display: { kind: "books", items: books } }
  }

  it("replaces this turn's search card when the card showed only that book", () => {
    const items: ChatItem[] = [
      { id: "1", kind: "user", text: "Is Dune in?" },
      searchCard("2", [dune]),
      { id: "3", kind: "status", text: "Opening the book" },
    ]

    expect(withoutSupersededCard(items, duneDetail)).toEqual([items[0], items[2]])
  })

  it("keeps an earlier turn's card, a card with several books, and a card for another book", () => {
    const items: ChatItem[] = [
      searchCard("1", [dune]),
      { id: "2", kind: "user", text: "And the others?" },
      searchCard("3", [dune, emma]),
      searchCard("4", [emma]),
    ]

    expect(withoutSupersededCard(items, duneDetail)).toEqual(items)
    expect(withoutSupersededCard(items, { kind: "books", items: [dune] })).toBe(items)
  })
})

describe("a proposal's latest state", () => {
  it("replaces the proposal its card holds, and leaves other conversations as they are", () => {
    const card: ChatItem = {
      id: "1",
      kind: "result",
      tool: "prepare_borrow",
      display: { kind: "proposal", proposal: proposal() },
    }
    const conversation: Conversation = { conversationId: "conv-1", items: [card] }
    const confirmed = proposal({ status: "confirmed", resolved_at: "2026-09-19T12:02:00Z" })

    expect(withProposal(conversation, confirmed)).toEqual({
      conversationId: "conv-1",
      items: [{ ...card, display: { kind: "proposal", proposal: confirmed } }],
    })
    expect(withProposal(conversation, proposal({ id: "proposal-2" }))).toBe(conversation)
  })
})
