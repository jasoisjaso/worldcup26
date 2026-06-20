import LoginForm from "./LoginForm"

export const dynamic = "force-dynamic"

export default function AdminLoginPage() {
  return (
    <div className="min-h-screen flex items-center justify-center p-6">
      <div className="w-full max-w-sm">
        <div className="mb-6">
          <div className="text-xs uppercase tracking-[0.18em] text-amber-500/80 mb-1">
            WC26 · Internal
          </div>
          <h1 className="font-display text-2xl text-slate-100">Admin sign-in</h1>
          <p className="text-sm text-slate-400 mt-1">
            Paste the admin token. Cookie lasts 12h on this device.
          </p>
        </div>
        <LoginForm />
      </div>
    </div>
  )
}
