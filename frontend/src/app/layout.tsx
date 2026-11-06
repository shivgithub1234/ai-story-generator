import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Story Studio · A little idea. A whole new world.",
  description:
    "Your personal writing space. Plan, write, and refine stories with AI.",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
