import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import "./globals.css";
import { InvestigationProvider } from "@/context/InvestigationContext";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "Sherlock - Crime Analytics",
  description: "AI-powered crime investigation and knowledge graph analysis",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body
        className={`${geistSans.variable} ${geistMono.variable} antialiased bg-[#fafafa] text-[#1a1a1a]`}
      >
        <InvestigationProvider>
          {children}
        </InvestigationProvider>
      </body>
    </html>
  );
}
