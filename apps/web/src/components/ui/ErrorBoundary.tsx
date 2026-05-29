"use client"

import { Component, type ErrorInfo, type ReactNode } from "react"

interface Props {
  children: ReactNode
  fallback?: ReactNode
}

interface State {
  hasError: boolean
  message: string
}

export default class ErrorBoundary extends Component<Props, State> {
  constructor(props: Props) {
    super(props)
    this.state = { hasError: false, message: "" }
  }

  static getDerivedStateFromError(error: unknown): State {
    const message = error instanceof Error ? error.message : String(error)
    return { hasError: true, message }
  }

  componentDidCatch(error: unknown, info: ErrorInfo) {
    console.error("[ErrorBoundary]", error, info.componentStack)
  }

  render() {
    if (this.state.hasError) {
      if (this.props.fallback) return this.props.fallback
      return (
        <div className="flex items-center justify-center min-h-[200px] px-6 py-10">
          <div className="rounded-xl border border-red-100 bg-red-50 px-6 py-5 max-w-md text-center">
            <p className="text-sm font-medium text-red-700 mb-1">Something went wrong</p>
            <p className="text-xs text-red-500 font-mono break-all">{this.state.message}</p>
            <button
              onClick={() => this.setState({ hasError: false, message: "" })}
              className="mt-4 text-xs text-red-600 underline hover:text-red-800"
            >
              Try again
            </button>
          </div>
        </div>
      )
    }
    return this.props.children
  }
}
