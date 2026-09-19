import { useEffect, useState } from "react"

/**
 * The current time in milliseconds, refreshed every `intervalMs` so relative times stay true.
 * Never earlier than `atLeast`, such as when the data on screen was fetched: a list refreshed
 * between two ticks would otherwise show its newest entry as in the future ("in 40 seconds").
 */
export function useNow(intervalMs = 60_000, atLeast = 0): number {
  const [now, setNow] = useState(() => Date.now())

  useEffect(() => {
    const timer = setInterval(() => setNow(Date.now()), intervalMs)
    return () => clearInterval(timer)
  }, [intervalMs])

  return Math.max(now, atLeast)
}
