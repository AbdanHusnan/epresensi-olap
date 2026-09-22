import type { DashboardDefinition } from "@/types/dashboard";

export function DashboardPage({ dashboard }: { dashboard: DashboardDefinition }) {
  return (
    <>
      <header className="page-heading">
        <p className="eyebrow">PRESENSI PEGAWAI</p>
        <h1>{dashboard.title}</h1>
        <p>{dashboard.description}</p>
      </header>
      <section className="metric-grid" aria-label="Indikator utama">
        {dashboard.metrics.map((metric) => (
          <article key={metric} className="metric-card">
            <h2>{metric}</h2>
            <p className="metric-value" aria-label="Data belum tersedia">—</p>
            <p className="metric-note">Target belum ditetapkan</p>
          </article>
        ))}
      </section>
      <section className="empty-panel" aria-labelledby="analytics-heading">
        <span className="empty-symbol" aria-hidden="true">▥</span>
        <h2 id="analytics-heading">Analitik sedang disiapkan</h2>
        <p>Data kehadiran dan grafik akan tampil setelah dashboard terhubung.</p>
        <p className="filter-note">Filter yang akan tersedia: tanggal{dashboard.departmentFilter ? " dan departemen" : ""}.</p>
      </section>
    </>
  );
}
