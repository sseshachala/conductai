import { NextRequest, NextResponse } from 'next/server';
import { randomUUID } from 'crypto';

// RFC 7591 Dynamic Client Registration — accepts any MCP client (Claude.ai, Cursor, etc.)
export async function POST(req: NextRequest) {
  let body: Record<string, unknown> = {};
  try { body = await req.json(); } catch { /* empty body is fine */ }

  const clientId = `mcp_${randomUUID().replace(/-/g, '')}`;

  return NextResponse.json({
    client_id: clientId,
    client_id_issued_at: Math.floor(Date.now() / 1000),
    redirect_uris: body.redirect_uris ?? [],
    grant_types: ['authorization_code'],
    response_types: ['code'],
    token_endpoint_auth_method: 'none',
    code_challenge_methods_supported: ['S256'],
    client_name: body.client_name ?? 'MCP Client',
  }, { status: 201 });
}
