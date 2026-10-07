export interface Project { id: string; name: string; agent_count: number; project_type?: string }

export type UserRole = "admin" | "security" | "developer" | "viewer" | null

export interface NotificationItem {
  id: string
  title: string
  tone: "warn" | "err" | "ok" | "info"
  desc: string
  time: string
  unread: boolean
  href?: string
  created_at?: string | null
}
