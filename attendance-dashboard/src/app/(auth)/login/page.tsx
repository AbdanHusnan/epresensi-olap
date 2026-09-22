import Link from "next/link";

export const metadata = { title: "Masuk" };

export default function LoginPage() {
  return <main className="login-page"><section className="empty-panel">
    <p className="eyebrow">ePRESENSI</p>
    <h1>Masuk ke dashboard</h1>
    <p>Akses melalui SSO instansi sedang disiapkan.</p>
    <Link className="text-link" href="/">Lihat pratinjau tampilan</Link>
  </section></main>;
}
