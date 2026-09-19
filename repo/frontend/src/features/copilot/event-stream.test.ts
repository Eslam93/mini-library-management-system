import { describe, expect, it } from "vitest"

import { createEventParser, type RawEvent } from "@/features/copilot/event-stream"

function parse(pieces: string[]): RawEvent[] {
  const events: RawEvent[] = []
  const parser = createEventParser((event) => events.push(event))
  for (const piece of pieces) parser.push(piece)
  parser.end()
  return events
}

/** The text cut into pieces of `size` characters. */
function cut(text: string, size: number): string[] {
  const pieces: string[] = []
  for (let index = 0; index < text.length; index += size) pieces.push(text.slice(index, index + size))
  return pieces
}

const STREAM =
  'event: status\ndata: {"text":"Searching the catalog"}\n\n' +
  ": keep-alive\n\n" +
  'event: message\ndata: {"text":"Found it"}\n\n' +
  "event: done\ndata: {}\n\n"

const EXPECTED: RawEvent[] = [
  { event: "status", data: '{"text":"Searching the catalog"}' },
  { event: "message", data: '{"text":"Found it"}' },
  { event: "done", data: "{}" },
]

describe("createEventParser", () => {
  it.each([1, 2, 3, 7, STREAM.length])("reads the same events when the text arrives %i characters at a time", (size) => {
    expect(parse(cut(STREAM, size))).toEqual(EXPECTED)
  })

  it("reads \\r\\n line endings, even when a piece ends between the two characters", () => {
    const text = STREAM.replaceAll("\n", "\r\n")
    const splitInsidePair = text.indexOf("\r\n") + 1

    expect(parse([text.slice(0, splitInsidePair), text.slice(splitInsidePair)])).toEqual(EXPECTED)
    expect(parse(cut(text, 1))).toEqual(EXPECTED)
  })

  it("joins data lines, names an unnamed event message, and keeps a last event without its blank line", () => {
    expect(parse(["data: first\ndata:second\n\n", "event: done"])).toEqual([
      { event: "message", data: "first\nsecond" },
      { event: "done", data: "" },
    ])
  })
})
