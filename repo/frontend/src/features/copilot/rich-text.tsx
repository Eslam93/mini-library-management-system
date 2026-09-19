import { Fragment } from "react"

import { cn } from "@/lib/utils"

type Block =
  | { type: "paragraph"; lines: string[] }
  | { type: "list"; ordered: boolean; start: number; items: string[] }

const BULLET = /^\s*[-*•]\s+(.*)$/
const NUMBERED = /^\s*(\d+)[.)]\s+(.*)$/
const HEADING = /^\s*#{1,6}\s+(.*)$/

/**
 * Splits the text into paragraphs (separated by blank lines) and lists (lines
 * starting with "-", "*" or "1."). A heading line becomes a bold line.
 */
function toBlocks(text: string): Block[] {
  const blocks: Block[] = []
  let current: Block | null = null

  for (const raw of text.split(/\r\n|\r|\n/)) {
    const line = raw.trimEnd()
    if (line.trim() === "") {
      current = null
      continue
    }

    const numbered = NUMBERED.exec(line)
    const bullet = numbered ? null : BULLET.exec(line)
    if (numbered || bullet) {
      const ordered = numbered !== null
      const item = numbered ? numbered[2] : (bullet?.[1] ?? "")
      if (current?.type === "list" && current.ordered === ordered) {
        current.items.push(item)
      } else {
        current = { type: "list", ordered, start: numbered ? Number(numbered[1]) : 1, items: [item] }
        blocks.push(current)
      }
      continue
    }

    const heading = HEADING.exec(line)
    const content = heading ? `**${heading[1].replaceAll("**", "")}**` : line
    if (current?.type === "paragraph") {
      current.lines.push(content)
    } else {
      current = { type: "paragraph", lines: [content] }
      blocks.push(current)
    }
  }
  return blocks
}

// ***bold italic*** first, then **bold**, which may hold *italic* inside.
const STRONG = /\*\*\*(.+?)\*\*\*|\*\*(.+?)\*\*/g
// A single-asterisk run that starts and ends next to a word, so "2 * 3" stays as it is.
const ITALIC = /(?<![*\w])\*(?![\s*])([^*]+?)(?<!\s)\*(?![*\w])/g

function Italics({ text }: { text: string }) {
  return text
    .split(ITALIC)
    .map((piece, index) => (index % 2 === 1 ? <em key={index}>{piece}</em> : piece))
}

/**
 * Text with **bold**, *italic* and ***bold italic*** runs. Everything else
 * stays plain text: nothing is read as HTML.
 */
function Inline({ text }: { text: string }) {
  const nodes = []
  let last = 0
  for (const match of text.matchAll(STRONG)) {
    const [whole, boldItalic, bold] = match
    nodes.push(<Italics key={`text-${last}`} text={text.slice(last, match.index)} />)
    nodes.push(
      <strong key={`strong-${match.index}`}>
        {boldItalic !== undefined ? <em>{boldItalic}</em> : <Italics text={bold} />}
      </strong>,
    )
    last = match.index + whole.length
  }
  nodes.push(<Italics key={`text-${last}`} text={text.slice(last)} />)
  return nodes
}

/** The assistant's reply with light formatting: paragraphs, lists, bold and italic. */
export function RichText({ text, className }: { text: string; className?: string }) {
  return (
    <div className={cn("space-y-2 text-sm leading-relaxed break-words", className)}>
      {toBlocks(text).map((block, index) => {
        if (block.type === "paragraph") {
          return (
            <p key={index}>
              {block.lines.map((line, lineIndex) => (
                <Fragment key={lineIndex}>
                  {lineIndex > 0 && <br />}
                  <Inline text={line} />
                </Fragment>
              ))}
            </p>
          )
        }
        const items = block.items.map((item, itemIndex) => (
          <li key={itemIndex}>
            <Inline text={item} />
          </li>
        ))
        return block.ordered ? (
          <ol key={index} start={block.start} className="list-decimal space-y-1 pl-5">
            {items}
          </ol>
        ) : (
          <ul key={index} className="list-disc space-y-1 pl-5">
            {items}
          </ul>
        )
      })}
    </div>
  )
}
