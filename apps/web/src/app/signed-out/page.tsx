export default function SignedOut() {
  return <main className="mx-auto max-w-md p-8 space-y-4">
    <h1 className="text-xl font-semibold">Signed out of Conduct</h1>
    <a href="/oauth2/start?rd=%2Ftheguard" className="underline">Sign in</a>
  </main>
}
