import { Inter, Fira_Code } from 'next/font/google'
import Providers from '@/components/Providers'
import '@/styles/globals.css'

const inter = Inter({
  subsets: ['latin'],
  variable: '--font-inter',
})

const firaCode = Fira_Code({
  subsets: ['latin'],
  weight: ['400', '500', '600', '700'],
  variable: '--font-mono',
})

export const metadata = {
  title: 'AutoOverlay AI | Track 4',
  description: 'AI-driven income strategies on your existing portfolio',
}

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" suppressHydrationWarning>
      <body className={`${inter.variable} ${firaCode.variable} antialiased`}>
        <Providers>{children}</Providers>
      </body>
    </html>
  )
}
