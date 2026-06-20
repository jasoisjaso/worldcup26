import { cookies } from "next/headers"
import { redirect } from "next/navigation"
import AdminDashboard from "./AdminDashboard"

export const dynamic = "force-dynamic"

export default function AdminPage() {
  const cookie = cookies().get("wc26_admin")
  if (!cookie?.value) {
    redirect("/admin/login")
  }
  return <AdminDashboard />
}
