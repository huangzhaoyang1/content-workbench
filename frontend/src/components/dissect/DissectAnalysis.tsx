"use client";

import * as React from "react";
import {
  Anchor,
  Boxes,
  Zap,
  Users,
  CheckCircle2,
  Lightbulb,
  Clock,
  Type,
} from "lucide-react";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import type { DissectResult, DissectTypeTag } from "@/lib/types";

const TAG_VARIANT: Record<DissectTypeTag, "destructive" | "warning" | "success" | "secondary" | "default"> = {
  反常识: "destructive",
  痛点: "warning",
  干货: "success",
  故事: "secondary",
  经验: "default",
};

function SectionCard({
  icon: Icon,
  title,
  children,
}: {
  icon: React.ComponentType<{ className?: string }>;
  title: string;
  children: React.ReactNode;
}) {
  return (
    <Card>
      <CardHeader className="flex-row items-center gap-2 space-y-0 pb-3">
        <Icon className="h-4 w-4 text-primary" />
        <CardTitle className="text-sm">{title}</CardTitle>
      </CardHeader>
      <CardContent className="space-y-3 pt-0 text-sm">
        {children}
      </CardContent>
    </Card>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="space-y-1">
      <div className="text-xs font-medium text-muted-foreground">{label}</div>
      <div className="leading-relaxed text-foreground/90">{children}</div>
    </div>
  );
}

export function DissectAnalysis({ result }: { result: DissectResult }) {
  const { basics, hook, structure, boom, audience, portable, migration } = result;

  return (
    <div className="space-y-4">
      {/* 基础信息 */}
      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-sm">基础信息</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3 pt-0">
          <div className="text-base font-semibold text-foreground">
            {basics.title}
          </div>
          {basics.summary && (
            <p className="text-sm leading-relaxed text-foreground/80">
              {basics.summary}
            </p>
          )}
          {basics.topic && (
            <p className="text-xs text-muted-foreground">
              选题方向：{basics.topic}
            </p>
          )}
          <div className="flex flex-wrap items-center gap-2 pt-1">
            {basics.type_tags.map((t) => (
              <Badge key={t} variant={TAG_VARIANT[t]}>
                {t}
              </Badge>
            ))}
            {basics.duration_sec != null && (
              <span className="inline-flex items-center gap-1 text-xs text-muted-foreground">
                <Clock className="h-3.5 w-3.5" />
                约 {Math.round(basics.duration_sec / 60)} 分
                {basics.duration_sec % 60} 秒
              </span>
            )}
            {basics.word_count != null && (
              <span className="inline-flex items-center gap-1 text-xs text-muted-foreground">
                <Type className="h-3.5 w-3.5" />
                {basics.word_count} 字
              </span>
            )}
          </div>
        </CardContent>
      </Card>

      <div className="grid gap-4 md:grid-cols-2">
        {/* 🪝 钩子分析 */}
        <SectionCard icon={Anchor} title="🪝 钩子分析">
          {hook.quote && (
            <div className="rounded-lg border-l-2 border-primary/60 bg-muted/40 px-3 py-2 text-xs italic text-foreground/80">
              “{hook.quote}”
            </div>
          )}
          {hook.technique && <Field label="手法">{hook.technique}</Field>}
          {hook.why && <Field label="为什么有效">{hook.why}</Field>}
          {hook.score != null && (
            <Field label="钩子强度">
              <span className="font-semibold text-foreground">{hook.score}</span>
              <span className="text-muted-foreground"> / 10</span>
              <div className="mt-1 h-1.5 w-full overflow-hidden rounded-full bg-muted">
                <div
                  className="h-full rounded-full bg-primary"
                  style={{ width: `${hook.score * 10}%` }}
                />
              </div>
            </Field>
          )}
        </SectionCard>

        {/* 🎯 受众分析 */}
        <SectionCard icon={Users} title="🎯 受众分析">
          {audience.who && <Field label="打动谁">{audience.who}</Field>}
          {audience.pain && <Field label="真实痛点">{audience.pain}</Field>}
          {audience.scene && <Field label="刷到场景">{audience.scene}</Field>}
        </SectionCard>

        {/* 💥 爆点分析 */}
        <SectionCard icon={Zap} title="💥 爆点分析">
          {boom.core && (
            <div className="rounded-lg bg-amber-500/10 px-3 py-2 text-xs font-medium text-amber-300">
              {boom.core}
            </div>
          )}
          {boom.reasons.length > 0 && (
            <Field label="能火的原因">
              <ul className="list-disc space-y-1 pl-5">
                {boom.reasons.map((r, i) => (
                  <li key={i}>{r}</li>
                ))}
              </ul>
            </Field>
          )}
          {boom.emotion && <Field label="戳中情绪">{boom.emotion}</Field>}
        </SectionCard>

        {/* 📐 结构拆解 */}
        <SectionCard icon={Boxes} title="📐 结构拆解">
          <ol className="space-y-2">
            {structure.map((seg, i) => (
              <li key={i} className="flex gap-3">
                <span className="mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-primary/15 text-[11px] font-semibold text-primary">
                  {i + 1}
                </span>
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2">
                    <span className="text-sm font-medium text-foreground">
                      {seg.label}
                    </span>
                    {seg.seconds && (
                      <span className="rounded bg-muted px-1.5 py-0.5 text-[10px] text-muted-foreground">
                        {seg.seconds}
                      </span>
                    )}
                  </div>
                  {seg.content && (
                    <p className="mt-0.5 text-xs leading-relaxed text-muted-foreground">
                      {seg.content}
                    </p>
                  )}
                  {seg.role && (
                    <p className="mt-0.5 text-[11px] text-foreground/60">
                      作用：{seg.role}
                    </p>
                  )}
                </div>
              </li>
            ))}
          </ol>
        </SectionCard>
      </div>

      {/* ✅ 可迁移点 */}
      {portable.length > 0 && (
        <SectionCard icon={CheckCircle2} title="✅ 可迁移点（直接搬公众号）">
          <ul className="space-y-2">
            {portable.map((p, i) => (
              <li key={i} className="rounded-lg border border-border bg-muted/30 px-3 py-2">
                <div className="text-sm font-medium text-foreground">{p.point}</div>
                {p.how && (
                  <div className="mt-1 text-xs leading-relaxed text-muted-foreground">
                    👉 {p.how}
                  </div>
                )}
              </li>
            ))}
          </ul>
        </SectionCard>
      )}

      {/* 迁移建议 */}
      <SectionCard icon={Lightbulb} title="🚀 迁移建议">
        {migration.titles.length > 0 && (
          <Field label="公众号标题备选">
            <div className="space-y-1">
              {migration.titles.map((t, i) => (
                <div
                  key={i}
                  className="rounded-md bg-muted/40 px-3 py-1.5 text-sm text-foreground/90"
                >
                  {i + 1}. {t}
                </div>
              ))}
            </div>
          </Field>
        )}
        {migration.opening && <Field label="开头改法">{migration.opening}</Field>}
        {migration.expand.length > 0 && (
          <Field label="可展开的点">
            <ul className="list-disc space-y-1 pl-5">
              {migration.expand.map((e, i) => (
                <li key={i}>{e}</li>
              ))}
            </ul>
          </Field>
        )}
        {migration.ending && <Field label="结尾引导">{migration.ending}</Field>}
      </SectionCard>
    </div>
  );
}
