import './globals.css'
import { Space_Grotesk } from 'next/font/google'

const space = Space_Grotesk({ subsets: ['latin'] })

export const metadata = {
  title: 'ViddyScribe',
  description: 'Generate Audio-described videos with AI',
}

export default function RootLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return (
    <html lang="en">
      <body className={space.className}>{children}</body>
    </html>
  )
}
