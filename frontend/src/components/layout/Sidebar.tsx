"use client";

import * as React from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  LayoutDashboard,
  Settings,
  Flame,
  Lightbulb,
  History,
  BarChart3,
  ListChecks,
  Menu,
  X,
  type LucideIcon,
} from "lucide-react";
import { cn } from "@/lib/utils";

interface NavItem {
  href: string;
  label: string;
  icon: LucideIcon;
  desc: string;
}

const NAV: NavItem[] = [
  { href: "/", label: "概览", icon: LayoutDashboard, desc: "工作台总览" },
  { href: "/hotspot", label: "热点素材", icon: Flame, desc: "搜索与洞察" },
  { href: "/analytics", label: "数据分析", icon: BarChart3, desc: "复盘 · 找方向" },
  { href: "/topic", label: "选题与生产", icon: Lightbulb, desc: "生成选题 · 跑流水线" },
  { href: "/queue", label: "任务队列", icon: ListChecks, desc: "批量排期 · 定时" },
  { href: "/tasks", label: "历史任务", icon: History, desc: "往期产出" },
  { href: "/config", label: "系统配置", icon: Settings, desc: "密钥与参数" },
];

function NavList({ onNavigate }: { onNavigate?: () => void }) {
  const pathname = usePathname();
  return (
    <nav className="flex-1 space-y-1 overflow-y-auto px-3">
      {NAV.map((item) => {
        const active =
          item.href === "/" ? pathname === "/" : pathname.startsWith(item.href);
        const Icon = item.icon;
        return (
          <Link
            key={item.href}
            href={item.href}
            onClick={onNavigate}
            aria-current={active ? "page" : undefined}
            className={cn(
              "group flex items-center gap-3 rounded-lg px-3 py-2 text-sm transition-all duration-150",
              active
                ? "bg-sidebar-accent font-medium text-sidebar-accent-foreground"
                : "text-muted-foreground hover:bg-sidebar-accent/60 hover:text-sidebar-foreground"
            )}
          >
            <Icon
              className={cn(
                "h-4 w-4 shrink-0 transition-transform duration-150",
                !active && "group-hover:scale-110"
              )}
            />
            <span className="flex flex-col">
              <span>{item.label}</span>
              <span className="text-[11px] text-muted-foreground/70">
                {item.desc}
              </span>
            </span>
          </Link>
        );
      })}
    </nav>
  );
}

function Brand() {
  return (
    <div className="flex items-center gap-2 px-5 py-5">
      <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-sidebar-primary text-sidebar-primary-foreground">
        <Flame className="h-5 w-5" />
      </div>
      <div className="leading-tight">
        <div className="text-sm font-semibold">AI 内容运营</div>
        <div className="text-xs text-muted-foreground">工作台</div>
      </div>
    </div>
  );
}

export function Sidebar() {
  const pathname = usePathname();
  const [open, setOpen] = React.useState(false);

  // 路由变化时自动收起抽屉
  React.useEffect(() => {
    setOpen(false);
  }, [pathname]);

  // 抽屉打开时锁定滚动 + Esc 关闭
  React.useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOpen(false);
    };
    document.addEventListener("keydown", onKey);
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.removeEventListener("keydown", onKey);
      document.body.style.overflow = prev;
    };
  }, [open]);

  const current = NAV.find((n) =>
    n.href === "/" ? pathname === "/" : pathname.startsWith(n.href)
  );

  return (
    <>
      {/* 桌面端：常驻侧栏 */}
      <aside className="hidden h-screen w-60 shrink-0 flex-col border-r border-sidebar-border bg-sidebar text-sidebar-foreground lg:flex">
        <Brand />
        <NavList />
        <div className="border-t border-sidebar-border px-5 py-3 text-[11px] text-muted-foreground">
          本地生活短视频 · 内容生产流水线
        </div>
      </aside>

      {/* 移动端：顶部条 */}
      <header className="fixed inset-x-0 top-0 z-40 flex h-14 items-center gap-3 border-b border-sidebar-border bg-sidebar px-4 text-sidebar-foreground lg:hidden">
        <button
          type="button"
          aria-label="打开菜单"
          onClick={() => setOpen(true)}
          className="flex h-9 w-9 items-center justify-center rounded-lg transition-colors hover:bg-sidebar-accent"
        >
          <Menu className="h-5 w-5" />
        </button>
        <div className="flex items-center gap-2">
          <div className="flex h-7 w-7 items-center justify-center rounded-md bg-sidebar-primary text-sidebar-primary-foreground">
            <Flame className="h-4 w-4" />
          </div>
          <span className="text-sm font-semibold">
            {current?.label ?? "AI 内容运营"}
          </span>
        </div>
      </header>

      {/* 移动端：抽屉 */}
      {open && (
        <div className="fixed inset-0 z-50 lg:hidden">
          <div
            className="absolute inset-0 animate-overlay-in bg-black/60 backdrop-blur-sm"
            onClick={() => setOpen(false)}
          />
          <aside className="absolute left-0 top-0 flex h-full w-64 animate-slide-in-left flex-col border-r border-sidebar-border bg-sidebar text-sidebar-foreground shadow-2xl">
            <div className="flex items-center justify-between pr-3">
              <Brand />
              <button
                type="button"
                aria-label="关闭菜单"
                onClick={() => setOpen(false)}
                className="flex h-8 w-8 items-center justify-center rounded-lg transition-colors hover:bg-sidebar-accent"
              >
                <X className="h-4 w-4" />
              </button>
            </div>
            <NavList onNavigate={() => setOpen(false)} />
            <div className="border-t border-sidebar-border px-5 py-3 text-[11px] text-muted-foreground">
              本地生活短视频 · 内容生产流水线
            </div>
          </aside>
        </div>
      )}
    </>
  );
}
