"use client"

import { createContext, useContext, useState, useEffect } from "react"
import { usePathname } from "next/navigation"

interface SidebarContextValue {
  /** Mobile drawer open state */
  isOpen: boolean
  /** Desktop collapsed (icon-only) state */
  isCollapsed: boolean
  toggle: () => void
  close: () => void
  toggleCollapsed: () => void
}

const SidebarContext = createContext<SidebarContextValue>({
  isOpen: false,
  isCollapsed: false,
  toggle: () => {},
  close: () => {},
  toggleCollapsed: () => {},
})

export function SidebarProvider({ children }: { children: React.ReactNode }) {
  const [isOpen, setIsOpen] = useState(false)
  const [isCollapsed, setIsCollapsed] = useState(false)
  const pathname = usePathname()

  // Restore collapsed preference from localStorage
  useEffect(() => {
    const stored = localStorage.getItem("sidebar-collapsed")
    if (stored === "true") setIsCollapsed(true)
  }, [])

  // Close mobile drawer on navigation
  useEffect(() => {
    setIsOpen(false)
  }, [pathname])

  const toggleCollapsed = () => {
    setIsCollapsed((prev) => {
      localStorage.setItem("sidebar-collapsed", String(!prev))
      return !prev
    })
  }

  return (
    <SidebarContext.Provider
      value={{
        isOpen,
        isCollapsed,
        toggle: () => setIsOpen((o) => !o),
        close: () => setIsOpen(false),
        toggleCollapsed,
      }}
    >
      {children}
    </SidebarContext.Provider>
  )
}

export const useSidebar = () => useContext(SidebarContext)
