import { SignIn } from "@clerk/nextjs"

export default function SignInPage() {
  return (
    <div className="min-h-screen flex items-center justify-center bg-stone-50">
      <div className="space-y-4 text-center">
        <div className="mb-6">
          <h1 className="text-2xl font-bold text-stone-900">Delegators</h1>
          <p className="text-sm text-stone-500 mt-1">AI agent orchestration for engineering teams</p>
        </div>
        <SignIn />
      </div>
    </div>
  )
}
