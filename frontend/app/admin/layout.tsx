import type { Metadata, Viewport } from "next"

// Hard-stop the admin surface from indexing. The cookie gate keeps anonymous
// traffic out, but bot crawlers should never have known the path existed.
//
// The manifest override is what makes "Add to Home Screen" on /admin install
// a SEPARATE app from the public site. Root layout points at /manifest.json
// (start_url: "/"); without overriding here, adding /admin to the home screen
// would still launch the public homepage. /admin-manifest.json sets
// start_url + scope to /admin so the installed icon opens straight into the
// dashboard, with its own "WC26 Ops" label + amber theme to visually
// distinguish from the public app icon.
export const metadata: Metadata = {
  manifest: "/admin-manifest.json",
  title: "WC26 Ops",
  robots: {
    index: false,
    follow: false,
    nocache: true,
    googleBot: { index: false, follow: false, noimageindex: true },
  },
}

// Theme colour must be set on viewport (not metadata) per Next.js 14+;
// matches admin-manifest.json so the iOS/Android status bar tints amber
// when launched from the home-screen icon.
export const viewport: Viewport = {
  themeColor: "#f59e0b",
}

export default function AdminLayout({ children }: { children: React.ReactNode }) {
  return <div className="min-h-screen bg-surface-0">{children}</div>
}
