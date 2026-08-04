"use client";

import * as React from "react";
import { ArrowDownUp, Plus } from "lucide-react";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Button } from "@/components/ui/button";
import { EmptyState } from "@/components/ui/empty-state";
import type { AnalyticsRankItem, RankingKey } from "@/lib/types";

interface RankingTableProps {
  items: AnalyticsRankItem[];
  /** 当前榜单主指标，决定默认排序列。 */
  metric: RankingKey;
  onPick: (item: AnalyticsRankItem) => void;
}

type SortKey = "rank" | "reads" | "likes" | "shares" | "like_rate";

const NUM_COLS: Array<{ key: SortKey; label: string }> = [
  { key: "reads", label: "阅读量" },
  { key: "likes", label: "在看" },
  { key: "shares", label: "分享" },
  { key: "like_rate", label: "在看率" },
];

function cellValue(it: AnalyticsRankItem, k: SortKey): number {
  if (k === "rank") return it.rank;
  const v = it[k];
  return typeof v === "number" ? v : -1;
}

function fmt(v: number | null, suffix = ""): string {
  if (v === null || v === undefined) return "—";
  return `${v.toLocaleString("zh-CN")}${suffix}`;
}

/** 榜单表格：支持点列头排序，每行可加入选题参考。 */
export function RankingTable({ items, metric, onPick }: RankingTableProps) {
  const [sortKey, setSortKey] = React.useState<SortKey>("rank");
  const [desc, setDesc] = React.useState(false);

  React.useEffect(() => {
    setSortKey("rank");
    setDesc(false);
  }, [metric]);

  const sorted = React.useMemo(() => {
    const arr = [...items];
    arr.sort((a, b) => {
      const d = cellValue(a, sortKey) - cellValue(b, sortKey);
      return desc ? -d : d;
    });
    return arr;
  }, [items, sortKey, desc]);

  const toggle = (k: SortKey) => {
    if (k === sortKey) setDesc((d) => !d);
    else {
      setSortKey(k);
      setDesc(k !== "rank");
    }
  };

  if (items.length === 0) {
    return (
      <EmptyState
        icon={ArrowDownUp}
        title="这个维度暂无数据"
        description="上传的表格里没有识别到对应的数值列，换一个 Tab 看看，或检查导出文件的表头。"
      />
    );
  }

  const HeadBtn = ({ k, label }: { k: SortKey; label: string }) => (
    <button
      type="button"
      onClick={() => toggle(k)}
      className="inline-flex items-center gap-1 hover:text-foreground"
    >
      {label}
      {sortKey === k && (
        <span className="text-[10px]">{desc ? "↓" : "↑"}</span>
      )}
    </button>
  );

  return (
    <div className="rounded-xl border border-border">
      <Table>
        <TableHeader>
          <TableRow className="hover:bg-transparent">
            <TableHead className="w-14">
              <HeadBtn k="rank" label="#" />
            </TableHead>
            <TableHead className="min-w-[220px]">标题</TableHead>
            <TableHead className="w-24">日期</TableHead>
            {NUM_COLS.map((c) => (
              <TableHead key={c.key} className="w-24 text-right">
                <div className="flex justify-end">
                  <HeadBtn k={c.key} label={c.label} />
                </div>
              </TableHead>
            ))}
            <TableHead className="w-32 text-right">操作</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {sorted.map((it) => (
            <TableRow key={`${it.rank}-${it.title}`}>
              <TableCell className="text-muted-foreground tabular-nums">
                {it.rank}
              </TableCell>
              <TableCell className="max-w-[320px] truncate font-medium" title={it.title}>
                {it.title}
              </TableCell>
              <TableCell className="text-xs text-muted-foreground">
                {it.date ?? "—"}
              </TableCell>
              <TableCell className="text-right tabular-nums">
                {fmt(it.reads)}
              </TableCell>
              <TableCell className="text-right tabular-nums">
                {fmt(it.likes)}
              </TableCell>
              <TableCell className="text-right tabular-nums">
                {fmt(it.shares)}
              </TableCell>
              <TableCell className="text-right tabular-nums">
                {it.like_rate === null || it.like_rate === undefined
                  ? "—"
                  : `${it.like_rate}%`}
              </TableCell>
              <TableCell className="text-right">
                <Button size="xs" variant="outline" onClick={() => onPick(it)}>
                  <Plus className="h-3 w-3" />
                  加入选题参考
                </Button>
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  );
}
