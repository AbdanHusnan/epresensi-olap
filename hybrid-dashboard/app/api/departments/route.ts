import { NextResponse } from 'next/server';
import { currentUser } from '../../../lib/auth';
import { testRun } from '../../../lib/test-runs';
import options from '../../../lib/department-options.json';

export async function GET(request: Request) {
  const user = await currentUser();
  if (!user) return NextResponse.json({ error: 'Please sign in.' }, { status: 401 });
  const url = new URL(request.url);
  const run = testRun(url.searchParams.get('run'));
  if (!run) return NextResponse.json({ error: 'Unknown test run.' }, { status: 400 });
  const query = (url.searchParams.get('q') || '').trim().toLocaleLowerCase().slice(0,100);
  const departments = (options as Record<string, { id: number; name: string }[]>)[run.key] || [];
  return NextResponse.json({ departments: departments.filter(department =>
    (user.role === 'director' || department.id === user.departmentId) &&
    department.name.toLocaleLowerCase().includes(query)).slice(0,20) }, { headers: { 'Cache-Control': 'private, no-store' } });
}
