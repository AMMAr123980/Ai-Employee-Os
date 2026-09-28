import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "NEXOS AI Employee OS — Autonomous Turnkey Business Engine",
  description: "Enterprise AI Employee OS coordinating WhatsApp, Voice Commands, Meeting Intelligence, CRM, Quotations, and Accounting.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
