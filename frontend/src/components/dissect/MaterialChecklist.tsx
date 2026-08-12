"use client";

import * as React from "react";
import {
  Boxes,
  ChevronDown,
  CircleAlert,
  Hash,
  Lightbulb,
  Quote,
  Wrench,
  Clapperboard,
} from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import type { DissectMaterials } from "@/lib/types";

const LEVEL_META = {
  full: {
    label: "素材齐全",
    variant: "success" as const,
    hint: "观点、案例、数字、金句、方法都抠到了，三篇文章都有料可写。",
  },
  partial: {
    label: "素材有缺口",
    variant: "warning" as const,
    hint: "部分类型缺失，对应段落会偏空，建议补完整口播文案重跑。",
  },
  thin: {
    label: "素材太薄",
    variant: "destructive" as const,
    hint: "几乎抠不到具体素材，多半只拿到了标题或简介，强烈建议手动粘贴完整文案。",
  },
};

type IconType = React.ComponentType<{ className?: string }>;

/** 五个清单的统一描述，决定折叠面板的顺序与渲染方式。 */
type ListKey = "views" | "cases" | "numbers" | "quotes" | "methods";

const LISTS: {
  key: ListKey;
  icon: IconType;
  title: string;
  empty: string;
}[] = [
  {
    key: "views",
    icon: Lightbulb,
    title: "观点清单",
    empty: "原文没有可单独列出的观点，改写时会标注为「我自己的判断」。",
  },
  {
    key: "cases",
    icon: Clapperboard,
    title: "案例清单",
    empty: "原文里没有可引用的案例，改写时会标注为「我准备这么试」。",
  },
  {
    key: "numbers",
    icon: Hash,
    title: "数据清单",
    empty: "全文无任何具体数字 —— 这通常说明抓到的文案不完整。",
  },
  {
    key: "quotes",
    icon: Quote,
    title: "金句清单",
    empty: "没有可以单独截图转发的句子。",
  },
  {
    key: "methods",
    icon: Wrench,
    title: "方法清单",
    empty: "原文没有点名任何工具或方法。",
  },
];

/** 单条素材的渲染：不同类型的清单用稍微不同的视觉强调。 */
function renderItem(key: ListKey, item: unknown, i: number): React.ReactNode {
  if (key === "views") {
    const v = item as { point: string; detail: string };
    return (
      <li key={i}>
        <span className="text-foreground">{v.point}</span>
        {v.detail && (
          <span className="text-muted-foreground">　依据：{v.detail}</span>
        )}
      </li>
    );
  }
  if (key === "cases") {
    const c = item as { what: string; detail: string };
    return (
      <li key={i}>
        <span className="text-foreground">{c.what}</span>
        {c.detail && (
          <span className="text-muted-foreground">　细节：{c.detail}</span>
        )}
      </li>
    );
  }
  if (key === "numbers") {
    const n = item as { value: string; context: string };
    return (
      <li key={i}>
        <span className="rounded bg-primary/10 px-1 font-medium text-foreground">
          {n.value}
        </span>
        {n.context && (
          <span className="text-muted-foreground">　{n.context}</span>
        )}
      </li>
    );
  }
  if (key === "methods") {
    const t = item as { name: string; usage: string };
    return (
      <li key={i}>
        <span className="font-medium text-foreground">{t.name}</span>
        {t.usage && (
          <span className="text-muted-foreground">　用法：{t.usage}</span>
        )}
      </li>
    );
  }
  // quotes / logic_chain 都是纯字符串
  return (
    <li key={i} className="border-l-2 border-primary/40 pl-2 italic">
      {String(item)}
    </li>
  );
}

function CollapsibleList({
  def,
  materials,
}: {
  def: (typeof LISTS)[number];
  materials: DissectMaterials;
}) {
  const Icon = def.icon;
  const items = (materials[def.key] as unknown[]) ?? [];
  const count = items.length;
  const [open, setOpen] = React.useState(true);

  return (
    <div className="overflow-hidden rounded-lg border border-border bg-muted/20">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="flex w-full items-center gap-1.5 px-3 py-2 text-left text-xs font-medium text-foreground transition-colors hover:bg-muted/40"
        aria-expanded={open}
      >
        <Icon className="h-3.5 w-3.5 text-muted-foreground" />
        {def.title}
        <span
          className={cn(
            "rounded px-1.5 text-[10px] tabular-nums",
            count > 0
              ? "bg-primary/15 text-foreground"
              : "bg-destructive/15 text-destructive"
          )}
        >
          {count}
        </span>
        <ChevronDown
          className={cn(
            "ml-auto h-3.5 w-3.5 text-muted-foreground transition-transform",
            open && "rotate-180"
          )}
        />
      </button>
      {open && (
        <div className="border-t border-border px-3 py-2">
          {count > 0 ? (
            <ul className="space-y-1.5 text-xs leading-relaxed text-foreground/80">
              {items.map((it, i) => renderItem(def.key, it, i))}
            </ul>
          ) : (
            <p className="text-xs text-muted-foreground">{def.empty}</p>
          )}
        </div>
      )}
    </div>
  );
}

export function MaterialChecklist({
  materials,
  className,
}: {
  materials: DissectMaterials;
  className?: string;
}) {
  const meta = LEVEL_META[materials.completeness.level] ?? LEVEL_META.partial;

  return (
    <div className={cn("space-y-3", className)}>
      <div className="rounded-xl border border-border bg-card p-4 shadow-sm">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div className="flex items-center gap-2 text-sm font-medium text-foreground">
            <Boxes className="h-4 w-4 text-primary" />
            完整素材清单
            <span className="text-xs font-normal text-muted-foreground">
              改写时会被强制消费，数字必须原样出现在正文里
            </span>
          </div>
          <Badge variant={meta.variant}>{meta.label}</Badge>
        </div>

        <p className="mt-2 text-xs leading-relaxed text-muted-foreground">
          {materials.completeness.note || meta.hint}
        </p>

        {materials.completeness.missing.length > 0 && (
          <div className="mt-2 flex flex-wrap items-center gap-1.5">
            <CircleAlert className="h-3.5 w-3.5 text-amber-400" />
            {materials.completeness.missing.map((m, i) => (
              <span
                key={i}
                className="rounded bg-amber-500/10 px-1.5 py-0.5 text-[11px] text-amber-400"
              >
                {m}
              </span>
            ))}
          </div>
        )}
      </div>

      <div className="space-y-2">
        {LISTS.map((def) => (
          <CollapsibleList key={def.key} def={def} materials={materials} />
        ))}
      </div>
    </div>
  );
}
