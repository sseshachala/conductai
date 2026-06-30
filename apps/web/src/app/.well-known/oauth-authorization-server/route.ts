import { NextResponse } from 'next/server';

export async function GET() {
  const base = process.env.NEXT_PUBLIC_APP_URL ?? 'https://app.conductai.ai';
  return NextResponse.json({
    issuer: base,
    authorization_endpoint: `${base}/api/mcp/guard/oauth/authorize`,
    token_endpoint: `${base}/api/mcp/guard/oauth/callback`,
    registration_endpoint: `${base}/api/mcp/guard/oauth/register`,
    response_types_supported: ['code'],
    grant_types_supported: ['authorization_code', 'refresh_token'],
    code_challenge_methods_supported: ['S256'],
    token_endpoint_auth_methods_supported: ['client_secret_post', 'none'],
    scopes_supported: ['guard:read'],
  });
}
