"use client";

import * as React from "react";
import { Loader2, CalendarClock } from "lucide-react";
import { Dialog } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Label } from "@/components/ui/label";
import { Select } from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import type { ScheduleFrequency, ScheduleInput, ScheduleJob } from "@/lib/types";

interface ScheduleDialogProps {
  open: boolean;
  /** 传入表示编辑，null 表示新建。 */
  job: ScheduleJob | null;
  saving: boolean;
  onSubmit: (payload: ScheduleInput) => void;
  onClose: () => void;
}

const WEEKDAYS = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"];

const EMPTY: ScheduleInput = {
  name: "",
  topic: "",
  angle: "",
  extra: "",
  platform: "wechat",
  frequency: "daily",
  time: "09:00",
  weekday: 0,
  cron: "",
  enabled: true,
};

/** 新增 / 编辑定时任务对话框。 */
export function ScheduleDialog({
  open,
  job,
  saving,
  onSubmit,
  onClose,
}: ScheduleDialogProps) {
  const [form, setForm] = React.useState<ScheduleInput>(EMPTY);
  const [err, setErr] = React.useState<string | null>(null);

  React.useEffect(() => {
    if (!open) return;
    setErr(null);
    setForm(
      job
        ? {
            name: job.name,
            topic: job.topic,
            angle: job.angle,
            extra: job.extra,
            platform: job.platform,
            frequency: job.frequency,
            time: job.time,
            weekday: job.weekday,
            cron: job.cron,
            enabled: job.enabled,
          }
        : EMPTY
    );
  }, [open, job]);

  const set = <K extends keyof ScheduleInput>(k: K, v: ScheduleInput[K]) =>
    setForm((f) => ({ ...f, [k]: v }));

  const submit = () => {
    if (!form.name.trim()) return setErr("任务名称不能为空");
    if (!form.topic.trim()) return setErr("选题主题不能为空");
    if (form.frequency === "cron") {
      const parts = (form.cron || "").trim().split(/\s+/);
      if (parts.length !== 5)
        return setErr("cron 需要 5 个字段，例如「0 9 * * 1」表示每周一 09:00");
    } else if (!/^\d{1,2}:\d{2}$/.test(form.time || "")) {
      return setErr("执行时间格式应为 HH:MM，例如 09:00");
    }
    setErr(null);
    onSubmit({ ...form, name: form.name.trim(), topic: form.topic.trim() });
  };

  return (
    <Dialog open={open} onClose={saving ? () => undefined : onClose} className="max-w-xl">
      <div className="flex items-center gap-2">
        <CalendarClock className="h-4 w-4 text-muted-foreground" />
        <h3 className="text-base font-semibold">
          {job ? "编辑定时任务" : "新增定时任务"}
        </h3>
      </div>
      <p className="mt-1 text-xs text-muted-foreground">
        到点后会自动把这个选题加进队列并开始执行，产出照常进历史任务。
      </p>

      <div className="mt-5 space-y-4">
        <div className="space-y-1.5">
          <Label>任务名称 *</Label>
          <Input
            value={form.name}
            onChange={(e) => set("name", e.target.value)}
            placeholder="例如：每天早上出一期 AI 工具实测"
          />
        </div>

        <div className="grid grid-cols-2 gap-3">
          <div className="space-y-1.5">
            <Label>频率</Label>
            <Select
              value={form.frequency}
              onChange={(e) => set("frequency", e.target.value as ScheduleFrequency)}
            >
              <option value="daily">每天</option>
              <option value="weekly">每周</option>
              <option value="cron">自定义 cron</option>
            </Select>
          </div>

          {form.frequency === "cron" ? (
            <div className="space-y-1.5">
              <Label>cron 表达式</Label>
              <Input
                value={form.cron}
                onChange={(e) => set("cron", e.target.value)}
                placeholder="0 9 * * 1"
              />
            </div>
          ) : (
            <div className="space-y-1.5">
              <Label>执行时间</Label>
              <Input
                type="time"
                value={form.time}
                onChange={(e) => set("time", e.target.value)}
              />
            </div>
          )}
        </div>

        {form.frequency === "weekly" && (
          <div className="space-y-1.5">
            <Label>星期几</Label>
            <Select
              value={String(form.weekday ?? 0)}
              onChange={(e) => set("weekday", Number(e.target.value))}
            >
              {WEEKDAYS.map((w, i) => (
                <option key={w} value={i}>
                  {w}
                </option>
              ))}
            </Select>
          </div>
        )}

        {form.frequency === "cron" && (
          <p className="rounded-md bg-muted/50 px-2.5 py-1.5 text-[11px] text-muted-foreground">
            五个字段依次是「分 时 日 月 周」，周里 0 表示周日。例：
            <code className="mx-1">30 8 * * 1-5</code>= 工作日每天 08:30。
          </p>
        )}

        <div className="space-y-1.5">
          <Label>选题主题 *</Label>
          <Input
            value={form.topic}
            onChange={(e) => set("topic", e.target.value)}
            placeholder="例如：普通人能用上的 AI 提效工具"
          />
        </div>

        <div className="space-y-1.5">
          <Label>切入角度</Label>
          <Textarea
            rows={2}
            value={form.angle}
            onChange={(e) => set("angle", e.target.value)}
            placeholder="例如：只讲真正省时间的那 3 个，附我的实测耗时"
          />
        </div>

        <div className="space-y-1.5">
          <Label>补充要求（可选）</Label>
          <Textarea
            rows={2}
            value={form.extra}
            onChange={(e) => set("extra", e.target.value)}
            placeholder="例如：结尾留一个互动问题"
          />
        </div>

        <div className="flex items-center justify-between rounded-lg border border-border px-3 py-2.5">
          <div>
            <div className="text-sm font-medium">启用</div>
            <div className="text-[11px] text-muted-foreground">
              关掉后保留配置但不会自动执行
            </div>
          </div>
          <Switch
            checked={!!form.enabled}
            onCheckedChange={(v) => set("enabled", v)}
          />
        </div>

        {err && (
          <p className="rounded-md border border-destructive/40 bg-destructive/10 px-2.5 py-1.5 text-xs text-destructive">
            {err}
          </p>
        )}
      </div>

      <div className="mt-6 flex justify-end gap-2">
        <Button variant="ghost" onClick={onClose} disabled={saving}>
          取消
        </Button>
        <Button onClick={submit} disabled={saving}>
          {saving && <Loader2 className="h-4 w-4 animate-spin" />}
          {job ? "保存修改" : "创建任务"}
        </Button>
      </div>
    </Dialog>
  );
}
