import { NextRequest, NextResponse } from 'next/server';
import { createHmac } from 'crypto';
import { auth, currentUser } from '@clerk/nextjs/server';

function sign(payload: string) {
  return createHmac('sha256', process.env.MCP_OAUTH_SECRET ?? 'dev-secret').update(payload).digest('hex');
}

function verifyStateCookie(val: string) {
  const [encoded, sig] = val.split('.');
  if (!encoded || !sig || sign(encoded) !== sig) return null;
  try {
    const parsed = JSON.parse(Buffer.from(encoded, 'base64url').toString());
    if (Date.now() > parsed.exp) return null;
    return parsed as {
      redirectUri: string;
      state: string;
      codeChallenge: string;
      codeChallengeMethod: string;
      workspaceId: string;
      exp: number;
    };
  } catch { return null; }
}

export async function GET(req: NextRequest) {
  const appUrl = process.env.NEXT_PUBLIC_APP_URL ?? 'https://app.conductai.ai';
  // Use server-only API_URL (no NEXT_PUBLIC prefix) so it's never baked at build time
  const apiUrl = process.env.API_URL ?? process.env.NEXT_PUBLIC_API_URL ?? 'https://api.conductai.ai';

  const stateCookie = req.cookies.get('mcp_oauth_state')?.value;
  if (!stateCookie) {
    return NextResponse.redirect(`${appUrl}/sign-in?error=mcp_state_missing`);
  }

  const oauthState = verifyStateCookie(stateCookie);
  if (!oauthState) {
    return NextResponse.redirect(`${appUrl}/sign-in?error=mcp_state_invalid`);
  }

  const session = await auth();
  if (!session.userId) {
    return NextResponse.redirect(
      `${appUrl}/sign-in?redirect_url=${encodeURIComponent('/api/mcp/guard/oauth/complete')}`
    );
  }

  const user = await currentUser();
  const email = user?.emailAddresses?.[0]?.emailAddress;
  if (!email) {
    return NextResponse.redirect(`${appUrl}/sign-in?error=mcp_no_email`);
  }

  const clerkToken = await session.getToken();
  const tokenRes = await fetch(`${apiUrl}/guard/mcp/oauth/member-token`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'Authorization': `Bearer ${clerkToken}`,
    },
    body: JSON.stringify({ workspace_id: oauthState.workspaceId, email }),
  });

  if (!tokenRes.ok) {
    const errBody = await tokenRes.text().catch(() => 'unreadable');
    const wsid = oauthState.workspaceId || '(empty)';
    return NextResponse.redirect(
      `${appUrl}/sign-in?error=mcp_member_token_failed&status=${tokenRes.status}&ws=${wsid}&api=${encodeURIComponent(apiUrl)}&detail=${encodeURIComponent(errBody.slice(0, 100))}`
    );
  }

  const { member_token } = await tokenRes.json();

  const codePayload = JSON.stringify({
    memberToken: member_token,
    workspaceId: oauthState.workspaceId,
    cc: oauthState.codeChallenge,
    exp: Date.now() + 5 * 60 * 1000,
  });
  const encodedCode = Buffer.from(codePayload).toString('base64url');
  const code = `${encodedCode}.${sign(encodedCode)}`;

  const redirectUrl = new URL(oauthState.redirectUri);
  redirectUrl.searchParams.set('code', code);
  redirectUrl.searchParams.set('state', oauthState.state);

  const res = NextResponse.redirect(redirectUrl.toString());
  res.cookies.delete('mcp_oauth_state');
  return res;
}
