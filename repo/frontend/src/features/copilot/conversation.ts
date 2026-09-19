import type { CopilotDisplay, ProposalOut } from "@/features/copilot/types"

/**
 * One entry in the conversation as the panel shows it. Status lines exist
 * only while their turn runs; everything else is kept for the tab.
 */
export type ChatItem =
  | { id: string; kind: "user"; text: string }
  | { id: string; kind: "status"; text: string }
  | { id: string; kind: "result"; tool: string; display: CopilotDisplay }
  | { id: string; kind: "assistant"; text: string }
  | { id: string; kind: "error"; code: string; message: string }
  | { id: string; kind: "stopped" }

export type Conversation = {
  /** Set by the server's first event; null until the first turn starts. */
  conversationId: string | null
  items: ChatItem[]
}

type WithoutId<Item> = Item extends unknown ? Omit<Item, "id"> : never

/** An item before it gets its id. */
export type NewChatItem = WithoutId<ChatItem>

export const EMPTY_CONVERSATION: Conversation = { conversationId: null, items: [] }

let lastId = 0

/** Ids only need to be unique within the tab's conversation, including items restored from storage. */
export function withId(item: NewChatItem): ChatItem {
  lastId += 1
  return { ...item, id: `${Date.now().toString(36)}-${lastId}` } as ChatItem
}

const STORAGE_PREFIX = "library.copilot."

/** Where the tab keeps the conversation. One key per user, so a new sign-in never sees the last one's. */
function storageKey(userId: string) {
  return `${STORAGE_PREFIX}${userId}`
}

/**
 * The conversation saved in this tab, or an empty one. Storage can be
 * missing, full or blocked (private windows), and a stored value may come
 * from an older version of the app, so anything unexpected reads as empty.
 */
export function loadConversation(userId: string): Conversation {
  try {
    const raw = sessionStorage.getItem(storageKey(userId))
    if (!raw) return EMPTY_CONVERSATION
    const value = JSON.parse(raw) as Partial<Conversation>
    if (!Array.isArray(value.items)) return EMPTY_CONVERSATION
    const conversationId = typeof value.conversationId === "string" ? value.conversationId : null
    return { conversationId, items: value.items }
  } catch {
    return EMPTY_CONVERSATION
  }
}

/** Saves the conversation for the tab. Status lines belong to a running turn, so they are left out. */
export function saveConversation(userId: string, conversation: Conversation) {
  try {
    if (conversation.conversationId === null && conversation.items.length === 0) {
      sessionStorage.removeItem(storageKey(userId))
      return
    }
    const items = conversation.items.filter((item) => item.kind !== "status")
    sessionStorage.setItem(storageKey(userId), JSON.stringify({ ...conversation, items }))
  } catch {
    // Without storage the conversation still lasts until the page reloads.
  }
}

/** Drops every conversation this tab kept, when someone signs out. */
export function forgetConversations() {
  try {
    const keys = Array.from({ length: sessionStorage.length }, (_, index) => sessionStorage.key(index))
    for (const key of keys) {
      if (key?.startsWith(STORAGE_PREFIX)) sessionStorage.removeItem(key)
    }
  } catch {
    // Nothing was stored.
  }
}

/** The last message the user sent, which "Try again" sends again. */
export function lastUserIndex(items: ChatItem[]): number {
  return items.findLastIndex((item) => item.kind === "user")
}

/**
 * The items ready for a new result. When the result is a book's detail, a
 * search card of the running turn that showed only that book is dropped: the
 * detail says everything the card said, so the turn shows the detail alone.
 */
export function withoutSupersededCard(items: ChatItem[], display: CopilotDisplay): ChatItem[] {
  if (display.kind !== "book") return items
  const turnStart = lastUserIndex(items) + 1
  const superseded = (item: ChatItem, index: number) =>
    index >= turnStart &&
    item.kind === "result" &&
    item.display.kind === "books" &&
    item.display.items.length === 1 &&
    item.display.items[0].id === display.book.id
  return items.filter((item, index) => !superseded(item, index))
}

/**
 * The conversation with a proposal's card holding the proposal's latest
 * state, so a card restored after a reload shows how the proposal ended.
 * The same conversation when nothing changes.
 */
export function withProposal(conversation: Conversation, proposal: ProposalOut): Conversation {
  let changed = false
  const items = conversation.items.map((item) => {
    if (
      item.kind !== "result" ||
      item.display.kind !== "proposal" ||
      item.display.proposal.id !== proposal.id ||
      item.display.proposal === proposal
    ) {
      return item
    }
    changed = true
    return { ...item, display: { kind: "proposal" as const, proposal } }
  })
  return changed ? { ...conversation, items } : conversation
}
