import { screen, waitFor, within } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

import type { Conversation } from "@/features/copilot/conversation"
import { CopilotLauncher } from "@/features/copilot/copilot-launcher"
import type { CopilotConfig } from "@/features/copilot/types"
import { formatDueDate } from "@/lib/format"
import { errorResponse, requestsTo, stubApi } from "@/test/api-stub"
import { bookDetail, bookSummary, loan, memberUser, proposal, staffUser, tableDisplay } from "@/test/fixtures"
import { renderWithProviders } from "@/test/render"

const encoder = new TextEncoder()

function config(overrides: Partial<CopilotConfig> = {}): CopilotConfig {
  return {
    available: true,
    face: "member",
    reason: null,
    examples: ["Show me available science fiction", "When is my book due?"],
    ...overrides,
  }
}

/** Server-sent events as the API writes them. */
function sse(...events: [name: string, data: unknown][]) {
  return events.map(([name, data]) => `event: ${name}\ndata: ${JSON.stringify(data)}\n\n`).join("")
}

/**
 * A 200 event stream the test feeds by hand. Text goes out in pieces of a
 * few bytes, so lines, JSON and even multi-byte characters are cut apart.
 */
function eventStream() {
  let source!: ReadableStreamDefaultController<Uint8Array>
  let cancelled = false
  const body = new ReadableStream<Uint8Array>({
    start(controller) {
      source = controller
    },
    cancel() {
      cancelled = true
    },
  })
  return {
    response: new Response(body, { headers: { "Content-Type": "text/event-stream" } }),
    send(text: string, size = 5) {
      const bytes = encoder.encode(text)
      for (let index = 0; index < bytes.length; index += size) {
        source.enqueue(bytes.slice(index, index + size))
      }
    },
    close() {
      source.close()
    },
    get cancelled() {
      return cancelled
    },
  }
}

/** A whole turn's stream, already complete. */
function replyWith(text: string) {
  const stream = eventStream()
  stream.send(text)
  stream.close()
  return stream.response
}

function renderLauncher(user = memberUser()) {
  return renderWithProviders(<CopilotLauncher />, { user, route: "/catalog" })
}

/** The conversation the tab keeps for a user. */
function storedConversation(userId: string): Conversation {
  return JSON.parse(sessionStorage.getItem(`library.copilot.${userId}`) ?? "null") as Conversation
}

/** The status of the proposal whose card the stored conversation holds. */
function storedProposalStatus(userId: string) {
  for (const item of storedConversation(userId).items) {
    if (item.kind === "result" && item.display.kind === "proposal") return item.display.proposal.status
  }
  return null
}

async function openPanel(user: ReturnType<typeof userEvent.setup>) {
  await user.click(screen.getByRole("button", { name: "Copilot" }))
  return screen.findByRole("dialog")
}

function messageBox() {
  return screen.getByRole("textbox", { name: "Message" })
}

describe("CopilotLauncher", () => {
  beforeEach(() => {
    sessionStorage.clear()
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it("asks for nothing until it is opened, then shows the member face with example prompts", async () => {
    const fetchMock = stubApi({ "GET /api/copilot/config": () => config() })
    const user = userEvent.setup()

    renderLauncher()
    expect(fetchMock).not.toHaveBeenCalled()

    const panel = await openPanel(user)

    expect(panel).toHaveAccessibleName("Library assistant")
    expect(await within(panel).findByRole("button", { name: "When is my book due?" })).toBeInTheDocument()
    expect(messageBox()).toHaveFocus()
  })

  it("calls itself the Staff Copilot for staff", async () => {
    stubApi({ "GET /api/copilot/config": () => config({ face: "staff", examples: [] }) })
    const user = userEvent.setup()

    renderLauncher(staffUser())

    expect(await openPanel(user)).toHaveAccessibleName("Staff Copilot")
  })

  it("explains calmly when the assistant is not configured, with a way to the catalog", async () => {
    stubApi({
      "GET /api/copilot/config": () =>
        config({ available: false, reason: "No language model is configured." }),
    })
    const user = userEvent.setup()

    renderLauncher()
    const panel = await openPanel(user)

    expect(await within(panel).findByText("The assistant is unavailable right now")).toBeInTheDocument()
    expect(within(panel).getByText("No language model is configured.")).toBeInTheDocument()
    expect(within(panel).getByRole("link", { name: "Search the catalog" })).toHaveAttribute("href", "/catalog")
    expect(within(panel).queryByRole("button", { name: "When is my book due?" })).not.toBeInTheDocument()
    expect(messageBox()).toBeDisabled()
  })

  it("turns unavailable when the chat is refused with 503 before it streams", async () => {
    stubApi({
      "GET /api/copilot/config": () => config(),
      "POST /api/copilot/chat": () =>
        errorResponse(503, "copilot_unavailable", "The assistant is not available."),
    })
    const user = userEvent.setup()

    renderLauncher()
    const panel = await openPanel(user)
    await user.type(messageBox(), "Can I borrow Dune?{Enter}")

    expect(await within(panel).findByText("The assistant is unavailable right now")).toBeInTheDocument()
    expect(messageBox()).toBeDisabled()
    expect(within(panel).queryByRole("button", { name: "Try again" })).not.toBeInTheDocument()
  })

  it("streams a turn: status while it runs, then books as cards and the reply", async () => {
    const stream = eventStream()
    const fetchMock = stubApi({
      "GET /api/copilot/config": () => config(),
      "POST /api/copilot/chat": ({ body }) =>
        (body as { conversation_id?: string }).conversation_id
          ? replyWith(sse(["message", { text: "Anything else?" }], ["done", {}]))
          : stream.response,
    })
    const user = userEvent.setup()

    renderLauncher()
    const panel = await openPanel(user)
    await user.type(messageBox(), "Show me available science fiction{Enter}")

    stream.send(
      sse(["conversation", { conversation_id: "conv-1" }], ["status", { text: "Searching the catalog" }]),
    )
    expect(await within(panel).findByText("Searching the catalog")).toBeInTheDocument()
    expect(messageBox()).toBeDisabled()
    expect(within(panel).getByRole("button", { name: "Stop" })).toBeInTheDocument()

    stream.send(
      sse(
        [
          "result",
          {
            tool: "search_catalog",
            display: {
              kind: "books",
              items: [
                bookSummary(),
                bookSummary({
                  id: "book-2",
                  title: "Hyperion",
                  author: "Dan Simmons",
                  copies_available: 0,
                  availability: "all_borrowed",
                }),
              ],
            },
          },
        ],
        ["message", { text: "Here are **two** matches — both classics:\n- Dune\n- Hyperion" }],
        ["done", {}],
      ),
      // One byte at a time: the dash's three bytes arrive apart.
      1,
    )
    stream.close()

    const books = await within(panel).findByRole("list", { name: "2 books" })
    expect(within(books).getByRole("link", { name: "Dune" })).toHaveAttribute("href", "/books/book-1")
    expect(within(books).getByRole("link", { name: "Hyperion" })).toHaveAttribute("href", "/books/book-2")
    expect(within(books).getByText("2 of 3 available")).toBeInTheDocument()
    expect(within(books).getByText("All copies borrowed")).toBeInTheDocument()
    expect(within(panel).getByText("two").tagName).toBe("STRONG")
    expect(within(panel).getByText(/matches — both classics/)).toBeInTheDocument()
    // Status lines belong to the running turn only.
    await waitFor(() => expect(within(panel).queryByText("Searching the catalog")).not.toBeInTheDocument())
    expect(messageBox()).toBeEnabled()

    // A follow-up continues the same conversation on the server.
    await user.type(messageBox(), "Only the available ones{Enter}")
    expect(await within(panel).findByText("Anything else?")).toBeInTheDocument()
    const requests = requestsTo(fetchMock, "POST /api/copilot/chat")
    expect(requests.map((request) => request.body)).toEqual([
      { message: "Show me available science fiction" },
      { conversation_id: "conv-1", message: "Only the available ones" },
    ])

    // A book card leads to the book's page and closes the panel.
    await user.click(within(panel).getByRole("link", { name: "Hyperion" }))
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument())
    expect(screen.getByTestId("location")).toHaveTextContent("/books/book-2")
  })

  it("shows an error event inline and sends the last message again on Try again", async () => {
    let calls = 0
    const fetchMock = stubApi({
      "GET /api/copilot/config": () => config(),
      "POST /api/copilot/chat": () => {
        calls += 1
        return calls === 1
          ? replyWith(
              sse(
                ["conversation", { conversation_id: "conv-1" }],
                ["error", { code: "copilot_timeout", message: "The assistant took too long to answer." }],
                ["done", {}],
              ),
            )
          : replyWith(sse(["message", { text: "Two copies exist; one is available now." }], ["done", {}]))
      },
    })
    const user = userEvent.setup()

    renderLauncher()
    const panel = await openPanel(user)
    await user.type(messageBox(), "Can I borrow Dune?{Enter}")

    const alert = await within(panel).findByRole("alert")
    expect(alert).toHaveTextContent("The answer took too long")
    expect(alert).toHaveTextContent("The assistant took too long to answer.")

    await user.click(within(alert).getByRole("button", { name: "Try again" }))

    expect(await within(panel).findByText("Two copies exist; one is available now.")).toBeInTheDocument()
    expect(within(panel).queryByRole("alert")).not.toBeInTheDocument()
    expect(within(panel).getAllByText("Can I borrow Dune?")).toHaveLength(1)
    const requests = requestsTo(fetchMock, "POST /api/copilot/chat")
    expect(requests.map((request) => request.body)).toEqual([
      { message: "Can I borrow Dune?" },
      { conversation_id: "conv-1", message: "Can I borrow Dune?" },
    ])
  })

  it("says so when the server cannot be reached, or when messages come too fast", async () => {
    let calls = 0
    stubApi({
      "GET /api/copilot/config": () => config(),
      "POST /api/copilot/chat": () => {
        calls += 1
        if (calls === 1) throw new TypeError("Failed to fetch")
        return errorResponse(429, "copilot_rate_limited", "Too many messages in a short time.")
      },
    })
    const user = userEvent.setup()

    renderLauncher()
    const panel = await openPanel(user)
    await user.type(messageBox(), "Anything overdue?{Enter}")

    expect(await within(panel).findByRole("alert")).toHaveTextContent("Could not reach the server.")

    await user.click(within(panel).getByRole("button", { name: "Try again" }))

    const alert = await within(panel).findByRole("alert")
    await waitFor(() => expect(alert).toHaveTextContent("Too many messages"))
    expect(alert).toHaveTextContent("Wait a minute before sending another message.")
  })

  it("sends an example prompt and shows the loans it finds with their due dates", async () => {
    // Midday UTC keeps "today" the same calendar date in every time zone.
    vi.useFakeTimers({ toFake: ["Date"] })
    vi.setSystemTime(new Date("2026-09-19T12:00:00Z"))
    const fetchMock = stubApi({
      "GET /api/copilot/config": () => config(),
      "POST /api/copilot/chat": () =>
        replyWith(
          sse(
            [
              "result",
              {
                tool: "get_my_loans",
                display: {
                  kind: "loans",
                  items: [
                    loan({ due_at: "2026-09-15T23:59:59Z", is_overdue: true, days_overdue: 4 }),
                    loan({
                      id: "loan-2",
                      copy: { id: "copy-7", code: "CP-0007" },
                      book: { id: "book-2", title: "Emma", author: "Jane Austen" },
                      due_at: "2026-09-21T23:59:59Z",
                    }),
                  ],
                },
              },
            ],
            ["message", { text: "Dune is overdue." }],
            ["done", {}],
          ),
        ),
    })
    const user = userEvent.setup()

    renderLauncher()
    const panel = await openPanel(user)
    await user.click(await within(panel).findByRole("button", { name: "When is my book due?" }))

    const loans = await within(panel).findByRole("list", { name: "2 loans" })
    const [dune, emma] = within(loans).getAllByRole("listitem")
    expect(within(dune).getByRole("link", { name: "Dune" })).toHaveAttribute("href", "/books/book-1")
    expect(within(dune).getByText("Overdue")).toBeInTheDocument()
    expect(within(emma).getByText(/CP-0007/)).toBeInTheDocument()
    expect(within(emma).getByText("Due in 2 days")).toBeInTheDocument()
    expect(requestsTo(fetchMock, "POST /api/copilot/chat")[0].body).toEqual({
      message: "When is my book due?",
    })
  })

  it("streams the analyst's figures as a table for staff and keeps it for the tab", async () => {
    const figures = tableDisplay({ chart: null })
    stubApi({
      "GET /api/copilot/config": () => config({ face: "staff", examples: [] }),
      "POST /api/copilot/chat": () =>
        replyWith(
          sse(
            ["result", { tool: "query_metrics", display: figures }],
            ["message", { text: "Technology led with 37.1% of loans." }],
            ["done", {}],
          ),
        ),
    })
    const user = userEvent.setup()

    renderLauncher(staffUser())
    const panel = await openPanel(user)
    await user.type(messageBox(), "Which categories were borrowed most this quarter?{Enter}")

    const table = await within(panel).findByRole("table", { name: "Loans by category" })
    const [, technology] = within(table).getAllByRole("row")
    expect(within(technology).getByRole("rowheader")).toHaveTextContent("Technology")
    expect(within(technology).getAllByRole("cell")[1]).toHaveTextContent("37.1%")
    expect(await within(panel).findByText("Technology led with 37.1% of loans.")).toBeInTheDocument()
    expect(storedConversation("user-staff").items).toContainEqual(
      expect.objectContaining({ kind: "result", tool: "query_metrics", display: figures }),
    )
  })

  it("runs a search from a category chip", async () => {
    const fetchMock = stubApi({
      "GET /api/copilot/config": () => config(),
      "POST /api/copilot/chat": () =>
        replyWith(
          sse(
            ["result", { tool: "list_categories", display: { kind: "categories", items: ["History", "Poetry"] } }],
            ["done", {}],
          ),
        ),
    })
    const user = userEvent.setup()

    renderLauncher()
    const panel = await openPanel(user)
    await user.type(messageBox(), "What categories are there?{Enter}")
    await user.click(await within(panel).findByRole("button", { name: "Show me Poetry books" }))

    await waitFor(() => expect(requestsTo(fetchMock, "POST /api/copilot/chat")).toHaveLength(2))
    expect(requestsTo(fetchMock, "POST /api/copilot/chat")[1].body).toEqual({
      message: "Show me Poetry books",
    })
  })

  it("sends on Enter and adds a line on Shift+Enter", async () => {
    const fetchMock = stubApi({
      "GET /api/copilot/config": () => config(),
      "POST /api/copilot/chat": () => replyWith(sse(["message", { text: "Noted." }], ["done", {}])),
    })
    const user = userEvent.setup()

    renderLauncher()
    await openPanel(user)
    await user.type(messageBox(), "Books by Austen{Shift>}{Enter}{/Shift}published before 1815")

    expect(messageBox()).toHaveValue("Books by Austen\npublished before 1815")
    expect(requestsTo(fetchMock, "POST /api/copilot/chat")).toHaveLength(0)

    await user.keyboard("{Enter}")

    expect(await screen.findByText("Noted.")).toBeInTheDocument()
    expect(messageBox()).toHaveValue("")
    expect(requestsTo(fetchMock, "POST /api/copilot/chat")[0].body).toEqual({
      message: "Books by Austen\npublished before 1815",
    })
  })

  it("keeps the conversation for the tab when the panel mounts again", async () => {
    const fetchMock = stubApi({
      "GET /api/copilot/config": () => config(),
      "POST /api/copilot/chat": () =>
        replyWith(
          sse(["conversation", { conversation_id: "conv-9" }], ["message", { text: "Dune is available." }], ["done", {}]),
        ),
    })
    const user = userEvent.setup()

    const first = renderLauncher()
    await openPanel(user)
    await user.type(messageBox(), "Is Dune in?{Enter}")
    expect(await screen.findByText("Dune is available.")).toBeInTheDocument()
    first.unmount()

    renderLauncher()
    const panel = await openPanel(user)

    expect(within(panel).getByText("Is Dune in?")).toBeInTheDocument()
    expect(within(panel).getByText("Dune is available.")).toBeInTheDocument()
    await user.type(messageBox(), "And Emma?{Enter}")
    await waitFor(() => expect(requestsTo(fetchMock, "POST /api/copilot/chat")).toHaveLength(2))
    expect(requestsTo(fetchMock, "POST /api/copilot/chat")[1].body).toEqual({
      conversation_id: "conv-9",
      message: "And Emma?",
    })

    // A new conversation forgets it.
    await user.click(within(panel).getByRole("button", { name: "New conversation" }))
    expect(within(panel).queryByText("Is Dune in?")).not.toBeInTheDocument()
    expect(sessionStorage.getItem("library.copilot.user-member")).toBeNull()
  })

  it("stops a running turn: the request is aborted and what arrived stays", async () => {
    const stream = eventStream()
    const fetchMock = stubApi({
      "GET /api/copilot/config": () => config(),
      "POST /api/copilot/chat": () => stream.response,
    })
    const user = userEvent.setup()

    renderLauncher()
    const panel = await openPanel(user)
    await user.type(messageBox(), "Show me everything{Enter}")
    stream.send(sse(["status", { text: "Searching the catalog" }]))
    expect(await within(panel).findByText("Searching the catalog")).toBeInTheDocument()

    await user.click(within(panel).getByRole("button", { name: "Stop" }))

    expect(await within(panel).findByText("You stopped this answer.")).toBeInTheDocument()
    const [, init] = fetchMock.mock.calls.find(([input]) => String(input) === "/api/copilot/chat") ?? []
    expect(init?.signal?.aborted).toBe(true)
    expect(stream.cancelled).toBe(true)
    expect(within(panel).getByText("Show me everything")).toBeInTheDocument()
    expect(messageBox()).toBeEnabled()
    expect(within(panel).getByRole("button", { name: "Send" })).toBeInTheDocument()
  })
  it("shows a book's detail alone when the same turn first found only that book", async () => {
    stubApi({
      "GET /api/copilot/config": () => config({ face: "staff", examples: [] }),
      "POST /api/copilot/chat": () =>
        replyWith(
          sse(
            ["conversation", { conversation_id: "conv-1" }],
            ["result", { tool: "search_catalog", display: { kind: "books", items: [bookSummary()] } }],
            ["result", { tool: "get_book", display: { kind: "book", book: bookDetail() } }],
            ["message", { text: "Dune has two copies on the shelf." }],
            ["done", {}],
          ),
        ),
    })
    const user = userEvent.setup()

    renderLauncher(staffUser())
    const panel = await openPanel(user)
    await user.type(messageBox(), "Tell me about Dune{Enter}")

    expect(await within(panel).findByText("Dune has two copies on the shelf.")).toBeInTheDocument()
    expect(within(panel).getByRole("list", { name: "Copies" })).toBeInTheDocument()
    expect(within(panel).queryByRole("list", { name: "1 book" })).not.toBeInTheDocument()
    expect(within(panel).getAllByRole("link", { name: "Dune" })).toHaveLength(1)
    // The stored conversation is collapsed too, so a reload shows the same.
    const kinds = storedConversation("user-staff").items.map((item) =>
      item.kind === "result" ? item.display.kind : item.kind,
    )
    expect(kinds).toEqual(["user", "book", "assistant"])
  })

  it("confirms a streamed proposal without reading it again, and keeps how it ended for the tab", async () => {
    vi.useFakeTimers({ toFake: ["Date"] })
    vi.setSystemTime(new Date("2026-09-19T12:01:00Z"))
    const confirmed = proposal({
      status: "confirmed",
      resolved_at: "2026-09-19T12:01:30Z",
      loan: loan({ id: "loan-9", due_at: "2026-10-03T23:59:59Z" }),
    })
    const fetchMock = stubApi({
      "GET /api/copilot/config": () => config({ face: "staff", examples: [] }),
      "POST /api/copilot/chat": () =>
        replyWith(
          sse(
            ["conversation", { conversation_id: "conv-1" }],
            ["result", { tool: "prepare_borrow", display: { kind: "proposal", proposal: proposal() } }],
            ["message", { text: "The card is ready for you to confirm." }],
            ["done", {}],
          ),
        ),
      "POST /api/copilot/proposals/proposal-1/confirm": () => confirmed,
    })
    const user = userEvent.setup()

    const first = renderLauncher(staffUser())
    const panel = await openPanel(user)
    await user.type(messageBox(), "Borrow The Hobbit for Maya Hassan{Enter}")
    const card = await within(panel).findByRole("article", { name: "Proposed borrow" })
    await user.click(within(card).getByRole("button", { name: "Confirm" }))

    const outcome = `Borrowed, due ${formatDueDate("2026-10-03T23:59:59Z")}`
    expect(await within(card).findByText(outcome)).toBeInTheDocument()
    expect(requestsTo(fetchMock, "GET /api/copilot/proposals/proposal-1")).toHaveLength(0)
    await waitFor(() => expect(storedProposalStatus("user-staff")).toBe("confirmed"))
    first.unmount()

    // After a reload the card shows the outcome from storage, with no request.
    renderLauncher(staffUser())
    const reopened = await openPanel(user)
    expect(within(reopened).getByText(outcome)).toBeInTheDocument()
    expect(requestsTo(fetchMock, "GET /api/copilot/proposals/proposal-1")).toHaveLength(0)
  })

  it("reads a stored pending proposal once when the panel opens, and stores how it ended", async () => {
    vi.useFakeTimers({ toFake: ["Date"] })
    vi.setSystemTime(new Date("2026-09-19T12:01:00Z"))
    const stored: Conversation = {
      conversationId: "conv-1",
      items: [
        { id: "1", kind: "user", text: "Borrow The Hobbit for Maya Hassan" },
        { id: "2", kind: "result", tool: "prepare_borrow", display: { kind: "proposal", proposal: proposal() } },
      ],
    }
    sessionStorage.setItem("library.copilot.user-staff", JSON.stringify(stored))
    const fetchMock = stubApi({
      "GET /api/copilot/config": () => config({ face: "staff", examples: [] }),
      "GET /api/copilot/proposals/proposal-1": () =>
        proposal({ status: "cancelled", resolved_at: "2026-09-19T12:00:30Z" }),
    })
    const user = userEvent.setup()

    renderLauncher(staffUser())
    const panel = await openPanel(user)

    expect(await within(panel).findByText("Cancelled. Nothing changed.")).toBeInTheDocument()
    expect(requestsTo(fetchMock, "GET /api/copilot/proposals/proposal-1")).toHaveLength(1)
    await waitFor(() => expect(storedProposalStatus("user-staff")).toBe("cancelled"))
  })
})
