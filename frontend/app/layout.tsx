import type { Metadata } from 'next'
import { Inter } from 'next/font/google'
import './styles/globals.css'

const inter = Inter({ subsets: ['latin'], variable: '--font-inter' })

export const metadata: Metadata = {
  title: {
    default: 'AutoOverlay AI | Options Alpha',
    template: '%s | AutoOverlay AI',
  },
  description: 'Algorithmic options overlay dashboard.',
  icons: {
    icon: '/logo.png',
    apple: '/logo.png',
  },
}

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" suppressHydrationWarning className={inter.variable}>
      <body className="bg-[#020617] text-[#f8fafc] antialiased">
        {children}
      </body>
    </html>
  )
}
