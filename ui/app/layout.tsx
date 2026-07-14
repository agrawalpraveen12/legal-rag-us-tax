import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Legal Tax Research Assistant",
  description: "US Internal Revenue Code — AI-Powered Research Tool",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" className="h-full">
      <body className="min-h-full flex flex-col">{children}</body>
    </html>
  );
}
