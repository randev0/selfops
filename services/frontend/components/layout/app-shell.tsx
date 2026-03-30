"use client"

import { SidebarProvider, useSidebar } from "./sidebar-context"
import { Sidebar } from "./sidebar"
import { cn } from "@/lib/utils"

interface AppShellProps {
  children: React.ReactNode
}

function AppShellInner({ children }: AppShellProps) {
  const { isOpen, isCollapsed, close } = useSidebar()

  return (
    <div className="flex h-screen bg-zinc-950 overflow-hidden">
      {/* Mobile backdrop — tap outside sidebar to close */}
      {isOpen && (
        <div
          className="fixed inset-0 z-30 bg-black/60 md:hidden"
          onClick={close}
          aria-hidden="true"
        />
      )}

      <Sidebar />

      {/* Main area — margin tracks sidebar width with matching transition */}
      <div
        className={cn(
          "flex flex-1 flex-col min-w-0 overflow-hidden",
          "transition-[margin] duration-200 ease-in-out",
          // Mobile: no left margin (sidebar is overlay)
          "ml-0",
          // Desktop: margin matches sidebar width
          isCollapsed ? "md:ml-14" : "md:ml-64",
        )}
      >
        <main className="flex-1 overflow-y-auto">
          {children}
        </main>
      </div>
    </div>
  )
}

export function AppShell({ children }: AppShellProps) {
  return (
    <SidebarProvider>
      <AppShellInner>{children}</AppShellInner>
    </SidebarProvider>
  )
}
