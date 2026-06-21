// Sentry server-side init for Node runtime routes (default API + RSC).
// Loaded via instrumentation.ts. Without a DSN this is a no-op.
import * as Sentry from "@sentry/nextjs"

const dsn = process.env.SENTRY_DSN || process.env.NEXT_PUBLIC_SENTRY_DSN
if (dsn) {
  Sentry.init({
    dsn,
    release: process.env.SENTRY_RELEASE,
    tracesSampleRate: 0.05,
  })
}
