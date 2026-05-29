"use client"

import { useEffect } from "react"

export type ToastType = "error" | "success" | "info"

export interface ToastData {
  message: string
  type?: ToastType
}

interface ToastProps extends ToastData {
  onDismiss: () => void
}

const TYPE_STYLES: Record<ToastType, string> = {
  error:   "bg-red-50   border-red-200   text-red-800",
  success: "bg-emerald-50 border-emerald-200 text-emerald-800",
  info:    "bg-stone-50  border-stone-200  text-stone-700",
}

const TYPE_ICONS: Record<ToastType, string> = {
  error:   "✕",
  success: "✓",
  info:    "ℹ",
}

export default function Toast({ message, type = "error", onDismiss }: ToastProps) {
  useEffect(() => {
    const t = setTimeout(onDismiss, 5000)
    return () => clearTimeout(t)
  }, [onDismiss])

  return (
    <div
      role="alert"
      aria-live="assertive"
      className={`fixed bottom-6 left-1/2 -translate-x-1/2 z-[9999] flex items-center gap-3 rounded-xl border px-4 py-3 shadow-lg text-sm font-medium min-w-[280px] max-w-[480px] ${TYPE_STYLES[type]}`}
    >
      <span aria-hidden="true" className="shrink-0 text-base leading-none">{TYPE_ICONS[type]}</span>
      <span className="flex-1">{message}</span>
      <button
        onClick={onDismiss}
        aria-label="Dismiss notification"
        className="shrink-0 opacity-50 hover:opacity-100 transition-opacity text-xs leading-none"
      >
        ✕
      </button>
    </div>
  )
}
