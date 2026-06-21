// Next.js 14 instrumentation hook — loaded once at server startup. We dispatch
// to the right Sentry config based on the runtime so the Node-only modules in
// sentry.server.config don't get pulled into the Edge bundle.
export async function register() {
  if (process.env.NEXT_RUNTIME === "nodejs") {
    await import("./sentry.server.config")
  }
  if (process.env.NEXT_RUNTIME === "edge") {
    await import("./sentry.edge.config")
  }
}
