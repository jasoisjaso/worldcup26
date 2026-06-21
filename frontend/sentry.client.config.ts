// Sentry client-side (browser) init. Loaded by Next.js automatically when
// this file is present at the project root and @sentry/nextjs is installed.
// DSN flows in through NEXT_PUBLIC_SENTRY_DSN at build time (set as a
// Docker build-arg in compose); when unset the SDK is a no-op so dev
// builds don't ever leak events.
import * as Sentry from "@sentry/nextjs"

const dsn = process.env.NEXT_PUBLIC_SENTRY_DSN
if (dsn) {
  Sentry.init({
    dsn,
    release: process.env.SENTRY_RELEASE,
    tracesSampleRate: 0.05,
    replaysOnErrorSampleRate: 0,
    replaysSessionSampleRate: 0,
  })
}
