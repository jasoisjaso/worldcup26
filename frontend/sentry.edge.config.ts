// Sentry edge-runtime init (middleware + edge-runtime routes). Same DSN as
// server; the Edge runtime needs its own init because it runs in a separate
// JS engine context.
import * as Sentry from "@sentry/nextjs"

const dsn = process.env.SENTRY_DSN || process.env.NEXT_PUBLIC_SENTRY_DSN
if (dsn) {
  Sentry.init({
    dsn,
    release: process.env.SENTRY_RELEASE,
    tracesSampleRate: 0.05,
  })
}
