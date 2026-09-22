"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { dashboards } from "@/config/dashboards";

export function Sidebar() {
  const pathname = usePathname();
  return (
    <aside className="sidebar">
      <Link href="/" className="brand" aria-label="ePresensi Overview">
        <span className="brand-mark" aria-hidden="true">eP</span>
        <span>ePresensi<small>Management dashboard</small></span>
      </Link>
      <p className="nav-label">ANALYTICS</p>
      <nav aria-label="Navigasi utama">
        {Object.values(dashboards).map((item, index) => (
          <Link key={item.key} href={item.href}
            aria-current={pathname === item.href ? "page" : undefined}>
            <span className="nav-number" aria-hidden="true">0{index + 1}</span>
            {item.title}
          </Link>
        ))}
      </nav>
      <div className="sidebar-note">Ruang kerja manajemen<span>Presensi · Kedisiplinan · Departemen</span></div>
    </aside>
  );
}
