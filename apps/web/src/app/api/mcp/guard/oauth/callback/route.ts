import { NextRequest, NextResponse } from 'next/server';
import { createHmac, createHash } from 'crypto';

function sign(payload: string) {
  return createHmac('sha256', process.env.MCP_OAUTH_SECRET ?? 'dev-secret').update(payload).digest('hex');
}

function verifyCode(code: string) {
  const [encoded, sig] = code.split('.');
  if (!encoded || !sig || sign(encoded) !== sig) return null;
  try {
    const parsed = JSON.parse(Buffer.from(encoded, 'base64url').toString());
    if (Date.now() > parsed.exp) return null;
    return parsed as { memberToken: string; workspaceId: string; cc: string; exp: number };
  } catch { return null; }
}

function verifyPkce(verifier: string, challenge: string) {
  return createHash('sha256').update(verifier).digest('base64url') === challenge;
}

export async function POST(req: NextRequest) {
  let body: Record<string, string> = {};
  const ct = req.headers.get('content-type') ?? '';
  if (ct.includes('application/x-www-form-urlencoded')) {
    body = Object.fromEntries(new URLSearchParams(await req.text()));
  } else {
    body = await req.json().catch(() => ({}));
  }

  const { grant_type, code, code_verifier } = body;

  if (grant_type !== 'authorization_code') {
    return NextResponse.json({ error: 'unsupported_grant_type' }, { status: 400 });
  }
  if (!code) return NextResponse.json({ error: 'invalid_request' }, { status: 400 });

  const decoded = verifyCode(code);
  if (!decoded) return NextResponse.json({ error: 'invalid_grant' }, { status: 400 });

  if (!code_verifier) return NextResponse.json({ error: 'invalid_request: code_verifier required' }, { status: 400 });
  if (!verifyPkce(code_verifier, decoded.cc)) return NextResponse.json({ error: 'invalid_grant' }, { status: 400 });

  return NextResponse.json({
    access_token: decoded.memberToken,
    token_type: 'bearer',
    expires_in: 315360000, // member_token doesn't expire — return a large TTL
  });
}
