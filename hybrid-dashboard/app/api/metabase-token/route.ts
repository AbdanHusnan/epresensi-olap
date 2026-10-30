import { NextResponse } from 'next/server';
import { currentUser, dashboardId, requiredEnv, sameOrigin, signToken } from '../../../lib/auth';
export async function POST(request: Request) {
  if (!sameOrigin(request)) return NextResponse.json({ error: 'Invalid request origin.' }, { status: 403 });
  const user = await currentUser();
  if (!user) return NextResponse.json({ error: 'Your session has ended. Please sign in again.' }, { status: 401 });
  try {
    const body = await request.json();
    const id = dashboardId(user.role);
    if (body.entityType !== 'dashboard' || String(body.entityId) !== String(id))
      return NextResponse.json({ error: 'This dashboard is not available for your role.' }, { status: 403 });
    const params = user.role === 'manager' ? { department: user.departmentId } : {};
    if (user.role === 'manager' && !user.departmentId) return NextResponse.json({ error: 'Department assignment required.' }, { status: 403 });
    const jwt = signToken({ resource: { dashboard: id }, params, exp: Math.floor(Date.now() / 1000) + 600 }, requiredEnv('METABASE_EMBEDDING_SECRET'));
    return NextResponse.json({ jwt }, { headers: { 'Cache-Control': 'no-store' } });
  } catch { return NextResponse.json({ error: 'The dashboard is unavailable. Please try again.' }, { status: 503 }); }
}
