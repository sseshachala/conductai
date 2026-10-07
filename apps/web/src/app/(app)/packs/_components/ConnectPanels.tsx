"use client"

import { useState } from "react"

export function MCPConnectPanel() {
  const [tab, setTab] = useState<"ts" | "py" | "java" | "csharp" | "go">("ts")

  const snippets: Record<typeof tab, string> = {
    ts: `import Anthropic from "@anthropic-ai/sdk";

const client = new Anthropic();
const response = await client.beta.messages.create({
  model: "claude-opus-4-5",
  max_tokens: 1024,
  tools: [{
    type: "mcp",
    server_url: "https://api.conductai.ai/guard/mcp",
    server_name: "ConductGuard",
    authorization_token: process.env.CONDUCT_API_KEY,
  }],
  messages: [{ role: "user", content: "..." }],
});`,
    py: `import anthropic, os

client = anthropic.Anthropic()
response = client.beta.messages.create(
    model="claude-opus-4-5",
    max_tokens=1024,
    tools=[{
        "type": "mcp",
        "server_url": "https://api.conductai.ai/guard/mcp",
        "server_name": "ConductGuard",
        "authorization_token": os.environ["CONDUCT_API_KEY"],
    }],
    messages=[{"role": "user", "content": "..."}],
)`,
    java: `var request = HttpRequest.newBuilder()
    .uri(URI.create("https://api.conductai.ai/guard/mcp"))
    .header("Authorization", "Bearer " + System.getenv("CONDUCT_API_KEY"))
    .header("Content-Type", "application/json")
    .POST(HttpRequest.BodyPublishers.ofString(payload))
    .build();
var response = HttpClient.newHttpClient()
    .send(request, HttpResponse.BodyHandlers.ofString());`,
    csharp: `var client = new HttpClient();
client.DefaultRequestHeaders.Add(
    "Authorization", $"Bearer {Environment.GetEnvironmentVariable("CONDUCT_API_KEY")}");

var response = await client.PostAsJsonAsync(
    "https://api.conductai.ai/guard/mcp",
    new { method = "tools/call", params = new {
        name = "guard_check", arguments = new { action = "..." }
    }}
);`,
    go: `req, _ := http.NewRequest("POST", "https://api.conductai.ai/guard/mcp", body)
req.Header.Set("Authorization", "Bearer "+os.Getenv("CONDUCT_API_KEY"))
req.Header.Set("Content-Type", "application/json")
resp, _ := http.DefaultClient.Do(req)`,
  }

  const tabs = [
    { id: "ts" as const, label: "TypeScript" },
    { id: "py" as const, label: "Python" },
    { id: "java" as const, label: "Java" },
    { id: "csharp" as const, label: "C#" },
    { id: "go" as const, label: "Go" },
  ]

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 20 }}>
      <div>
        <h2 style={{ fontSize: 16, fontWeight: 700, color: "var(--text)", marginBottom: 4 }}>Connect via MCP</h2>
        <p style={{ fontSize: 13, color: "var(--text-3)", lineHeight: 1.6 }}>
          Any MCP-capable agent — Claude Desktop, Cursor, Windsurf, VS Code Copilot — inherits your Guard policies the moment it connects.
        </p>
      </div>

      {/* JSON config */}
      <div className="card" style={{ padding: "16px 20px" }}>
        <p style={{ fontSize: 11, fontWeight: 700, textTransform: "uppercase", letterSpacing: ".08em", color: "var(--text-muted)", marginBottom: 10 }}>Add to your MCP client config</p>
        <pre style={{ fontSize: 12.5, fontFamily: "var(--font-mono, monospace)", color: "var(--accent-text)", lineHeight: 1.7, overflowX: "auto", margin: 0 }}>{`{
  "mcpServers": {
    "conductguard": {
      "url": "https://api.conductai.ai/guard/mcp",
      "headers": { "Authorization": "Bearer YOUR_API_KEY" }
    }
  }
}`}</pre>
      </div>

      {/* SDK snippets */}
      <div className="card" style={{ padding: 0, overflow: "hidden" }}>
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", padding: "14px 20px 0" }}>
          <p style={{ fontSize: 11, fontWeight: 700, textTransform: "uppercase", letterSpacing: ".08em", color: "var(--text-muted)" }}>Connect from code</p>
          <div style={{ display: "flex", gap: 4 }}>
            {tabs.map(t => (
              <button key={t.id} onClick={() => setTab(t.id)} style={{
                padding: "4px 10px", borderRadius: 6, fontSize: 12, fontWeight: 600, border: "none", cursor: "pointer", fontFamily: "inherit",
                background: tab === t.id ? "var(--accent)" : "transparent",
                color: tab === t.id ? "#fff" : "var(--text-3)",
              }}>{t.label}</button>
            ))}
          </div>
        </div>
        <pre style={{ margin: 0, padding: "14px 20px 18px", fontSize: 12.5, fontFamily: "var(--font-mono, monospace)", color: "var(--accent-text)", lineHeight: 1.7, overflowX: "auto" }}>
          {snippets[tab]}
        </pre>
      </div>

      {/* Footer */}
      <p style={{ fontSize: 12, color: "var(--text-muted)" }}>
        Need an API token?{" "}
        <a href="/agent-identity?tab=tokens" style={{ color: "var(--accent-text)", textDecoration: "none", fontWeight: 600 }}>Generate one in Agent Identity →</a>
      </p>
    </div>
  )
}

export function ProxyConnectPanel() {
  const [tab, setTab] = useState<"ts" | "py" | "curl" | "anthropic" | "openai">("ts")

  const snippets: Record<typeof tab, string> = {
    ts: `import OpenAI from "openai";

// Point any OpenAI-compatible SDK at Conduct — Guard policies apply automatically.
const client = new OpenAI({
  baseURL: "https://api.conductai.ai/proxy/openai/v1",
  apiKey: process.env.CONDUCT_API_KEY,
});

const res = await client.chat.completions.create({
  model: "gpt-4o-mini",
  messages: [{ role: "user", content: "..." }],
});`,
    py: `from openai import OpenAI

client = OpenAI(
    base_url="https://api.conductai.ai/proxy/openai/v1",
    api_key=os.environ["CONDUCT_API_KEY"],
)
res = client.chat.completions.create(
    model="gpt-4o-mini",
    messages=[{"role": "user", "content": "..."}],
)`,
    anthropic: `import Anthropic from "@anthropic-ai/sdk";

const client = new Anthropic({
  baseURL: "https://api.conductai.ai/proxy/anthropic",
  apiKey: process.env.CONDUCT_API_KEY,
});

const res = await client.messages.create({
  model: "claude-sonnet-4-5",
  max_tokens: 1024,
  messages: [{ role: "user", content: "..." }],
});`,
    openai: `# OpenRouter, Portkey, Helicone, LiteLLM, Azure — configured in Settings → Proxy.
# Once set, this single base URL routes to whichever upstream you chose.

export CONDUCT_PROXY=https://api.conductai.ai/proxy/openai/v1
export CONDUCT_API_KEY=cond_live_...`,
    curl: `curl https://api.conductai.ai/proxy/openai/v1/chat/completions \\
  -H "Authorization: Bearer $CONDUCT_API_KEY" \\
  -H "Content-Type: application/json" \\
  -d '{
    "model": "gpt-4o-mini",
    "messages": [{"role": "user", "content": "..."}]
  }'`,
  }

  const tabs = [
    { id: "ts" as const, label: "TypeScript" },
    { id: "py" as const, label: "Python" },
    { id: "anthropic" as const, label: "Anthropic SDK" },
    { id: "openai" as const, label: "Env vars" },
    { id: "curl" as const, label: "curl" },
  ]

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 20 }}>
      <div>
        <h2 style={{ fontSize: 16, fontWeight: 700, color: "var(--text)", marginBottom: 4 }}>Connect via Proxy</h2>
        <p style={{ fontSize: 13, color: "var(--text-3)", lineHeight: 1.6 }}>
          OpenAI, Anthropic, and Perplexity SDKs all work — swap the base URL, keep the SDK. Guard policies, spend limits, and audit apply to every call. Upstream (OpenRouter, Portkey, Helicone, LiteLLM, Azure) is configured once in{" "}
          <a href="/settings?tab=proxy" style={{ color: "var(--accent-text)", textDecoration: "none", fontWeight: 600 }}>Settings → Proxy</a>.
        </p>
      </div>

      {/* Base URL card */}
      <div className="card" style={{ padding: "16px 20px" }}>
        <p style={{ fontSize: 11, fontWeight: 700, textTransform: "uppercase", letterSpacing: ".08em", color: "var(--text-muted)", marginBottom: 10 }}>Point your SDK here</p>
        <pre style={{ fontSize: 12.5, fontFamily: "var(--font-mono, monospace)", color: "var(--accent-text)", lineHeight: 1.7, overflowX: "auto", margin: 0 }}>{`# OpenAI-compatible
base_url:  https://api.conductai.ai/proxy/openai/v1
# Anthropic
base_url:  https://api.conductai.ai/proxy/anthropic
# Perplexity
base_url:  https://api.conductai.ai/proxy/perplexity

Authorization: Bearer YOUR_CONDUCT_API_KEY`}</pre>
      </div>

      {/* SDK snippets */}
      <div className="card" style={{ padding: 0, overflow: "hidden" }}>
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", padding: "14px 20px 0" }}>
          <p style={{ fontSize: 11, fontWeight: 700, textTransform: "uppercase", letterSpacing: ".08em", color: "var(--text-muted)" }}>Connect from code</p>
          <div style={{ display: "flex", gap: 4 }}>
            {tabs.map(t => (
              <button key={t.id} onClick={() => setTab(t.id)} style={{
                padding: "4px 10px", borderRadius: 6, fontSize: 12, fontWeight: 600, border: "none", cursor: "pointer", fontFamily: "inherit",
                background: tab === t.id ? "var(--accent)" : "transparent",
                color: tab === t.id ? "#fff" : "var(--text-3)",
              }}>{t.label}</button>
            ))}
          </div>
        </div>
        <pre style={{ margin: 0, padding: "14px 20px 18px", fontSize: 12.5, fontFamily: "var(--font-mono, monospace)", color: "var(--accent-text)", lineHeight: 1.7, overflowX: "auto" }}>
          {snippets[tab]}
        </pre>
      </div>

      {/* Footer */}
      <p style={{ fontSize: 12, color: "var(--text-muted)" }}>
        Need an API token?{" "}
        <a href="/agent-identity?tab=tokens" style={{ color: "var(--accent-text)", textDecoration: "none", fontWeight: 600 }}>Generate one in Agent Identity →</a>
      </p>
    </div>
  )
}
