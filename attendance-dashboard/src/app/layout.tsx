import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: { default: "ePresensi Dashboard", template: "%s | ePresensi" },
  description: "Dashboard presensi untuk manajemen.",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="id"><body>{children}</body></html>;
}
