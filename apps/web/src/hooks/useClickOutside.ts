// Platform-wide click-outside hook — attaches a mousedown listener that
// fires the callback when the click lands outside the returned ref's
// subtree. Native handler-only; safe on the server (only wires up in the
// effect, which is client-side). Use for popovers, dropdowns, menus.
//
// Introduced with #1982 (Guard Activity toolbar consolidation) so multiple
// dropdown-style primitives can share one implementation instead of each
// re-implementing the pattern.

"use client"

import { useEffect, useRef } from "react"

export function useClickOutside<T extends HTMLElement>(onOutside: () => void) {
  const ref = useRef<T>(null)
  useEffect(() => {
    function handle(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) onOutside()
    }
    window.addEventListener("mousedown", handle)
    return () => window.removeEventListener("mousedown", handle)
  }, [onOutside])
  return ref
}
