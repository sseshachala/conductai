export const metadata = {
  title: "Lens | Conduct",
  description: "Lens is the conversational interface built into the Conduct app.",
}

export default function LensHoldingPage() {
  return (
    <div className="min-h-[60vh] flex flex-col items-center justify-center px-6 text-center">
      <h1 className="text-2xl font-bold text-stone-900 mb-3">Lens</h1>
      <p className="text-stone-500 max-w-sm leading-relaxed mb-6">
        Lens is our chat surface for the app. It is not a standalone product.
        Docs live at{" "}
        <a href="/docs/lens" className="text-indigo-600 underline underline-offset-2 hover:text-indigo-800">
          /docs/lens
        </a>
        .
      </p>
      <a
        href="/docs/lens"
        className="text-sm font-semibold text-indigo-600 hover:text-indigo-800 transition-colors"
      >
        Go to Lens docs
      </a>
    </div>
  )
}
