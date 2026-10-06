"use client";

import * as React from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { Settings, ListChecks, Menu, X, Coins } from "lucide-react";
import { cn } from "@/lib/utils";
import {
  MarkWorkbench,
  MarkDouyin,
  MarkHotspot,
  MarkHistory,
  MarkAnalytics,
} from "@/components/brand/marks";

interface NavItem {
  href: string;
  label: string;
  icon: React.ComponentType<{ className?: string }>;
  desc: string;
  /** 自定义高亮判定；不传则默认「/ 精确匹配，其余前缀匹配」。 */
  activeWhen?: (pathname: string) => boolean;
}

const NAV: NavItem[] = [
  {
    href: "/",
    label: "工作台",
    icon: MarkWorkbench,
    desc: "流程总入口",
    activeWhen: (p) => p === "/",
  },
  {
    href: "/douyin-sync",
    label: "抖音线",
    icon: MarkDouyin,
    desc: "即时拆解 · 收藏沉淀",
    activeWhen: (p) => p === "/douyin-sync" || p.startsWith("/douyin-sync") || p === "/dissect",
  },
  {
    href: "/hotspot",
    label: "热点线",
    icon: MarkHotspot,
    desc: "搜索热点 · 生成选题",
    activeWhen: (p) => p === "/hotspot" || p.startsWith("/hotspot") || p === "/topic",
  },
  {
    href: "/tasks",
    label: "历史任务",
    icon: MarkHistory,
    desc: "出稿与审核 · 往期",
    activeWhen: (p) => p === "/tasks" || p.startsWith("/tasks"),
  },
  {
    href: "/queue",
    label: "任务队列",
    icon: ListChecks,
    desc: "排队出稿 · 批量生产",
    activeWhen: (p) => p === "/queue" || p.startsWith("/queue"),
  },
  {
    href: "/analytics",
    label: "数据分析",
    icon: MarkAnalytics,
    desc: "复盘找方向",
    activeWhen: (p) => p === "/analytics" || p.startsWith("/analytics"),
  },
  {
    href: "/llm-cost",
    label: "调用与成本",
    icon: Coins,
    desc: "token 与费用",
    activeWhen: (p) => p === "/llm-cost" || p.startsWith("/llm-cost"),
  },
  {
    href: "/config",
    label: "设置",
    icon: Settings,
    desc: "密钥与参数",
    activeWhen: (p) => p === "/config" || p.startsWith("/config"),
  },
];

function isActive(item: NavItem, pathname: string): boolean {
  if (item.activeWhen) return item.activeWhen(pathname);
  return item.href === "/" ? pathname === "/" : pathname.startsWith(item.href);
}

function NavLink({
  item,
  active,
  onNavigate,
}: {
  item: NavItem;
  active: boolean;
  onNavigate?: () => void;
}) {
  const Icon = item.icon;
  return (
    <Link
      href={item.href}
      onClick={onNavigate}
      aria-current={active ? "page" : undefined}
      className={cn(
        "group flex items-center gap-3 rounded-lg border-l-2 px-3 py-2.5 text-[15px] transition-all duration-150",
        active
          ? "border-accent bg-accent/10 font-medium text-ink"
          : "border-transparent text-ink-2 hover:bg-sidebar-accent/60 hover:text-ink"
      )}
    >
      <Icon
        className={cn(
          "h-5 w-5 shrink-0 transition-transform duration-150",
          active ? "text-accent" : "text-ink-3 group-hover:scale-110 group-hover:text-ink-2"
        )}
      />
      <span className="flex min-w-0 flex-col">
        <span className="truncate leading-tight">{item.label}</span>
        <span className="truncate text-[11px] text-ink-3">{item.desc}</span>
      </span>
    </Link>
  );
}

function Brand() {
  return (
    <div className="flex items-center gap-2 px-5 py-5">
      <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-primary text-primary-foreground">
        <MarkWorkbench className="h-5 w-5" />
      </div>
      <div className="leading-tight">
        <div className="text-sm font-semibold text-ink">AI 内容运营</div>
        <div className="text-xs text-ink-2">工作台</div>
      </div>
    </div>
  );
}

function SidebarBody({
  pathname,
  onNavigate,
}: {
  pathname: string;
  onNavigate?: () => void;
}) {
  return (
    <div className="flex h-full flex-col">
      <Brand />
      <nav className="flex-1 space-y-1 overflow-y-auto px-3 pt-1">
        {NAV.map((item) => (
          <NavLink
            key={item.href}
            item={item}
            active={isActive(item, pathname)}
            onNavigate={onNavigate}
          />
        ))}
      </nav>
      <div className="border-t border-subtle px-5 py-3 text-[11px] leading-relaxed text-ink-2">
        抖音爆款或热点，都能变成你的公众号文章
      </div>
    </div>
  );
}

export function Sidebar() {
  const pathname = usePathname();
  const router = useRouter();
  const [open, setOpen] = React.useState(false);
  const restored = React.useRef(false);

  // 记住上次访问的页面：写入
  React.useEffect(() => {
    if (pathname) localStorage.setItem("cw:last-path", pathname);
  }, [pathname]);

  // 记住上次访问的页面：从「/」进入时自动回到上次页面
  React.useEffect(() => {
    if (restored.current) return;
    restored.current = true;
    const last = localStorage.getItem("cw:last-path");
    if (last && last !== "/" && pathname === "/") {
      router.replace(last);
    }
  }, [pathname, router]);

  React.useEffect(() => {
    setOpen(false);
  }, [pathname]);

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

  const current = NAV.find((n) => isActive(n, pathname));

  return (
    <>
      <aside className="hidden h-screen w-60 shrink-0 flex-col border-r border-subtle bg-sidebar text-sidebar-foreground lg:flex">
        <SidebarBody pathname={pathname} />
      </aside>

      <header className="fixed inset-x-0 top-0 z-40 flex h-14 items-center gap-3 border-b border-subtle bg-sidebar px-4 text-sidebar-foreground lg:hidden">
        <button
          type="button"
          aria-label="打开菜单"
          onClick={() => setOpen(true)}
          className="flex h-9 w-9 items-center justify-center rounded-lg transition-colors hover:bg-sidebar-accent"
        >
          <Menu className="h-5 w-5" />
        </button>
        <div className="flex items-center gap-2">
          <div className="flex h-7 w-7 items-center justify-center rounded-md bg-primary text-primary-foreground">
            <MarkWorkbench className="h-4 w-4" />
          </div>
          <span className="text-sm font-semibold">{current?.label ?? "AI 内容运营"}</span>
        </div>
      </header>

      {open && (
        <div className="fixed inset-0 z-50 lg:hidden">
          <div
            className="absolute inset-0 animate-overlay-in bg-base/70 backdrop-blur-sm"
            onClick={() => setOpen(false)}
          />
          <aside className="absolute left-0 top-0 flex h-full w-64 animate-slide-in-left flex-col border-r border-subtle bg-sidebar text-sidebar-foreground shadow-2xl">
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
            <div className="min-h-0 flex-1">
              <SidebarBody pathname={pathname} onNavigate={() => setOpen(false)} />
            </div>
          </aside>
        </div>
      )}
    </>
  );
}
