import type { Metadata } from "next";
import localFont from "next/font/local";
import "./globals.css";
import { cn } from "@/lib/utils";
import { Sidebar } from "@/components/layout/Sidebar";
import { ToastProvider } from "@/components/ui/toast";

const geistSans = localFont({
  src: "./fonts/GeistVF.woff",
  variable: "--font-geist-sans",
  weight: "100 900",
});
const geistMono = localFont({
  src: "./fonts/GeistMonoVF.woff",
  variable: "--font-geist-mono",
  weight: "100 900",
});

export const metadata: Metadata = {
  title: "AI 内容运营工作台",
  description: "热点搜索 · 选题生成 · 流水线生产 · 历史任务 一站式内容运营",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="zh-CN" className={cn("dark", geistSans.variable)} suppressHydrationWarning>
      <body
        className={`${geistMono.variable} antialiased`}
      >
        <ToastProvider>
          <div className="flex h-screen overflow-hidden bg-background text-foreground">
            <Sidebar />
            <main className="flex-1 overflow-auto pt-14 lg:pt-0">
              {children}
            </main>
          </div>
        </ToastProvider>
      </body>
    </html>
  );
}
