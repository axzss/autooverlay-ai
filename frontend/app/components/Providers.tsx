'use client'

import { createContext, useContext, useState, ReactNode } from 'react'

interface MobileNavContextValue {
  mobileOpen: boolean
  setMobileOpen: (open: boolean) => void
}

const MobileNavContext = createContext<MobileNavContextValue>({
  mobileOpen: false,
  setMobileOpen: () => {},
})

export function useMobileNav() {
  return useContext(MobileNavContext)
}

export default function Providers({ children }: { children: ReactNode }) {
  const [mobileOpen, setMobileOpen] = useState(false)

  return (
    <MobileNavContext.Provider value={{ mobileOpen, setMobileOpen }}>
      {children}
    </MobileNavContext.Provider>
  )
}
