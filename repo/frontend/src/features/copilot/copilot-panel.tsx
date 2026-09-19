import { useEffect, useRef } from "react"
import { Check, CircleAlert, Loader2, RefreshCw, Search, Sparkles, SquarePen } from "lucide-react"
import { Link } from "react-router"

import { Button } from "@/components/ui/button"
import { SheetDescription, SheetHeader, SheetTitle } from "@/components/ui/sheet"
import type { ChatItem } from "@/features/copilot/conversation"
import { CopilotComposer } from "@/features/copilot/copilot-composer"
import type { CopilotChat } from "@/features/copilot/hooks"
import { ResultDisplay } from "@/features/copilot/result-display"
import { RichText } from "@/features/copilot/rich-text"
import { COPILOT_ERROR_CODES, type CopilotConfig, type CopilotFace } from "@/features/copilot/types"

type FaceText = {
  title: string
  description: string
  intro: string
  placeholder: string
}

const faceText: Record<CopilotFace, FaceText> = {
  member: {
    title: "Library assistant",
    description: "Books, availability and your loans",
    intro: "Ask about books and your loans",
    placeholder: "Ask about books, authors or your loans",
  },
  staff: {
    title: "Staff Copilot",
    description: "Books, members, loans, Borrow and Return, and the library's figures",
    intro: "Ask about the catalog, members, loans or how the library is used",
    placeholder: "Ask about books, members, loans or figures",
  },
}

type CopilotPanelProps = {
  face: CopilotFace
  /** Undefined while it loads. */
  config: CopilotConfig | undefined
  configFailed: boolean
  onRetryConfig: () => void
  chat: CopilotChat
  /** A link in the panel leads to a page: the panel closes. */
  onNavigate: () => void
}

/** The Copilot's side panel: the conversation, its results, and the message box. */
export function CopilotPanel({
  face,
  config,
  configFailed,
  onRetryConfig,
  chat,
  onNavigate,
}: CopilotPanelProps) {
  const text = faceText[face]
  const unavailable = config?.available === false || chat.unavailable
  const scrollRef = useRef<HTMLDivElement>(null)
  const lastItem = chat.items.at(-1)

  // Keep the newest part of the conversation in view.
  useEffect(() => {
    const scroller = scrollRef.current
    if (scroller) scroller.scrollTop = scroller.scrollHeight
  }, [chat.items.length, chat.running])

  let intro = null
  if (chat.items.length === 0 && !unavailable) {
    if (config) {
      intro = <Examples title={text.intro} examples={config.examples} onAsk={chat.send} />
    } else if (configFailed) {
      intro = <ConfigFailed onRetry={onRetryConfig} />
    } else {
      intro = <Working text="Loading the assistant" />
    }
  }

  return (
    <>
      <SheetHeader className="flex-row items-center justify-between gap-2 border-b py-3 pr-12 pl-4">
        <div className="min-w-0">
          <SheetTitle className="flex items-center gap-2">
            <Sparkles aria-hidden className="size-4 text-primary" />
            {text.title}
          </SheetTitle>
          <SheetDescription className="text-xs">{text.description}</SheetDescription>
        </div>
        <Button
          variant="ghost"
          size="sm"
          onClick={chat.reset}
          disabled={chat.items.length === 0 && !chat.running}
        >
          <SquarePen aria-hidden />
          <span className="sr-only sm:not-sr-only">New conversation</span>
        </Button>
      </SheetHeader>

      <div ref={scrollRef} className="flex-1 overflow-y-auto px-4 py-4">
        {intro}
        {chat.items.length > 0 && (
          <div role="log" aria-label="Conversation" className="space-y-4">
            {chat.items.map((item) => (
              <ChatEntry
                key={item.id}
                item={item}
                face={face}
                current={item === lastItem}
                running={chat.running}
                onRetry={chat.retry}
                onAsk={chat.send}
                onNavigate={onNavigate}
              />
            ))}
            {chat.running && lastItem?.kind !== "status" && <Working text="Working on it" />}
          </div>
        )}
        {unavailable && <Unavailable reason={config?.reason ?? null} onNavigate={onNavigate} />}
      </div>

      <CopilotComposer
        disabled={unavailable}
        running={chat.running}
        placeholder={unavailable ? "The assistant is unavailable" : text.placeholder}
        onSend={chat.send}
        onStop={chat.stop}
      />
    </>
  )
}

type ChatEntryProps = {
  item: ChatItem
  face: CopilotFace
  /** The newest entry: a status line shows the spinner, an error offers to try again. */
  current: boolean
  running: boolean
  onRetry: () => void
  onAsk: (message: string) => void
  onNavigate: () => void
}

function ChatEntry({ item, face, current, running, onRetry, onAsk, onNavigate }: ChatEntryProps) {
  switch (item.kind) {
    case "user":
      return (
        <p className="ml-auto w-fit max-w-[85%] rounded-2xl rounded-br-sm bg-primary px-3 py-2 text-sm break-words whitespace-pre-wrap text-primary-foreground">
          <span className="sr-only">You: </span>
          {item.text}
        </p>
      )
    case "status":
      return current && running ? (
        <Working text={item.text} />
      ) : (
        <p className="flex items-center gap-2 text-xs text-muted-foreground">
          <Check aria-hidden className="size-3.5" />
          {item.text}
        </p>
      )
    case "result":
      return (
        <ResultDisplay display={item.display} face={face} onNavigate={onNavigate} onAsk={onAsk} busy={running} />
      )
    case "assistant":
      return (
        <div>
          <span className="sr-only">Assistant: </span>
          <RichText text={item.text} />
        </div>
      )
    case "error":
      return (
        <TurnError
          code={item.code}
          message={item.message}
          onRetry={current && !running ? onRetry : undefined}
        />
      )
    case "stopped":
      return <p className="text-xs text-muted-foreground">You stopped this answer.</p>
  }
}

/** A subtle line with a spinner while something is on its way. */
function Working({ text }: { text: string }) {
  return (
    <p role="status" className="flex items-center gap-2 text-xs text-muted-foreground">
      <Loader2 aria-hidden className="size-3.5 animate-spin motion-reduce:animate-none" />
      {text}
    </p>
  )
}

function errorTitle(code: string) {
  if (code === COPILOT_ERROR_CODES.rateLimited) return "Too many messages"
  if (code === COPILOT_ERROR_CODES.timeout) return "The answer took too long"
  return "The assistant could not answer"
}

function TurnError({ code, message, onRetry }: { code: string; message: string; onRetry?: () => void }) {
  const rateLimited = code === COPILOT_ERROR_CODES.rateLimited
  return (
    <div
      role="alert"
      className="space-y-2 rounded-lg border border-destructive/30 bg-destructive/5 px-3 py-2.5 text-sm"
    >
      <p className="flex items-center gap-2 font-medium text-destructive">
        <CircleAlert aria-hidden className="size-4 shrink-0" />
        {errorTitle(code)}
      </p>
      <p className="text-muted-foreground">
        {message}
        {rateLimited && " Wait a minute before sending another message."}
      </p>
      {onRetry && (
        <Button variant="outline" size="sm" onClick={onRetry}>
          <RefreshCw aria-hidden />
          Try again
        </Button>
      )}
    </div>
  )
}

function Examples({
  title,
  examples,
  onAsk,
}: {
  title: string
  examples: string[]
  onAsk: (message: string) => void
}) {
  return (
    <div className="flex flex-col items-center gap-4 py-6 text-center">
      <div className="flex size-12 items-center justify-center rounded-full bg-accent text-accent-foreground">
        <Sparkles aria-hidden className="size-6" />
      </div>
      <div className="space-y-1">
        <h3 className="text-base font-semibold">{title}</h3>
        <p className="text-sm text-muted-foreground">
          Ask in your own words, or start with one of these.
        </p>
      </div>
      {examples.length > 0 && (
        <ul aria-label="Example questions" className="flex flex-wrap justify-center gap-2">
          {examples.map((example) => (
            <li key={example}>
              <Button
                variant="outline"
                size="sm"
                className="h-auto rounded-full py-1.5 text-left whitespace-normal"
                onClick={() => onAsk(example)}
              >
                {example}
              </Button>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}

function ConfigFailed({ onRetry }: { onRetry: () => void }) {
  return (
    <div role="alert" className="flex flex-col items-center gap-3 py-6 text-center text-sm">
      <p className="font-medium">Could not load the assistant</p>
      <p className="text-muted-foreground">Check your connection and try again.</p>
      <Button variant="outline" size="sm" onClick={onRetry}>
        <RefreshCw aria-hidden />
        Try again
      </Button>
    </div>
  )
}

/** Shown instead of the conversation's next answer when the assistant is off: the rest of the app still works. */
function Unavailable({ reason, onNavigate }: { reason: string | null; onNavigate: () => void }) {
  return (
    <div role="status" className="mt-4 space-y-3 rounded-lg border border-dashed bg-muted/40 p-4 text-sm first:mt-0">
      <p className="font-medium">The assistant is unavailable right now</p>
      {reason && <p className="text-muted-foreground">{reason}</p>}
      <p className="text-muted-foreground">
        Everything else in the library works as usual, and you can search the catalog yourself.
      </p>
      <Button asChild variant="outline" size="sm">
        <Link to="/catalog" onClick={onNavigate}>
          <Search aria-hidden />
          Search the catalog
        </Link>
      </Button>
    </div>
  )
}
