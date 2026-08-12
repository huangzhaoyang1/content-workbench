"use client";

import * as React from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  LayoutDashboard,
  Settings,
  Flame,
  Lightbulb,
  BarChart3,
  ListChecks,
  Target,
  Bookmark,
  FileText,
  ShieldCheck,
  ChevronDown,
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
  /** 自定义高亮判定；不传则默认「/ 精确匹配，其余前缀匹配」。 */
  activeWhen?: (pathname: string, review: boolean) => boolean;
}

// 第一级：核心流程（置顶，图标 + 大字号）
const CORE: NavItem[] = [
  { href: "/", label: "工作台", icon: LayoutDashboard, desc: "今日概览 · 核心流程" },
  { href: "/dissect", label: "拆解", icon: Target, desc: "抖音爆款 → 公众号" },
  { href: "/topic", label: "选题", icon: Lightbulb, desc: "生成选题 · 跑流水线" },
  {
    href: "/tasks",
    label: "出稿",
    icon: FileText,
    desc: "发起生产 · 历史产出",
    activeWhen: (p, review) => p === "/tasks" && !review,
  },
  {
    href: "/tasks?review=1",
    label: "审核",
    icon: ShieldCheck,
    desc: "待审核任务 · 发布",
    activeWhen: (p, review) => p === "/tasks" && review,
  },
];

// 第二级：更多（折叠组，默认收起）
const MORE: NavItem[] = [
  { href: "/hotspot", label: "热点", icon: Flame, desc: "搜索与洞察" },
  { href: "/queue", label: "队列", icon: ListChecks, desc: "批量排期 · 定时" },
  { href: "/analytics", label: "数据分析", icon: BarChart3, desc: "复盘 · 找方向" },
  { href: "/douyin-sync", label: "抖音同步", icon: Bookmark, desc: "收藏夹 → 素材池" },
  { href: "/config", label: "设置", icon: Settings, desc: "密钥与参数" },
];

const ALL = [...CORE, ...MORE];

function isActive(item: NavItem, pathname: string, review: boolean): boolean {
  if (item.activeWhen) return item.activeWhen(pathname, review);
  return item.href === "/" ? pathname === "/" : pathname.startsWith(item.href);
}

function NavLink({
  item,
  active,
  onNavigate,
  size = "sm",
}: {
  item: NavItem;
  active: boolean;
  onNavigate?: () => void;
  size?: "core" | "sm";
}) {
  const Icon = item.icon;
  return (
    <Link
      href={item.href}
      onClick={onNavigate}
      aria-current={active ? "page" : undefined}
      className={cn(
        "group flex items-center gap-3 rounded-lg transition-all duration-150",
        size === "core"
          ? "px-3 py-2.5 text-[15px]"
          : "px-3 py-2 text-sm",
        active
          ? "bg-sidebar-accent font-medium text-sidebar-accent-foreground"
          : "text-muted-foreground hover:bg-sidebar-accent/60 hover:text-sidebar-foreground"
      )}
    >
      <Icon
        className={cn(
          size === "core" ? "h-5 w-5" : "h-4 w-4",
          "shrink-0 transition-transform duration-150",
          !active && "group-hover:scale-110"
        )}
      />
      <span className="flex min-w-0 flex-col">
        <span className="truncate leading-tight">{item.label}</span>
        <span
          className={cn(
            "truncate text-[11px] text-muted-foreground/70",
            size === "core" ? "block" : "hidden lg:block"
          )}
        >
          {item.desc}
        </span>
      </span>
    </Link>
  );
}

function MoreGroup({
  pathname,
  review,
  onNavigate,
}: {
  pathname: string;
  review: boolean;
  onNavigate?: () => void;
}) {
  const [open, setOpen] = React.useState(false);
  return (
    <div className="px-3">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        className="flex w-full items-center gap-2 rounded-lg px-3 py-2 text-xs font-medium uppercase tracking-wide text-muted-foreground/70 transition-colors hover:bg-sidebar-accent/50 hover:text-sidebar-foreground"
      >
        <span>更多</span>
        <ChevronDown
          className={cn(
            "ml-auto h-3.5 w-3.5 transition-transform duration-200",
            open && "rotate-180"
          )}
        />
      </button>
      {open && (
        <div className="mt-1 space-y-1">
          {MORE.map((item) => (
            <NavLink
              key={item.href}
              item={item}
              active={isActive(item, pathname, review)}
              onNavigate={onNavigate}
            />
          ))}
        </div>
      )}
    </div>
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

function SidebarBody({
  pathname,
  onNavigate,
  review,
}: {
  pathname: string;
  onNavigate?: () => void;
  review: boolean;
}) {
  return (
    <div className="flex h-full flex-col">
      <Brand />
      {/* 核心流程：置顶，图标 + 大字号 */}
      <nav className="flex-1 space-y-1 overflow-y-auto px-3">
        <div className="px-3 pb-1 pt-1 text-[11px] font-medium uppercase tracking-wide text-muted-foreground/50">
          核心流程
        </div>
        {CORE.map((item) => (
          <NavLink
            key={item.href}
            item={item}
            active={isActive(item, pathname, review)}
            onNavigate={onNavigate}
            size="core"
          />
        ))}
        <div className="pt-2">
          <MoreGroup pathname={pathname} review={review} onNavigate={onNavigate} />
        </div>
      </nav>
      <div className="border-t border-sidebar-border px-5 py-3 text-[11px] text-muted-foreground">
        本地生活短视频 · 内容生产流水线
      </div>
    </div>
  );
}

export function Sidebar() {
  const pathname = usePathname();
  const [open, setOpen] = React.useState(false);
  // 用挂载后读取 location 的方式判断 ?review=1，避免 useSearchParams 的 Suspense 要求。
  const [review, setReview] = React.useState(false);

  React.useEffect(() => {
    const q = new URLSearchParams(window.location.search).get("review");
    setReview(q === "1");
  }, [pathname]);

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

  const current = ALL.find((n) => isActive(n, pathname, review));

  return (
    <>
      {/* 桌面端：常驻侧栏 */}
      <aside className="hidden h-screen w-60 shrink-0 flex-col border-r border-sidebar-border bg-sidebar text-sidebar-foreground lg:flex">
        <SidebarBody pathname={pathname} review={review} />
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
            <div className="min-h-0 flex-1">
              <SidebarBody
                pathname={pathname}
                review={review}
                onNavigate={() => setOpen(false)}
              />
            </div>
          </aside>
        </div>
      )}
    </>
  );
}
