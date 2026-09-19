import { useEffect, useId, useRef, useState } from "react"
import { ArrowUp, Square } from "lucide-react"

import { Button } from "@/components/ui/button"
import { Label } from "@/components/ui/label"
import { Textarea } from "@/components/ui/textarea"

/** The longest message the API accepts. */
const MAX_MESSAGE_LENGTH = 2000

type CopilotComposerProps = {
  /** The assistant cannot take messages at all. */
  disabled: boolean
  /** A turn is streaming: the box waits and Send becomes Stop. */
  running: boolean
  placeholder: string
  onSend: (message: string) => void
  onStop: () => void
}

/** The message box. Enter sends; Shift+Enter starts a new line. */
export function CopilotComposer({
  disabled,
  running,
  placeholder,
  onSend,
  onStop,
}: CopilotComposerProps) {
  const id = useId()
  const hintId = useId()
  const [draft, setDraft] = useState("")
  const inputRef = useRef<HTMLTextAreaElement>(null)
  const wasRunning = useRef(running)

  // The box is disabled during a turn, which drops its focus: give it back after.
  useEffect(() => {
    if (wasRunning.current && !running) inputRef.current?.focus()
    wasRunning.current = running
  }, [running])

  function submit() {
    const message = draft.trim()
    if (!message || running || disabled) return
    onSend(message)
    setDraft("")
  }

  return (
    <form
      className="border-t bg-background p-3"
      onSubmit={(event) => {
        event.preventDefault()
        submit()
      }}
    >
      <Label htmlFor={id} className="sr-only">
        Message
      </Label>
      <div className="flex items-end gap-2">
        <Textarea
          id={id}
          ref={inputRef}
          // The panel opens to type in: the box takes the focus the dialog would give its first button.
          autoFocus
          rows={1}
          value={draft}
          maxLength={MAX_MESSAGE_LENGTH}
          placeholder={placeholder}
          disabled={disabled || running}
          aria-describedby={hintId}
          onChange={(event) => setDraft(event.target.value)}
          onKeyDown={(event) => {
            // While an input method is composing, Enter confirms the text instead.
            if (event.key !== "Enter" || event.shiftKey || event.nativeEvent.isComposing) return
            event.preventDefault()
            submit()
          }}
          className="max-h-40 min-h-10 resize-none overflow-y-auto"
        />
        {running ? (
          <Button type="button" variant="outline" size="icon" onClick={onStop}>
            <Square aria-hidden className="fill-current" />
            <span className="sr-only">Stop</span>
          </Button>
        ) : (
          <Button type="submit" size="icon" disabled={disabled || draft.trim() === ""}>
            <ArrowUp aria-hidden />
            <span className="sr-only">Send</span>
          </Button>
        )}
      </div>
      <p id={hintId} className="mt-1.5 text-xs text-muted-foreground">
        Enter sends, Shift+Enter adds a line.
      </p>
    </form>
  )
}
