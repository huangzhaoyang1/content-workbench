"use client";

import { useEffect, useState } from "react";
import { Loader2, Save, Plug, CheckCircle2, XCircle, KeyRound, AlertTriangle } from "lucide-react";
import { api, friendlyMessage } from "@/lib/api";
import type { WorkbenchConfig } from "@/lib/types";
import { useToast } from "@/components/ui/toast";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Label } from "@/components/ui/label";
import { Button } from "@/components/ui/button";
import { Separator } from "@/components/ui/separator";
import { Skeleton } from "@/components/ui/skeleton";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { PageShell, PageHeader } from "@/components/layout/PageShell";

export default function ConfigPage() {
  const { toast } = useToast();
  const [cfg, setCfg] = useState<WorkbenchConfig | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState(false);
  const [dirty, setDirty] = useState(false);
  const [testRes, setTestRes] = useState<{
    serpapi: { ok: boolean; message: string };
    deepseek: { ok: boolean; message: string };
  } | null>(null);

  useEffect(() => {
    api
      .getConfig()
      .then(setCfg)
      .catch((e) => toast(friendlyMessage(e, "读取配置失败"), "error"))
      .finally(() => setLoading(false));
  }, [toast]);

  const update = (patch: Partial<WorkbenchConfig>) => {
    setDirty(true);
    setCfg((c) => (c ? { ...c, ...patch } : c));
  };

  const updateNested = <K extends "hotspot_api" | "search_api" | "deepseek">(
    key: K,
    patch: Partial<WorkbenchConfig[K]>
  ) => {
    setDirty(true);
    setCfg((c) =>
      c ? { ...c, [key]: { ...c[key], ...patch } } : c
    );
  };

  // 有未保存修改时，离开页面（刷新/关闭）前提醒
  useEffect(() => {
    if (!dirty) return;
    const handler = (e: BeforeUnloadEvent) => {
      e.preventDefault();
      e.returnValue = "";
    };
    window.addEventListener("beforeunload", handler);
    return () => window.removeEventListener("beforeunload", handler);
  }, [dirty]);

  const handleSave = async () => {
    if (!cfg) return;
    setSaving(true);
    try {
      const saved = await api.putConfig(cfg);
      setCfg(saved);
      setDirty(false);
      toast("配置已保存", "success");
    } catch (e) {
      toast(friendlyMessage(e, "保存失败"), "error");
    } finally {
      setSaving(false);
    }
  };

  const handleTest = async () => {
    if (!cfg) return;
    setTesting(true);
    setTestRes(null);
    try {
      const res = await api.testConnection(cfg.search_api, cfg.deepseek);
      setTestRes(res);
      if (res.serpapi.ok || res.deepseek.ok) {
        toast("连接测试完成", "success");
      } else {
        toast("密钥未填写或连接失败", "warning");
      }
    } catch (e) {
      toast(friendlyMessage(e, "测试失败"), "error");
    } finally {
      setTesting(false);
    }
  };

  if (loading) {
    return (
      <PageShell width="sm">
        <div className="space-y-4">
          <Skeleton className="h-8 w-40" />
          <Skeleton className="h-64 w-full" />
        </div>
      </PageShell>
    );
  }

  if (!cfg) {
    return (
      <PageShell width="sm">
        <Alert variant="destructive">
          <AlertTitle>无法加载配置</AlertTitle>
          <AlertDescription>请确认后端已启动并可访问 /api/config。</AlertDescription>
        </Alert>
      </PageShell>
    );
  }

  return (
    <PageShell width="sm">
      <PageHeader
        title="系统配置"
        description="配置账号信息、热点搜索与 AI 分析密钥。密钥保存在本地 workbench_config.json。"
        actions={
          <>
            {dirty && (
              <Badge variant="warning" className="gap-1">
                <AlertTriangle className="h-3 w-3" />
                未保存
              </Badge>
            )}
            <Button variant="outline" onClick={handleTest} disabled={testing}>
              {testing ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <Plug className="h-4 w-4" />
              )}
              测试连接
            </Button>
            <Button onClick={handleSave} disabled={saving}>
              {saving ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <Save className="h-4 w-4" />
              )}
              保存配置
            </Button>
          </>
        }
      />

      {testRes && (
        <div className="mt-4 grid grid-cols-1 gap-3 sm:grid-cols-2">
          <ConnBadge title="SerpAPI" res={testRes.serpapi} />
          <ConnBadge title="DeepSeek" res={testRes.deepseek} />
        </div>
      )}

      <Tabs defaultValue="basic" className="mt-6">
        <TabsList>
          <TabsTrigger value="basic">基础</TabsTrigger>
          <TabsTrigger value="search">智能搜索</TabsTrigger>
          <TabsTrigger value="deepseek">DeepSeek</TabsTrigger>
          <TabsTrigger value="advanced">高级</TabsTrigger>
        </TabsList>

        <TabsContent value="basic">
          <Card>
            <CardHeader>
              <CardTitle className="text-base">账号与内容定位</CardTitle>
              <CardDescription>用于选题生成时贴合你的账号调性。</CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <Field label="公众号 / 账号名称">
                <Input
                  value={cfg.account_name}
                  onChange={(e) => update({ account_name: e.target.value })}
                  placeholder="如：扬的AI学习日记"
                />
              </Field>
              <Field label="内容定位">
                <Input
                  value={cfg.positioning}
                  onChange={(e) => update({ positioning: e.target.value })}
                  placeholder="如：AI 副业实战 + 智能体小白教学"
                />
              </Field>
              <Field label="文风要求">
                <Textarea
                  value={cfg.style}
                  onChange={(e) => update({ style: e.target.value })}
                  placeholder="如：口语化、少术语、带真实踩坑体感"
                />
              </Field>
              <Field label="视觉风格">
                <Input
                  value={cfg.visual_style}
                  onChange={(e) => update({ visual_style: e.target.value })}
                  placeholder="如：简约科技风 / 暖色生活感"
                />
              </Field>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="search">
          <Card>
            <CardHeader>
              <CardTitle className="text-base">热点搜索</CardTitle>
              <CardDescription>
                选择 SerpAPI 真实搜索；留空则后端自动使用内置示例数据（mock）。
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <Field label="搜索类型">
                <select
                  className="flex h-9 w-full rounded-lg border border-input bg-transparent px-3 py-1 text-sm shadow-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                  value={cfg.search_api.type}
                  onChange={(e) =>
                    updateNested("search_api", {
                      type: e.target.value as WorkbenchConfig["search_api"]["type"],
                    })
                  }
                >
                  <option value="serpapi">SerpAPI（Google News）</option>
                  <option value="custom">自定义接口</option>
                  <option value="">示例数据（mock）</option>
                </select>
              </Field>
              <Field label="SerpAPI Key">
                <Input
                  type="password"
                  value={cfg.search_api.api_key}
                  onChange={(e) =>
                    updateNested("search_api", { api_key: e.target.value })
                  }
                  placeholder="留空则使用示例数据"
                />
              </Field>
              <Field label="每日搜索上限（防止超额扣费）">
                <Input
                  type="number"
                  value={cfg.daily_limit}
                  onChange={(e) =>
                    update({ daily_limit: Number(e.target.value) || 0 })
                  }
                />
              </Field>
              <Separator />
              <Field label="自定义热点接口 URL（type=custom 时生效）">
                <Input
                  value={cfg.hotspot_api.api_url}
                  onChange={(e) =>
                    updateNested("hotspot_api", { api_url: e.target.value })
                  }
                  placeholder="https://your-api.example.com/hotspots"
                />
              </Field>
              <Field label="自定义接口 Key">
                <Input
                  type="password"
                  value={cfg.hotspot_api.api_key}
                  onChange={(e) =>
                    updateNested("hotspot_api", { api_key: e.target.value })
                  }
                />
              </Field>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="deepseek">
          <Card>
            <CardHeader>
              <CardTitle className="text-base">DeepSeek 智能分析</CardTitle>
              <CardDescription>
                配置后对搜索结果做智能洞察与切入角度分析；留空则跳过。
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <Field label="Base URL">
                <Input
                  value={cfg.deepseek.base_url}
                  onChange={(e) =>
                    updateNested("deepseek", { base_url: e.target.value })
                  }
                />
              </Field>
              <Field label="API Key">
                <Input
                  type="password"
                  value={cfg.deepseek.api_key}
                  onChange={(e) =>
                    updateNested("deepseek", { api_key: e.target.value })
                  }
                  placeholder="sk-..."
                />
              </Field>
              <Field label="模型">
                <Input
                  value={cfg.deepseek.model}
                  onChange={(e) =>
                    updateNested("deepseek", { model: e.target.value })
                  }
                />
              </Field>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="advanced">
          <Card>
            <CardHeader>
              <CardTitle className="text-base">高级参数</CardTitle>
              <CardDescription>流水线脚本运行环境与项目根目录。</CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <Field label="Python 解释器路径">
                <Input
                  value={cfg.python_path}
                  onChange={(e) => update({ python_path: e.target.value })}
                  placeholder="python"
                />
              </Field>
              <Field label="现有流水线项目根目录" required>
                <Input
                  value={cfg.project_root}
                  onChange={(e) => update({ project_root: e.target.value })}
                  placeholder="C:\\Users\\...\\简约风格"
                />
              </Field>
              <Alert variant="info">
                <KeyRound className="h-4 w-4" />
                <AlertDescription>
                  流水线脚本（run_pipeline.py 等）必须位于项目根目录下的 scripts/，
                  data/issues/ 用于回读历史任务。
                </AlertDescription>
              </Alert>
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>
    </PageShell>
  );
}

function Field({
  label,
  children,
  required,
}: {
  label: string;
  children: React.ReactNode;
  required?: boolean;
}) {
  return (
    <div className="space-y-1.5">
      <Label required={required}>{label}</Label>
      {children}
    </div>
  );
}

function ConnBadge({
  title,
  res,
}: {
  title: string;
  res: { ok: boolean; message: string };
}) {
  return (
    <div
      className={`flex items-start gap-2 rounded-lg border px-3 py-2.5 text-sm ${
        res.ok
          ? "border-emerald-500/40 bg-emerald-500/10 text-emerald-300"
          : "border-destructive/40 bg-destructive/10 text-destructive"
      }`}
    >
      {res.ok ? (
        <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0" />
      ) : (
        <XCircle className="mt-0.5 h-4 w-4 shrink-0" />
      )}
      <div>
        <div className="font-medium">{title}</div>
        <div className="text-xs opacity-80">{res.message}</div>
      </div>
    </div>
  );
}
