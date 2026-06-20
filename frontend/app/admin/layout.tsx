import type { Metadata } from "next"

// Hard-stop the admin surface from indexing. The cookie gate keeps anonymous
// traffic out, but bot crawlers should never have known the path existed.
export const metadata: Metadata = {
  robots: {
    index: false,
    follow: false,
    nocache: true,
    googleBot: { index: false, follow: false, noimageindex: true },
  },
}

export default function AdminLayout({ children }: { children: React.ReactNode }) {
  return <div className="min-h-screen bg-surface-0">{children}</div>
}
