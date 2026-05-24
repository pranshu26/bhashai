import './globals.css';
import type { ReactNode } from 'react';

export const metadata = {
  title: 'BhashAI — Indian-language document translation',
  description: 'Human-quality English → Indian-language document translation that preserves structure.',
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
