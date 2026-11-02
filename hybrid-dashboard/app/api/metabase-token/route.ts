import { testRun, testRuns, runDashboardId } from '../../../lib/test-runs';
import { NextResponse } from 'next/server';
import { currentUser, dashboardId, requiredEnv, sameOrigin, signToken } from '../../../lib/auth';
export async function POST(request: Request) {
  if (!sameOrigin(request)) return NextResponse.json({ error: 'Invalid request origin.' }, { status: 403 });
  const user = await currentUser();
  if (!user) return NextResponse.json({ error: 'Your session has ended. Please sign in again.' }, { status: 401 });
  try {
    const body = await request.json();
    const inferredRun = body.run === undefined ? testRuns.find(item => Object.values(item[user.role]).some(id => String(id) === String(body.entityId))) : undefined;
    const run = testRun(body.run) ?? inferredRun;
    if (body.run !== undefined && !run) return NextResponse.json({ error: 'Unknown test run.' }, { status: 400 });
    if (body.section !== undefined && body.section !== 'overview' && body.section !== 'tables' && body.section !== 'period') return NextResponse.json({ error: 'Unknown dashboard section.' }, { status: 400 });
    const section = body.section === 'period' || (body.section === undefined && inferredRun && String(inferredRun[user.role].period) === String(body.entityId)) ? 'period' : body.section === 'tables' || (body.section === undefined && inferredRun && String(inferredRun[user.role].tables) === String(body.entityId)) ? 'tables' : 'overview';
    const id = run ? runDashboardId(run, user.role, section) : dashboardId(user.role);
    if (body.entityType !== 'dashboard' || String(body.entityId) !== String(id))
      return NextResponse.json({ error: 'This dashboard is not available for your role.' }, { status: 403 });
    const search = typeof body.search === 'string' ? body.search.trim() : '';
    if (search.length > 100) return NextResponse.json({ error: 'Search must be 100 characters or fewer.' }, { status: 400 });
    const params: Record<string, string | number | string[] | undefined> = user.role === 'manager' ? { department: user.departmentId } : {};
    if (!run || section === 'tables') params.search = search || [];
    if (run) {
      const validDate = (value: unknown): value is string => typeof value === 'string' && /^\d{4}-\d{2}-\d{2}$/.test(value) && Number.isFinite(Date.parse(value)) && new Date(value).toISOString().slice(0,10) === value;
      const start = body.startDate ?? run.startDate;
      const end = body.endDate ?? (section === 'period' ? run.endDate : start);
      if (!validDate(start) || !validDate(end) || start > end) return NextResponse.json({ error: 'Choose a valid start and end date.' }, { status: 400 });
      if (section !== 'period' && start !== end) return NextResponse.json({ error: 'Daily attendance requires one reporting date.' }, { status: 400 });
      if (user.role === 'director') {
        const department = body.department;
        if (department !== undefined && department !== '' && (!Number.isSafeInteger(Number(department)) || Number(department) <= 0)) return NextResponse.json({ error: 'Choose a valid department ID.' }, { status: 400 });
        params.department = department === undefined || department === '' ? [] : Number(department);
      }
      params.start_date = start;
      params.end_date = end;
    }
    if (user.role === 'manager' && !user.departmentId) return NextResponse.json({ error: 'Department assignment required.' }, { status: 403 });
    const jwt = signToken({ resource: { dashboard: id }, params, exp: Math.floor(Date.now() / 1000) + 600 }, requiredEnv('METABASE_EMBEDDING_SECRET'));
    return NextResponse.json({ jwt }, { headers: { 'Cache-Control': 'no-store' } });
  } catch { return NextResponse.json({ error: 'The dashboard is unavailable. Please try again.' }, { status: 503 }); }
}
