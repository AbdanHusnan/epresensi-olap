import type { Metadata } from 'next';
import type { ReactNode } from 'react';
import './globals.css';
export const metadata: Metadata = { title: 'e-Presensi · Attendance insights', description: 'Role-based attendance insights for directors and department managers.', robots: { index: false, follow: false } };
export default function RootLayout({children}:{children:ReactNode}){return <html lang="en"><body>{children}</body></html>;}
