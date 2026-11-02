import type { Metadata } from 'next';
import type { ReactNode } from 'react';
import './globals.css';
import { Inter } from 'next/font/google';
const inter = Inter({ subsets: ['latin'], display: 'swap', variable: '--font-inter' });
export const metadata: Metadata = { title: 'Dashboard Kehadiran E-Presensi BKD Jawa Timur', description: 'Role-based attendance insights for directors and department managers.', robots: { index: false, follow: false } };
export default function RootLayout({children}:{children:ReactNode}){return <html lang="en"><body className={inter.variable}>{children}</body></html>;}
