import { NextResponse } from "next/server";
import { dashboards } from "@/config/dashboards";
import { allowLocalPreview } from "@/lib/auth/preview-policy";
import { createPreviewGuestToken } from "@/lib/superset/guest-token";
import type { DashboardKey } from "@/types/dashboard";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";
const headers = { "Cache-Control": "no-store, private", Vary: "Origin, Host" };

export async function POST(request: Request, context: { params: Promise<{ key: string }> }) {
  const { key } = await context.params;
  if (!Object.hasOwn(dashboards, key)) return NextResponse.json({ error: "Dashboard tidak ditemukan." }, { status: 404, headers });
  if (!allowLocalPreview(process.env, request.headers.get("origin"), request.headers.get("host"))) {
    return NextResponse.json({ error: "Akses dashboard memerlukan SSO. Pratinjau hanya tersedia di development localhost." }, { status: 403, headers });
  }
  try {
    return NextResponse.json(await createPreviewGuestToken(key as DashboardKey), { headers });
  } catch {
    return NextResponse.json({ error: "Dashboard belum dapat diakses. Coba kembali atau hubungi administrator." }, { status: 503, headers });
  }
}
