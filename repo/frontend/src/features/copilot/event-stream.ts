/** One server-sent event: its name ("message" when the server gave none) and its data lines joined. */
export type RawEvent = {
  event: string
  data: string
}

const LINE_END = /\r\n|\r|\n/

/**
 * Turns text/event-stream text into events. The text may arrive in pieces
 * cut anywhere, even inside a line or between the two characters of a
 * "\r\n", so a partial line waits in the buffer until the rest arrives.
 */
export function createEventParser(onEvent: (event: RawEvent) => void) {
  let buffer = ""
  let name = ""
  let data: string[] = []

  function dispatch() {
    // The standard drops an event with no data; a named one still counts
    // here, so a bare "event: done" is not lost.
    if (data.length > 0 || name) onEvent({ event: name || "message", data: data.join("\n") })
    name = ""
    data = []
  }

  function readLine(line: string) {
    if (line === "") {
      dispatch()
      return
    }
    // A line starting with a colon is a comment, such as a keep-alive.
    if (line.startsWith(":")) return
    const colon = line.indexOf(":")
    const field = colon === -1 ? line : line.slice(0, colon)
    let value = colon === -1 ? "" : line.slice(colon + 1)
    if (value.startsWith(" ")) value = value.slice(1)
    if (field === "event") name = value
    else if (field === "data") data.push(value)
    // "id" and "retry" only matter for reconnecting, which a POST stream never does.
  }

  return {
    push(text: string) {
      buffer += text
      for (;;) {
        const end = LINE_END.exec(buffer)
        if (!end) return
        // A "\r" at the very end may be the first half of "\r\n".
        if (end[0] === "\r" && end.index === buffer.length - 1) return
        readLine(buffer.slice(0, end.index))
        buffer = buffer.slice(end.index + end[0].length)
      }
    },

    /** The body ended. A last event without its closing blank line still counts. */
    end() {
      const rest = buffer.endsWith("\r") ? buffer.slice(0, -1) : buffer
      buffer = ""
      if (rest) readLine(rest)
      dispatch()
    },
  }
}
