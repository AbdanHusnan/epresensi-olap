import { NextResponse } from 'next/server';
import { authenticate, homeFor, sameOrigin, sessionToken, SESSION_COOKIE, SESSION_SECONDS } from '../../../../lib/auth';
export async function POST(request: Request) {
  if (!sameOrigin(request)) return NextResponse.json({ error: 'Invalid request origin.' }, { status: 403 });
  try {
    const body = await request.json();
    if (typeof body.username !== 'string' || typeof body.password !== 'string' || body.username.length > 100 || body.password.length > 256)
      return NextResponse.json({ error: 'Enter your username and password.' }, { status: 400 });
    const user = authenticate(body.username, body.password);
    if (!user) return NextResponse.json({ error: 'The username or password is incorrect.' }, { status: 401 });
    const response = NextResponse.json({ redirect: homeFor(user.role) }, { headers: { 'Cache-Control': 'no-store' } });
    response.cookies.set(SESSION_COOKIE, sessionToken(user), { httpOnly: true, sameSite: 'lax', secure: request.headers.get('x-forwarded-proto') === 'https', path: '/', maxAge: SESSION_SECONDS });
    return response;
  } catch { return NextResponse.json({ error: 'Sign-in is unavailable. Please try again.' }, { status: 503 }); }
}
