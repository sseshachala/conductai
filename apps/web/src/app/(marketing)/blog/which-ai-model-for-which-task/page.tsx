"use client"

export default function BlogPost() {
  return (
    <div className="min-h-screen bg-white flex flex-col">
      <BlogNav />
      <main className="flex-1">
        <article className="max-w-2xl mx-auto px-6 py-16">
          <div className="mb-10">
            <div className="flex items-center gap-3 mb-6">
              <span className="text-xs font-semibold text-amber-700 bg-amber-50 border border-amber-200 px-2.5 py-1 rounded-full uppercase tracking-widest">
                Guide
              </span>
              <span className="text-xs text-stone-400">June 5, 2026</span>
            </div>
            <h1 className="text-4xl font-bold text-stone-900 leading-tight mb-4">
              Which AI model should you use — and for which task?
            </h1>
            <p className="text-lg text-stone-500 leading-relaxed">
              Claude, GPT-4o, Gemini, DeepSeek, Mistral, Llama — a practical guide for developers on picking the right model for the job. With code examples and a note on why governance matters when you run them all.
            </p>
          </div>

          <hr className="border-stone-100 mb-10" />

          <div className="prose prose-stone prose-sm max-w-none space-y-8 text-stone-700 leading-relaxed">

            <section>
              <h2 className="text-xl font-bold text-stone-900 mb-3">The problem with &quot;just use the best model&quot;</h2>
              <p>
                In 2026 developers have access to 15+ production-quality LLMs. The instinct is to default to the strongest one for everything. That&apos;s expensive and often wrong — a model optimised for long-context reasoning is overkill for a one-line fix, and a fast cheap model is the wrong choice for a complex security audit.
              </p>
              <p className="mt-4">
                The answer is routing. Know what each model is good at. Send the right task to the right model.
              </p>
            </section>

            <section>
              <h2 className="text-xl font-bold text-stone-900 mb-3">The model landscape</h2>
              <p>
                A practical overview of the models available in 2026 and where each one earns its place.
              </p>

              <div className="mt-5 rounded-xl border border-stone-200 overflow-hidden">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="bg-stone-50 border-b border-stone-200">
                      <th className="text-left px-4 py-3 font-semibold text-stone-600">Model</th>
                      <th className="text-left px-4 py-3 font-semibold text-stone-600">Provider</th>
                      <th className="text-left px-4 py-3 font-semibold text-stone-600">Best for</th>
                      <th className="text-left px-4 py-3 font-semibold text-stone-600">Context</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-stone-100">
                    <tr>
                      <td className="px-4 py-3 font-semibold text-stone-800">Claude Opus 4.7</td>
                      <td className="px-4 py-3 text-stone-500">Anthropic</td>
                      <td className="px-4 py-3 text-stone-600">Architecture reviews, complex refactors, security audits, multi-file changes</td>
                      <td className="px-4 py-3 text-stone-500">200k</td>
                    </tr>
                    <tr>
                      <td className="px-4 py-3 font-semibold text-stone-800">Claude Sonnet 4.6</td>
                      <td className="px-4 py-3 text-stone-500">Anthropic</td>
                      <td className="px-4 py-3 text-stone-600">Day-to-day coding, PR reviews, agent loops, RAG pipelines</td>
                      <td className="px-4 py-3 text-stone-500">200k</td>
                    </tr>
                    <tr>
                      <td className="px-4 py-3 font-semibold text-stone-800">Claude Haiku 4.5</td>
                      <td className="px-4 py-3 text-stone-500">Anthropic</td>
                      <td className="px-4 py-3 text-stone-600">Classification, routing, quick lookups, high-volume pipelines</td>
                      <td className="px-4 py-3 text-stone-500">200k</td>
                    </tr>
                    <tr>
                      <td className="px-4 py-3 font-semibold text-stone-800">GPT-4o</td>
                      <td className="px-4 py-3 text-stone-500">OpenAI</td>
                      <td className="px-4 py-3 text-stone-600">Vision tasks, tool-use agents, OpenAI-native integrations</td>
                      <td className="px-4 py-3 text-stone-500">128k</td>
                    </tr>
                    <tr>
                      <td className="px-4 py-3 font-semibold text-stone-800">GPT-4o mini</td>
                      <td className="px-4 py-3 text-stone-500">OpenAI</td>
                      <td className="px-4 py-3 text-stone-600">Simple completions, embeddings, lightweight agents</td>
                      <td className="px-4 py-3 text-stone-500">128k</td>
                    </tr>
                    <tr>
                      <td className="px-4 py-3 font-semibold text-stone-800">o3 / o3-mini</td>
                      <td className="px-4 py-3 text-stone-500">OpenAI</td>
                      <td className="px-4 py-3 text-stone-600">Maths, logic puzzles, step-by-step planning</td>
                      <td className="px-4 py-3 text-stone-500">200k</td>
                    </tr>
                    <tr>
                      <td className="px-4 py-3 font-semibold text-stone-800">Gemini 2.5 Pro</td>
                      <td className="px-4 py-3 text-stone-500">Google</td>
                      <td className="px-4 py-3 text-stone-600">Document analysis, 1M+ token codebases, multimodal</td>
                      <td className="px-4 py-3 text-stone-500">1M</td>
                    </tr>
                    <tr>
                      <td className="px-4 py-3 font-semibold text-stone-800">Gemini Flash 2.0</td>
                      <td className="px-4 py-3 text-stone-500">Google</td>
                      <td className="px-4 py-3 text-stone-600">High-throughput tasks, batch classification</td>
                      <td className="px-4 py-3 text-stone-500">1M</td>
                    </tr>
                    <tr>
                      <td className="px-4 py-3 font-semibold text-stone-800">DeepSeek R1</td>
                      <td className="px-4 py-3 text-stone-500">DeepSeek</td>
                      <td className="px-4 py-3 text-stone-600">Reasoning chains, maths, logic — at open-source cost</td>
                      <td className="px-4 py-3 text-stone-500">128k</td>
                    </tr>
                    <tr>
                      <td className="px-4 py-3 font-semibold text-stone-800">DeepSeek V3</td>
                      <td className="px-4 py-3 text-stone-500">DeepSeek</td>
                      <td className="px-4 py-3 text-stone-600">Code completion, agentic coding tasks</td>
                      <td className="px-4 py-3 text-stone-500">128k</td>
                    </tr>
                    <tr>
                      <td className="px-4 py-3 font-semibold text-stone-800">Mistral Large</td>
                      <td className="px-4 py-3 text-stone-500">Mistral</td>
                      <td className="px-4 py-3 text-stone-600">Regulated industries, EU data residency requirements</td>
                      <td className="px-4 py-3 text-stone-500">128k</td>
                    </tr>
                    <tr>
                      <td className="px-4 py-3 font-semibold text-stone-800">Mistral 7B / 8x7B</td>
                      <td className="px-4 py-3 text-stone-500">Mistral</td>
                      <td className="px-4 py-3 text-stone-600">On-prem inference, privacy-sensitive workloads</td>
                      <td className="px-4 py-3 text-stone-500">32k</td>
                    </tr>
                    <tr>
                      <td className="px-4 py-3 font-semibold text-stone-800">Llama 3.3 70B</td>
                      <td className="px-4 py-3 text-stone-500">Meta</td>
                      <td className="px-4 py-3 text-stone-600">Air-gapped environments, fine-tuning, research</td>
                      <td className="px-4 py-3 text-stone-500">128k</td>
                    </tr>
                    <tr>
                      <td className="px-4 py-3 font-semibold text-stone-800">Llama 3.1 8B</td>
                      <td className="px-4 py-3 text-stone-500">Meta</td>
                      <td className="px-4 py-3 text-stone-600">Edge inference, local dev, experimentation</td>
                      <td className="px-4 py-3 text-stone-500">128k</td>
                    </tr>
                    <tr className="bg-stone-50">
                      <td className="px-4 py-3 font-semibold text-stone-800">Codestral</td>
                      <td className="px-4 py-3 text-stone-500">Mistral</td>
                      <td className="px-4 py-3 text-stone-600">Code completion, FIM (fill-in-middle), IDE integrations</td>
                      <td className="px-4 py-3 text-stone-500">32k</td>
                    </tr>
                  </tbody>
                </table>
              </div>
            </section>

            <section>
              <h2 className="text-xl font-bold text-stone-900 mb-3">Which model for which task</h2>

              <div className="space-y-5">
                <div>
                  <p className="font-semibold text-stone-800 mb-1">Complex reasoning / architecture design</p>
                  <p>
                    Use <strong>Claude Opus 4.7</strong> or <strong>o3</strong>. These tasks need sustained multi-step reasoning across large context. Don&apos;t cheap out here — a bad architectural decision costs more than the token bill.
                  </p>
                </div>

                <div>
                  <p className="font-semibold text-stone-800 mb-1">Day-to-day coding (PR review, bug fix, refactor)</p>
                  <p>
                    Use <strong>Claude Sonnet 4.6</strong> or <strong>GPT-4o</strong>. The sweet spot of quality and speed for the tasks that make up 80% of a developer&apos;s day.
                  </p>
                </div>

                <div>
                  <p className="font-semibold text-stone-800 mb-1">High-volume classification / routing / triage</p>
                  <p>
                    Use <strong>Claude Haiku 4.5</strong> or <strong>GPT-4o mini</strong> or <strong>Gemini Flash 2.0</strong>. Fast, cheap, more than good enough for yes/no and category decisions. Running 10k classifications a day? This is where your model bill lives.
                  </p>
                </div>

                <div>
                  <p className="font-semibold text-stone-800 mb-1">Long document / large codebase analysis</p>
                  <p>
                    Use <strong>Gemini 2.5 Pro</strong>. The 1M context window is a genuine differentiator for whole-repo analysis, large PRD documents, or compliance scanning.
                  </p>
                </div>

                <div>
                  <p className="font-semibold text-stone-800 mb-1">Maths, logic, step-by-step planning</p>
                  <p>
                    Use <strong>o3</strong> or <strong>DeepSeek R1</strong>. Chain-of-thought reasoning is where these models separate themselves. DeepSeek R1 is particularly compelling because it&apos;s open-weights — you can self-host and match o3 quality at a fraction of the cost.
                  </p>
                </div>

                <div>
                  <p className="font-semibold text-stone-800 mb-1">Code completion / IDE integration</p>
                  <p>
                    Use <strong>Codestral</strong> or Copilot (GPT-4o base). Purpose-built for fill-in-middle and fast completions. Codestral is optimised for this use case specifically.
                  </p>
                </div>

                <div>
                  <p className="font-semibold text-stone-800 mb-1">GDPR / EU data residency requirements</p>
                  <p>
                    Use <strong>Mistral Large</strong>. EU-based infrastructure, strong multilingual support. The right choice when your data can&apos;t leave Europe.
                  </p>
                </div>

                <div>
                  <p className="font-semibold text-stone-800 mb-1">Air-gapped / self-hosted / privacy-sensitive</p>
                  <p>
                    Use <strong>Llama 3.3 70B</strong> (self-hosted) or <strong>Mistral 7B/8x7B</strong>. Open-weights models you run on your own infrastructure. No API calls, no data leaving your perimeter.
                  </p>
                </div>

                <div>
                  <p className="font-semibold text-stone-800 mb-1">Multimodal (images, diagrams, screenshots)</p>
                  <p>
                    Use <strong>GPT-4o</strong> or <strong>Gemini 2.5 Pro</strong>. Both handle vision well. GPT-4o is more mature for tool-use with vision; Gemini shines on large documents with embedded images.
                  </p>
                </div>
              </div>
            </section>

            <section>
              <h2 className="text-xl font-bold text-stone-900 mb-3">Getting started — code examples</h2>
              <p>
                Quick-start snippets for each major provider.
              </p>

              <div className="mt-5 space-y-6">

                <div>
                  <p className="text-sm font-semibold text-stone-700 mb-2">
                    Claude (Anthropic SDK) —{" "}
                    <a href="https://docs.anthropic.com/en/api/getting-started" className="font-normal text-indigo-600 hover:underline">docs</a>
                  </p>
                  <div className="rounded-xl bg-stone-950 px-5 py-4 font-mono text-sm space-y-1">
                    <p className="text-stone-500 text-xs">import anthropic</p>
                    <p className="text-stone-500 text-xs">&nbsp;</p>
                    <p className="text-emerald-400">client = anthropic.Anthropic()</p>
                    <p className="text-stone-500 text-xs">&nbsp;</p>
                    <p className="text-emerald-400">message = client.messages.create(</p>
                    <p className="text-emerald-400">&nbsp;&nbsp;&nbsp;&nbsp;model=<span className="text-sky-400">&quot;claude-sonnet-4-6&quot;</span>,</p>
                    <p className="text-emerald-400">&nbsp;&nbsp;&nbsp;&nbsp;max_tokens=<span className="text-sky-400">1024</span>,</p>
                    <p className="text-emerald-400">&nbsp;&nbsp;&nbsp;&nbsp;messages=[&#123;&quot;role&quot;: <span className="text-sky-400">&quot;user&quot;</span>, &quot;content&quot;: <span className="text-sky-400">&quot;Review this PR diff for security issues.&quot;</span>&#125;]</p>
                    <p className="text-emerald-400">)</p>
                    <p className="text-emerald-400">print(message.content[<span className="text-sky-400">0</span>].text)</p>
                  </div>
                </div>

                <div>
                  <p className="text-sm font-semibold text-stone-700 mb-2">
                    OpenAI —{" "}
                    <a href="https://platform.openai.com/docs" className="font-normal text-indigo-600 hover:underline">docs</a>
                  </p>
                  <div className="rounded-xl bg-stone-950 px-5 py-4 font-mono text-sm space-y-1">
                    <p className="text-stone-500 text-xs">from openai import OpenAI</p>
                    <p className="text-stone-500 text-xs">&nbsp;</p>
                    <p className="text-emerald-400">client = OpenAI()</p>
                    <p className="text-stone-500 text-xs">&nbsp;</p>
                    <p className="text-emerald-400">response = client.chat.completions.create(</p>
                    <p className="text-emerald-400">&nbsp;&nbsp;&nbsp;&nbsp;model=<span className="text-sky-400">&quot;gpt-4o&quot;</span>,</p>
                    <p className="text-emerald-400">&nbsp;&nbsp;&nbsp;&nbsp;messages=[&#123;&quot;role&quot;: <span className="text-sky-400">&quot;user&quot;</span>, &quot;content&quot;: <span className="text-sky-400">&quot;Explain the architecture of this codebase.&quot;</span>&#125;]</p>
                    <p className="text-emerald-400">)</p>
                    <p className="text-emerald-400">print(response.choices[<span className="text-sky-400">0</span>].message.content)</p>
                  </div>
                </div>

                <div>
                  <p className="text-sm font-semibold text-stone-700 mb-2">
                    Google Gemini —{" "}
                    <a href="https://ai.google.dev/gemini-api/docs" className="font-normal text-indigo-600 hover:underline">docs</a>
                  </p>
                  <div className="rounded-xl bg-stone-950 px-5 py-4 font-mono text-sm space-y-1">
                    <p className="text-stone-500 text-xs">import google.generativeai as genai</p>
                    <p className="text-stone-500 text-xs">&nbsp;</p>
                    <p className="text-emerald-400">genai.configure(api_key=<span className="text-sky-400">&quot;YOUR_API_KEY&quot;</span>)</p>
                    <p className="text-emerald-400">model = genai.GenerativeModel(<span className="text-sky-400">&quot;gemini-2.5-pro&quot;</span>)</p>
                    <p className="text-stone-500 text-xs">&nbsp;</p>
                    <p className="text-emerald-400">response = model.generate_content(<span className="text-sky-400">&quot;Summarise this 500-page compliance document.&quot;</span>)</p>
                    <p className="text-emerald-400">print(response.text)</p>
                  </div>
                </div>

                <div>
                  <p className="text-sm font-semibold text-stone-700 mb-2">
                    DeepSeek —{" "}
                    <a href="https://api-docs.deepseek.com" className="font-normal text-indigo-600 hover:underline">docs</a>
                  </p>
                  <div className="rounded-xl bg-stone-950 px-5 py-4 font-mono text-sm space-y-1">
                    <p className="text-stone-500 text-xs"># DeepSeek is OpenAI-compatible</p>
                    <p className="text-stone-500 text-xs">from openai import OpenAI</p>
                    <p className="text-stone-500 text-xs">&nbsp;</p>
                    <p className="text-emerald-400">client = OpenAI(</p>
                    <p className="text-emerald-400">&nbsp;&nbsp;&nbsp;&nbsp;api_key=<span className="text-sky-400">&quot;YOUR_DEEPSEEK_KEY&quot;</span>,</p>
                    <p className="text-emerald-400">&nbsp;&nbsp;&nbsp;&nbsp;base_url=<span className="text-sky-400">&quot;https://api.deepseek.com&quot;</span></p>
                    <p className="text-emerald-400">)</p>
                    <p className="text-stone-500 text-xs">&nbsp;</p>
                    <p className="text-emerald-400">response = client.chat.completions.create(</p>
                    <p className="text-emerald-400">&nbsp;&nbsp;&nbsp;&nbsp;model=<span className="text-sky-400">&quot;deepseek-reasoner&quot;</span>,</p>
                    <p className="text-emerald-400">&nbsp;&nbsp;&nbsp;&nbsp;messages=[&#123;&quot;role&quot;: <span className="text-sky-400">&quot;user&quot;</span>, &quot;content&quot;: <span className="text-sky-400">&quot;Solve this step-by-step: ...&quot;</span>&#125;]</p>
                    <p className="text-emerald-400">)</p>
                    <p className="text-emerald-400">print(response.choices[<span className="text-sky-400">0</span>].message.content)</p>
                  </div>
                </div>

                <div>
                  <p className="text-sm font-semibold text-stone-700 mb-2">
                    Mistral —{" "}
                    <a href="https://docs.mistral.ai" className="font-normal text-indigo-600 hover:underline">docs</a>
                  </p>
                  <div className="rounded-xl bg-stone-950 px-5 py-4 font-mono text-sm space-y-1">
                    <p className="text-stone-500 text-xs">from mistralai import Mistral</p>
                    <p className="text-stone-500 text-xs">&nbsp;</p>
                    <p className="text-emerald-400">client = Mistral(api_key=<span className="text-sky-400">&quot;YOUR_MISTRAL_KEY&quot;</span>)</p>
                    <p className="text-stone-500 text-xs">&nbsp;</p>
                    <p className="text-emerald-400">response = client.chat.complete(</p>
                    <p className="text-emerald-400">&nbsp;&nbsp;&nbsp;&nbsp;model=<span className="text-sky-400">&quot;mistral-large-latest&quot;</span>,</p>
                    <p className="text-emerald-400">&nbsp;&nbsp;&nbsp;&nbsp;messages=[&#123;&quot;role&quot;: <span className="text-sky-400">&quot;user&quot;</span>, &quot;content&quot;: <span className="text-sky-400">&quot;Classify this support ticket.&quot;</span>&#125;]</p>
                    <p className="text-emerald-400">)</p>
                    <p className="text-emerald-400">print(response.choices[<span className="text-sky-400">0</span>].message.content)</p>
                  </div>
                </div>

                <div>
                  <p className="text-sm font-semibold text-stone-700 mb-2">
                    Llama via Ollama (local) —{" "}
                    <a href="https://ollama.com" className="font-normal text-indigo-600 hover:underline">ollama.com</a>
                  </p>
                  <div className="rounded-xl bg-stone-950 px-5 py-4 font-mono text-sm space-y-1">
                    <p className="text-stone-500 text-xs"># Pull and run locally</p>
                    <p className="text-emerald-400">ollama pull llama3.3</p>
                    <p className="text-emerald-400">ollama run llama3.3 <span className="text-sky-400">&quot;Fix this bug in my Python script: ...&quot;</span></p>
                  </div>
                  <div className="mt-3 rounded-xl bg-stone-950 px-5 py-4 font-mono text-sm space-y-1">
                    <p className="text-stone-500 text-xs">import ollama</p>
                    <p className="text-stone-500 text-xs">&nbsp;</p>
                    <p className="text-emerald-400">response = ollama.chat(</p>
                    <p className="text-emerald-400">&nbsp;&nbsp;&nbsp;&nbsp;model=<span className="text-sky-400">&quot;llama3.3&quot;</span>,</p>
                    <p className="text-emerald-400">&nbsp;&nbsp;&nbsp;&nbsp;messages=[&#123;&quot;role&quot;: <span className="text-sky-400">&quot;user&quot;</span>, &quot;content&quot;: <span className="text-sky-400">&quot;Refactor this function.&quot;</span>&#125;]</p>
                    <p className="text-emerald-400">)</p>
                    <p className="text-emerald-400">print(response[<span className="text-sky-400">&quot;message&quot;</span>][<span className="text-sky-400">&quot;content&quot;</span>])</p>
                  </div>
                </div>

              </div>
            </section>

            <section>
              <h2 className="text-xl font-bold text-stone-900 mb-3">The problem nobody talks about: running 3+ models at once</h2>
              <p>
                In practice, most engineering teams don&apos;t use one model. They use Claude Code for agentic tasks, Copilot for completions, GPT-4o for specific tooling, and a self-hosted Llama for sensitive work. Each model has different:
              </p>
              <ul className="mt-3 space-y-1 list-disc pl-5">
                <li>Cost curves (you need per-model spend visibility)</li>
                <li>Risk profiles (some models are more likely to write insecure code, hallucinate package names, or suggest overly permissive auth patterns)</li>
                <li>Data handling policies (you may not want certain code sent to certain providers)</li>
              </ul>
              <p className="mt-4">
                When developers run AI tools without governance, these differences are invisible. You don&apos;t know which tool caused the bad suggestion. You don&apos;t know which developer&apos;s session is costing $200/day. You don&apos;t know if a model suggested code that should never have left your perimeter.
              </p>
              <p className="mt-4">
                <strong>This is the gap ConductGuard closes.</strong>
              </p>
            </section>

            <section>
              <h2 className="text-xl font-bold text-stone-900 mb-3">How ConductGuard helps when you run multiple models</h2>
              <p>
                ConductGuard sits between your developers and every AI coding tool they run — Claude Code, Codex, Cursor, and any tool that hooks into your IDE. It gives you three things:
              </p>

              <div className="mt-5 space-y-5">
                <div>
                  <p className="font-semibold text-stone-800 mb-1">1. Per-tool, per-developer spend visibility</p>
                  <p>
                    See exactly how much each developer is spending per tool per day. Set hard caps. Get Slack alerts before budgets blow. The spend breakdown works across models — you can see your Claude bill vs. your OpenAI bill vs. your Codex usage in one dashboard.
                  </p>
                </div>

                <div>
                  <p className="font-semibold text-stone-800 mb-1">2. Policy enforcement across every model</p>
                  <p>
                    Write a rule once — &quot;never send files from /secrets/ to any model&quot;, &quot;block any tool call that modifies production infrastructure without approval&quot;, &quot;warn on any model output that contains hardcoded credentials&quot; — and it applies to every tool. The rule doesn&apos;t care whether the output came from Claude or GPT-4o.
                  </p>
                </div>

                <div>
                  <p className="font-semibold text-stone-800 mb-1">3. Audit trail for every AI decision</p>
                  <p>
                    Every tool call, every model output, every decision (allowed / blocked / warned) is logged with: developer identity, tool name, model used, timestamp, cost, and the rule that triggered. If something goes wrong, you can trace it in seconds.
                  </p>
                </div>
              </div>

              <div className="mt-6 rounded-xl bg-stone-950 px-5 py-4 font-mono text-sm space-y-1">
                <p className="text-stone-500 text-xs mb-2"># install and sync in 30 seconds</p>
                <p className="text-emerald-400">pip install conduct-cli</p>
                <p className="text-emerald-400">conduct guard sync</p>
                <p className="text-stone-400 mt-2"># ✓ Hook registered in Claude Code</p>
                <p className="text-stone-400"># ✓ Hook registered in Codex</p>
                <p className="text-stone-400"># ✓ Policies synced (8 rules active)</p>
                <p className="text-stone-400"># ✓ Spend tracking active</p>
              </div>
            </section>

          </div>

          <hr className="border-stone-100 mt-12 mb-8" />

          <div className="rounded-2xl bg-stone-900 px-8 py-8 text-center">
            <h3 className="text-xl font-bold text-white mb-2">Run multiple AI models? Guard them all from one place.</h3>
            <p className="text-stone-400 text-sm mb-6">
              ConductGuard works with Claude Code, Codex, Cursor, and any tool that exposes hooks. Install in 30 seconds.
            </p>
            <div className="flex items-center justify-center gap-4">
              <a
                href="/tools/agent-booster"
                className="inline-flex items-center gap-2 rounded-lg bg-white text-stone-900 px-5 py-2.5 text-sm font-semibold hover:bg-stone-100 transition-colors"
              >
                Install ConductGuard
              </a>
              <a
                href="/docs"
                className="text-sm text-stone-400 hover:text-white transition-colors"
              >
                Read the docs →
              </a>
            </div>
          </div>

          <hr className="border-stone-100 mt-8 mb-8" />
          <div className="flex items-center justify-between text-sm">
            <a href="/blog" className="text-stone-400 hover:text-stone-700 transition-colors">
              ← All posts
            </a>
            <a
              href="/tools/agent-booster"
              className="inline-flex items-center gap-2 rounded-lg bg-stone-900 text-white px-4 py-2 text-sm font-semibold hover:bg-stone-700 transition-colors"
            >
              Install ConductGuard →
            </a>
          </div>
        </article>
      </main>
    </div>
  )
}

function BlogNav() {
  return (
    <header className="px-6 py-5 flex items-center justify-between max-w-6xl mx-auto w-full">
      <a href="/">
        <img src="/logo.png" alt="Conduct AI" className="h-10 w-auto" />
      </a>
      <div className="flex items-center gap-4">
        <a href="/blog" className="text-sm font-medium text-stone-500 hover:text-stone-900 transition-colors">Blog</a>
        <a href="/tools/agent-booster" className="text-sm font-medium text-stone-500 hover:text-stone-900 transition-colors">Agent Booster</a>
        <a href="/marketplace" className="text-sm font-medium text-stone-500 hover:text-stone-900 transition-colors">Agent Templates</a>
        <a href="/docs" className="text-sm font-medium text-stone-500 hover:text-stone-900 transition-colors">Docs</a>
      </div>
    </header>
  )
}
