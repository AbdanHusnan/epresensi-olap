export function Brand({ light = false }: { light?: boolean }) {
  return <div className={`brand ${light ? 'brand-light' : ''}`}><span className="brand-mark" aria-hidden="true"><i/><i/><i/></span><span>e-Presensi<span className="brand-subtitle">ATTENDANCE INSIGHTS</span></span></div>;
}
