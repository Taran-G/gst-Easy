import type { Metadata } from "next";
import "./globals.css";
import { DashboardShell } from "@/components/DashboardShell";

export const metadata: Metadata = {
  title: "LedgerGraph — GST Agent for CA Firms",
  description: "WhatsApp-first GST invoice, reconciliation and vendor-risk agent for Indian CA firms and SMEs, built on FalkorDB.",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body>
        <DashboardShell>{children}</DashboardShell>
      </body>
    </html>
  );
}
