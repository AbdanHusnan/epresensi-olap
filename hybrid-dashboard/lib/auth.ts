import { createHmac, createHash, timingSafeEqual } from 'node:crypto';
import { cookies } from 'next/headers';
import { redirect } from 'next/navigation';

export type Role = 'director' | 'manager';
export type User = { username: Role; name: string; role: Role; departmentId?: number };
export const SESSION_COOKIE = 'attendance_session';
export const SESSION_SECONDS = 8 * 60 * 60;

export function requiredEnv(name: string): string {
  const value = process.env[name];
  if (!value) throw new Error(`Missing server configuration: ${name}`);
  return value;
}
export function userFor(username: string): User | null {
  if (username === 'director') return { username, name: 'Director', role: 'director' };
  if (username === 'manager') {
    const departmentId = Number(requiredEnv('DEMO_MANAGER_DEPARTMENT_ID'));
    if (!Number.isSafeInteger(departmentId) || departmentId <= 0) return null;
    return { username, name: 'Department Manager', role: 'manager', departmentId };
  }
  return null;
}
export function authenticate(username: string, password: string): User | null {
  const user = userFor(username.trim().toLowerCase());
  if (!user) return null;
  const expected = requiredEnv(user.role === 'director' ? 'DEMO_DIRECTOR_PASSWORD' : 'DEMO_MANAGER_PASSWORD');
  const hash = (v: string) => createHash('sha256').update(v).digest();
  return timingSafeEqual(hash(password), hash(expected)) ? user : null;
}
export function signToken(payload: object, secret: string): string {
  const header = Buffer.from(JSON.stringify({ alg: 'HS256', typ: 'JWT' })).toString('base64url');
  const body = Buffer.from(JSON.stringify(payload)).toString('base64url');
  const value = `${header}.${body}`;
  return `${value}.${createHmac('sha256', secret).update(value).digest('base64url')}`;
}
export function sessionToken(user: User): string {
  return signToken({ sub: user.username, exp: Math.floor(Date.now() / 1000) + SESSION_SECONDS }, requiredEnv('APP_SESSION_SECRET'));
}
export async function currentUser(): Promise<User | null> {
  const token = (await cookies()).get(SESSION_COOKIE)?.value;
  if (!token) return null;
  try {
    const [header, body, signature, extra] = token.split('.');
    if (!header || !body || !signature || extra) return null;
    const expected = createHmac('sha256', requiredEnv('APP_SESSION_SECRET')).update(`${header}.${body}`).digest();
    const actual = Buffer.from(signature, 'base64url');
    if (actual.length !== expected.length || !timingSafeEqual(actual, expected)) return null;
    if (JSON.parse(Buffer.from(header, 'base64url').toString()).alg !== 'HS256') return null;
    const data = JSON.parse(Buffer.from(body, 'base64url').toString());
    if (typeof data.exp !== 'number' || data.exp <= Date.now() / 1000 || typeof data.sub !== 'string') return null;
    return userFor(data.sub);
  } catch { return null; }
}
export function homeFor(role: Role): string { return role === 'director' ? '/analytical' : '/operational'; }
export async function requireRole(role: Role): Promise<User> {
  const user = await currentUser();
  if (!user) redirect('/login');
  if (user.role !== role) redirect(homeFor(user.role));
  return user;
}
export function sameOrigin(request: Request): boolean {
  const origin = request.headers.get('origin');
  const host = request.headers.get('x-forwarded-host') || request.headers.get('host');
  try { return !!origin && new URL(origin).host === host; } catch { return false; }
}
export function dashboardId(role: Role): number {
  const id = Number(requiredEnv(role === 'director' ? 'METABASE_ANALYTICAL_DASHBOARD_ID' : 'METABASE_OPERATIONAL_DASHBOARD_ID'));
  if (!Number.isSafeInteger(id) || id <= 0) throw new Error('Invalid dashboard configuration');
  return id;
}
