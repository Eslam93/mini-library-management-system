import { Component, type ErrorInfo, type ReactNode } from "react"

import { ErrorState } from "@/components/states/error-state"

type ErrorBoundaryProps = {
  children: ReactNode
  /** A change to this value clears a caught error, for example a new route path. */
  resetKey?: unknown
  fallback?: (error: Error, reset: () => void) => ReactNode
}

type ErrorBoundaryState = {
  error: Error | null
}

/** Catches a render crash in its subtree and shows a fallback instead of a blank page. */
export class ErrorBoundary extends Component<ErrorBoundaryProps, ErrorBoundaryState> {
  state: ErrorBoundaryState = { error: null }

  static getDerivedStateFromError(error: unknown): ErrorBoundaryState {
    return { error: error instanceof Error ? error : new Error(String(error)) }
  }

  componentDidCatch(error: unknown, info: ErrorInfo) {
    console.error("A view crashed while rendering.", error, info.componentStack)
  }

  componentDidUpdate(previous: ErrorBoundaryProps) {
    // Clear the error without remounting children that are still healthy.
    if (this.state.error && !Object.is(previous.resetKey, this.props.resetKey)) {
      this.reset()
    }
  }

  reset = () => {
    this.setState({ error: null })
  }

  render() {
    const { error } = this.state
    if (!error) return this.props.children
    if (this.props.fallback) return this.props.fallback(error, this.reset)
    return <ErrorState title="This page failed to load" error={error} onRetry={this.reset} />
  }
}
