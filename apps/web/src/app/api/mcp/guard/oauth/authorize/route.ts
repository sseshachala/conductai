import { NextRequest, NextResponse } from 'next/server';
import { createHmac } from 'crypto';

function sign(payload: string) {
  return createHmac('sha256', process.env.MCP_OAUTH_SECRET ?? 'dev-secret').update(payload).digest('hex');
}

export async function GET(req: NextRequest) {
  const { searchParams } = req.nextUrl;
  const redirectUri = searchParams.get('redirect_uri');
  const state = searchParams.get('state');
  const responseType = searchParams.get('response_type');
  const codeChallenge = searchParams.get('code_challenge');
  const codeChallengeMethod = searchParams.get('code_challenge_method');

  // RFC 8707: MCP clients send the resource URL which contains workspace_id
  const resource = searchParams.get('resource') ?? '';
  let workspaceId = searchParams.get('workspace_id') ?? '';
  if (!workspaceId && resource) {
    try { workspaceId = new URL(resource).searchParams.get('workspace_id') ?? ''; } catch { /* ignore */ }
  }

  if (responseType !== 'code') {
    return NextResponse.json({ error: 'unsupported_response_type' }, { status: 400 });
  }
  if (!codeChallenge) {
    return NextResponse.json({ error: 'invalid_request: code_challenge required' }, { status: 400 });
  }
  if (!redirectUri || !state) {
    return NextResponse.json({ error: 'invalid_request: missing redirect_uri or state' }, { status: 400 });
  }

  const payload = JSON.stringify({
    redirectUri,
    state,
    codeChallenge,
    codeChallengeMethod: codeChallengeMethod ?? 'S256',
    workspaceId,
    exp: Date.now() + 10 * 60 * 1000,
  });
  const encoded = Buffer.from(payload).toString('base64url');
  const cookieVal = `${encoded}.${sign(encoded)}`;

  const appUrl = process.env.NEXT_PUBLIC_APP_URL ?? 'https://app.conductai.ai';
  const res = NextResponse.redirect(
    `${appUrl}/sign-in?redirect_url=${encodeURIComponent('/api/mcp/guard/oauth/complete')}`
  );
  res.cookies.set('mcp_oauth_state', cookieVal, {
    httpOnly: true,
    secure: process.env.NODE_ENV === 'production',
    sameSite: 'lax',
    maxAge: 600,
    path: '/',
    domain: '.conductai.ai', // covers both conductai.ai and app.conductai.ai
  });
  return res;
}
