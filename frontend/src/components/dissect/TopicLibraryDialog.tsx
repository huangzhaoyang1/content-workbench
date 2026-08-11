"use client";

import * as React from "react";
import {
  Check,
  Copy,
  ExternalLink,
  Eye,
  History,
  Library,
  Loader2,
  Pencil,
  RefreshCw,
  Rocket,
  RotateCcw,
  Search,
  Tag,
  Trash2,
  Undo2,
  X,
} from "lucide-react";
import { Dialog } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { EmptyState } from "@/components/ui/empty-state";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { useToast } from "@/components/ui/toast";
import { api, friendlyMessage } from "@/lib/api";
import { cn } from "@/lib/utils";
import type { TopicLibraryItem, TrashTopic, TopicVersion, TopicVersionDetail } from "@/lib/types";

export const TOPIC_CATEGORIES = ["踩坑类", "干货类", "复盘类", "工具类", "其他"];
export const TOPIC_PRIORITIES = ["高", "中", "低"];
export const TOPIC_STATUSES = ["待生产", "生产中", "已完成"];

const CAT_OPTIONS = ["全部", ...TOPIC_CATEGORIES];
const PRI_OPTIONS = ["全部", ...TOPIC_PRIORITIES];
const STA_OPTIONS = ["全部", ...TOPIC_STATUSES];

function priorityVariant(p: string) {
  if (p === "高") return "destructive" as const;
  if (p === "中") return "warning" as const;
  return "muted" as const;
}
function statusVariant(s: string) {
  if (s === "已完成") return "success" as const;
  if (s === "生产中") return "warning" as const;
  return "secondary" as const;
}

/** 轻量标签编辑器：回车/逗号添加，点 × 删除。 */
function TagInput({
  value,
  onChange,
}: {
  value: string[];
  onChange: (next: string[]) => void;
}) {
  const [draft, setDraft] = React.useState("");
  const add = () => {
    const v = draft.trim();
    if (!v) return;
    if (!value.includes(v)) onChange([...value, v]);
    setDraft("");
  };
  return (
    <div className="space-y-2">
      <div className="flex flex-wrap gap-1.5">
        {value.length === 0 && (
          <span className="text-xs text-muted-foreground">暂无标签</span>
        )}
        {value.map((t) => (
          <Badge key={t} variant="outline" className="gap-1 pr-1">
            {t}
            <button
              type="button"
              className="ml-0.5 rounded-full p-0.5 text-muted-foreground hover:bg-muted hover:text-foreground"
              onClick={() => onChange(value.filter((x) => x !== t))}
              aria-label={`删除标签 ${t}`}
            >
              <X className="h-3 w-3" />
            </button>
          </Badge>
        ))}
      </div>
      <div className="flex gap-2">
        <Input
          className="h-8 text-xs"
          placeholder="输入标签后回车添加"
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" || e.key === ",") {
              e.preventDefault();
              add();
            }
          }}
        />
        <Button size="xs" variant="outline" type="button" onClick={add}>
          添加
        </Button>
      </div>
    </div>
  );
}

interface Props {
  open: boolean;
  onClose: () => void;
  /** 选题库条目数变化时回调，用于刷新头部按钮上的计数 */
  onCountChange?: (n: number) => void;
  /** 「拿去生产」：把选题带进任务队列 */
  onProduce?: (item: TopicLibraryItem) => void;
  onGoTopicPage?: () => void;
}

export function TopicLibraryDialog({
  open,
  onClose,
  onCountChange,
  onProduce,
  onGoTopicPage,
}: Props) {
  const { toast } = useToast();

  const [items, setItems] = React.useState<TopicLibraryItem[]>([]);
  const [total, setTotal] = React.useState(0);
  const [loading, setLoading] = React.useState(false);

  const [tab, setTab] = React.useState<"library" | "trash">("library");

  // ---- 回收站 ----
  const [trash, setTrash] = React.useState<TrashTopic[]>([]);
  const [trashTotal, setTrashTotal] = React.useState(0);
  const [trashLoading, setTrashLoading] = React.useState(false);
  const [pendingTrashDelete, setPendingTrashDelete] = React.useState<TrashTopic | null>(null);
  const [purging, setPurging] = React.useState(false);
  const [pendingEmptyTrash, setPendingEmptyTrash] = React.useState(false);

  const [category, setCategory] = React.useState("全部");
  const [priority, setPriority] = React.useState("全部");
  const [status, setStatus] = React.useState("全部");
  const [tag, setTag] = React.useState("全部");
  const [keyword, setKeyword] = React.useState("");

  const [allTags, setAllTags] = React.useState<string[]>([]);
  const [selected, setSelected] = React.useState<Set<string>>(new Set());

  const [editing, setEditing] = React.useState<TopicLibraryItem | null>(null);
  const [editTags, setEditTags] = React.useState<string[]>([]);
  const [saving, setSaving] = React.useState(false);
  const [pendingDelete, setPendingDelete] = React.useState<TopicLibraryItem | null>(null);
  const [deleting, setDeleting] = React.useState(false);

  const [batchBusy, setBatchBusy] = React.useState(false);
  const [pendingBatchDelete, setPendingBatchDelete] = React.useState(false);

  // ---- 版本历史 ----
  const [versionOpen, setVersionOpen] = React.useState(false);
  const [versionTopicId, setVersionTopicId] = React.useState("");
  const [versionTopicTitle, setVersionTopicTitle] = React.useState("");
  const [versionCurrent, setVersionCurrent] = React.useState("");
  const [versions, setVersions] = React.useState<TopicVersion[]>([]);
  const [versionsLoading, setVersionsLoading] = React.useState(false);
  const [activeVersion, setActiveVersion] = React.useState<TopicVersionDetail | null>(null);
  const [compareMode, setCompareMode] = React.useState(false);
  const [pendingRestoreVersion, setPendingRestoreVersion] = React.useState<string | null>(null);
  const [restoring, setRestoring] = React.useState(false);

  const load = React.useCallback(
    async (override?: Partial<Record<"category" | "priority" | "status" | "tag" | "keyword", string>>) => {
      setLoading(true);
      try {
        const res = await api.dissectListTopics({
          limit: 200,
          category: override?.category ?? category,
          priority: override?.priority ?? priority,
          status: override?.status ?? status,
          tag: override?.tag ?? tag,
          keyword: override?.keyword ?? keyword,
        });
        setItems(res.items);
        setTotal(res.total);
        onCountChange?.(res.total);
      } catch (e) {
        toast(friendlyMessage(e, "读取选题库失败"), "error");
      } finally {
        setLoading(false);
      }
    },
    [category, priority, status, tag, keyword, onCountChange, toast]
  );

  const loadTags = React.useCallback(async () => {
    try {
      const res = await api.dissectListTopicTags();
      setAllTags(res.tags || []);
    } catch {
      /* 标签列表失败不影响主流程 */
    }
  }, []);

  const loadTrash = React.useCallback(async () => {
    setTrashLoading(true);
    try {
      const res = await api.dissectListTrash();
      setTrash(res.items || []);
      setTrashTotal(res.total || 0);
    } catch (e) {
      toast(friendlyMessage(e, "读取回收站失败"), "error");
    } finally {
      setTrashLoading(false);
    }
  }, [toast]);

  React.useEffect(() => {
    if (open) {
      setTab("library");
      setSelected(new Set());
      void load();
      void loadTags();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  /** 列表内直接改优先级/状态，不用进编辑弹窗 */
  const quickPatch = async (
    item: TopicLibraryItem,
    patch: { priority?: string; status?: string }
  ) => {
    setItems((prev) => prev.map((i) => (i.id === item.id ? { ...i, ...patch } : i)));
    try {
      await api.dissectUpdateTopic(item.id, patch);
    } catch (e) {
      toast(friendlyMessage(e, "更新失败"), "error");
      void load();
    }
  };

  const openEdit = (item: TopicLibraryItem) => {
    setEditing({ ...item });
    setEditTags(item.tags || []);
  };

  const saveEdit = async () => {
    if (!editing) return;
    if (!editing.title.trim()) {
      toast("标题不能为空", "warning");
      return;
    }
    setSaving(true);
    try {
      await api.dissectUpdateTopic(editing.id, {
        title: editing.title.trim(),
        content: editing.content,
        theme: editing.theme,
        category: editing.category,
        priority: editing.priority,
        status: editing.status,
        tags: editTags,
      });
      toast("已保存", "success");
      setEditing(null);
      void load();
      void loadTags();
    } catch (e) {
      toast(friendlyMessage(e, "保存失败"), "error");
    } finally {
      setSaving(false);
    }
  };

  const confirmDelete = async () => {
    if (!pendingDelete) return;
    setDeleting(true);
    try {
      await api.dissectDeleteTopic(pendingDelete.id);
      toast(`已移入回收站：「${pendingDelete.title}」`, "success");
      setPendingDelete(null);
      void load();
      void loadTags();
    } catch (e) {
      toast(friendlyMessage(e, "删除失败"), "error");
    } finally {
      setDeleting(false);
    }
  };

  const restoreTrashItem = async (item: TrashTopic) => {
    try {
      await api.dissectRestoreTopic(item.id);
      toast(`已恢复「${item.title}」`, "success");
      void loadTrash();
      void load();
      void loadTags();
    } catch (e) {
      toast(friendlyMessage(e, "恢复失败"), "error");
    }
  };

  const confirmPurge = async () => {
    if (!pendingTrashDelete) return;
    setPurging(true);
    try {
      await api.dissectPurgeTopic(pendingTrashDelete.id);
      toast(`已彻底删除「${pendingTrashDelete.title}」`, "success");
      setPendingTrashDelete(null);
      void loadTrash();
    } catch (e) {
      toast(friendlyMessage(e, "彻底删除失败"), "error");
    } finally {
      setPurging(false);
    }
  };

  const confirmEmptyTrash = async () => {
    try {
      await api.dissectEmptyTrash();
      toast("回收站已清空", "success");
      setPendingEmptyTrash(false);
      void loadTrash();
    } catch (e) {
      toast(friendlyMessage(e, "清空失败"), "error");
    }
  };

  const resetFilter = () => {
    setCategory("全部");
    setPriority("全部");
    setStatus("全部");
    setTag("全部");
    setKeyword("");
    void load({
      category: "全部",
      priority: "全部",
      status: "全部",
      tag: "全部",
      keyword: "",
    });
  };

  // ---- 多选 / 批量 ----
  const toggleSelect = (id: string) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const batchProduce = async () => {
    const ids = Array.from(selected);
    if (ids.length === 0) return;
    setBatchBusy(true);
    try {
      const res = await api.dissectBatchProduceTopics(ids);
      toast(`已把 ${res.added} 条选题送进队列`, {
        type: "success",
        action: { label: "去队列", onClick: () => onGoTopicPage?.() },
      });
      setSelected(new Set());
      void load();
    } catch (e) {
      toast(friendlyMessage(e, "批量生产失败"), "error");
    } finally {
      setBatchBusy(false);
    }
  };

  const runBatchDelete = async () => {
    const ids = Array.from(selected);
    if (ids.length === 0) return;
    setBatchBusy(true);
    try {
      const res = await api.dissectBatchDeleteTopics(ids);
      toast(`已把 ${res.removed} 条选题移入回收站`, "success");
      setSelected(new Set());
      void load();
      void loadTags();
    } catch (e) {
      toast(friendlyMessage(e, "批量删除失败"), "error");
    } finally {
      setBatchBusy(false);
      setPendingBatchDelete(false);
    }
  };

  // ---- 版本历史 ----
  const openVersions = () => {
    if (!editing) return;
    setVersionTopicId(editing.id);
    setVersionTopicTitle(editing.title);
    setVersionCurrent(editing.content || "");
    setActiveVersion(null);
    setCompareMode(false);
    setVersionOpen(true);
    void loadVersions(editing.id);
  };

  const loadVersions = React.useCallback(
    async (topicId: string) => {
      setVersionsLoading(true);
      try {
        const res = await api.dissectListTopicVersions(topicId);
        setVersions(res.versions || []);
      } catch (e) {
        toast(friendlyMessage(e, "读取版本历史失败"), "error");
      } finally {
        setVersionsLoading(false);
      }
    },
    [toast]
  );

  const viewVersion = async (vid: string) => {
    try {
      const res = await api.dissectGetTopicVersion(versionTopicId, vid);
      setActiveVersion(res.version);
    } catch (e) {
      toast(friendlyMessage(e, "读取版本失败"), "error");
    }
  };

  const confirmRestoreVersion = async () => {
    if (!pendingRestoreVersion) return;
    setRestoring(true);
    try {
      await api.dissectRestoreTopicVersion(versionTopicId, pendingRestoreVersion);
      toast("已回退到该版本（当前内容已自动存档）", "success");
      setPendingRestoreVersion(null);
      setVersionOpen(false);
      void load();
    } catch (e) {
      toast(friendlyMessage(e, "回退失败"), "error");
    } finally {
      setRestoring(false);
    }
  };

  return (
    <>
      <Dialog open={open} onClose={onClose} className="max-w-4xl">
        <div className="mb-3 flex items-center justify-between">
          <h2 className="flex items-center gap-2 text-base font-semibold">
            <Library className="h-4 w-4" />
            选题库
          </h2>
          <Button variant="ghost" size="icon" onClick={onClose}>
            <X className="h-4 w-4" />
          </Button>
        </div>

        {/* Tab 切换 */}
        <div className="mb-3 flex items-center gap-1 rounded-lg border border-border bg-muted/20 p-1">
          <button
            type="button"
            className={cn(
              "flex items-center gap-1.5 rounded-md px-3 py-1.5 text-xs font-medium transition-colors",
              tab === "library"
                ? "bg-background text-foreground shadow-sm"
                : "text-muted-foreground hover:text-foreground"
            )}
            onClick={() => setTab("library")}
          >
            <Library className="h-3.5 w-3.5" />
            选题库
            <span className="text-[10px] text-muted-foreground">{total}</span>
          </button>
          <button
            type="button"
            className={cn(
              "flex items-center gap-1.5 rounded-md px-3 py-1.5 text-xs font-medium transition-colors",
              tab === "trash"
                ? "bg-background text-foreground shadow-sm"
                : "text-muted-foreground hover:text-foreground"
            )}
            onClick={() => {
              setTab("trash");
              void loadTrash();
            }}
          >
            <Trash2 className="h-3.5 w-3.5" />
            回收站
            <span className="text-[10px] text-muted-foreground">{trashTotal}</span>
          </button>
        </div>

        {tab === "library" ? (
          <>
            {/* 筛选栏 */}
            <div className="mb-3 flex flex-wrap items-center gap-2 rounded-lg border border-border bg-muted/20 p-2.5">
              <div className="relative min-w-[160px] flex-1">
                <Search className="absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" />
                <Input
                  className="h-8 pl-8 text-xs"
                  placeholder="搜索标题 / 主题"
                  value={keyword}
                  onChange={(e) => setKeyword(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter") void load();
                  }}
                />
              </div>
              <Select
                className="h-8 w-[104px] text-xs"
                value={category}
                onChange={(e) => {
                  setCategory(e.target.value);
                  void load({ category: e.target.value });
                }}
              >
                {CAT_OPTIONS.map((o) => (
                  <option key={o} value={o}>
                    {o === "全部" ? "全部分类" : o}
                  </option>
                ))}
              </Select>
              <Select
                className="h-8 w-[96px] text-xs"
                value={priority}
                onChange={(e) => {
                  setPriority(e.target.value);
                  void load({ priority: e.target.value });
                }}
              >
                {PRI_OPTIONS.map((o) => (
                  <option key={o} value={o}>
                    {o === "全部" ? "全部优先级" : `${o}优先`}
                  </option>
                ))}
              </Select>
              <Select
                className="h-8 w-[100px] text-xs"
                value={status}
                onChange={(e) => {
                  setStatus(e.target.value);
                  void load({ status: e.target.value });
                }}
              >
                {STA_OPTIONS.map((o) => (
                  <option key={o} value={o}>
                    {o === "全部" ? "全部状态" : o}
                  </option>
                ))}
              </Select>
              <Select
                className="h-8 w-[104px] text-xs"
                value={tag}
                onChange={(e) => {
                  setTag(e.target.value);
                  void load({ tag: e.target.value });
                }}
              >
                <option value="全部">全部标签</option>
                {allTags.map((t) => (
                  <option key={t} value={t}>
                    {t}
                  </option>
                ))}
              </Select>
              <Button size="xs" variant="outline" onClick={() => void load()}>
                <RefreshCw className={cn("h-3 w-3", loading && "animate-spin")} />
                查询
              </Button>
              <Button size="xs" variant="ghost" onClick={resetFilter}>
                重置
              </Button>
            </div>

            {/* 批量操作条 */}
            {selected.size > 0 && (
              <div className="mb-3 flex flex-wrap items-center gap-2 rounded-lg border border-primary/40 bg-primary/5 px-3 py-2 text-xs">
                <span className="font-medium">已选 {selected.size} 项</span>
                <div className="ml-auto flex gap-2">
                  <Button
                    size="xs"
                    variant="outline"
                    onClick={batchProduce}
                    disabled={batchBusy}
                  >
                    <Rocket className={cn("mr-1 h-3 w-3", batchBusy && "animate-spin")} />
                    批量生产
                  </Button>
                  <Button
                    size="xs"
                    variant="destructive"
                    onClick={() => setPendingBatchDelete(true)}
                    disabled={batchBusy}
                  >
                    <Trash2 className="mr-1 h-3 w-3" />
                    批量删除
                  </Button>
                  <Button
                    size="xs"
                    variant="ghost"
                    onClick={() => setSelected(new Set())}
                  >
                    取消选择
                  </Button>
                </div>
              </div>
            )}

            <div className="mb-2 text-xs text-muted-foreground">
              共 {total} 条，当前筛选出 {items.length} 条
            </div>
          </>
        ) : (
          <div className="mb-3 flex items-center justify-between rounded-lg border border-border bg-muted/20 px-3 py-2">
            <span className="text-xs text-muted-foreground">
              回收站共 {trashTotal} 条，删除的选题会先到这里，可恢复或彻底删除。
            </span>
            {trashTotal > 0 && (
              <Button size="xs" variant="destructive" onClick={() => setPendingEmptyTrash(true)}>
                <Trash2 className="mr-1 h-3 w-3" />
                清空回收站
              </Button>
            )}
          </div>
        )}

        {/* 列表 */}
        <div className="max-h-[52vh] overflow-y-auto pr-1">
          {tab === "library" ? (
            loading ? (
              <div className="flex items-center justify-center gap-2 py-12 text-sm text-muted-foreground">
                <Loader2 className="h-4 w-4 animate-spin" />
                加载中…
              </div>
            ) : items.length === 0 ? (
              <EmptyState
                icon={Library}
                title={total > 0 ? "当前筛选条件下没有选题" : "选题库还是空的"}
                description={
                  total > 0
                    ? "把分类/优先级/状态/标签调回「全部」再看看。"
                    : "在拆解结果里点「加入选题库」，存下来的选题会显示在这里。"
                }
                action={
                  total > 0 ? (
                    <Button size="sm" variant="outline" onClick={resetFilter}>
                      重置筛选
                    </Button>
                  ) : undefined
                }
              />
            ) : (
              <div className="space-y-2">
                {items.map((item) => {
                  const checked = selected.has(item.id);
                  return (
                    <div
                      key={item.id}
                      className={cn(
                        "rounded-lg border bg-muted/20 p-3 transition-colors",
                        checked ? "border-primary/60 bg-primary/5" : "border-border"
                      )}
                    >
                      <div className="flex items-start justify-between gap-3">
                        <div className="flex min-w-0 flex-1 gap-2">
                          <input
                            type="checkbox"
                            className="mt-1 h-4 w-4 shrink-0 cursor-pointer rounded border-border accent-primary"
                            checked={checked}
                            onChange={() => toggleSelect(item.id)}
                            aria-label={`选择 ${item.title}`}
                          />
                          <div className="min-w-0 flex-1">
                            <div className="text-sm font-medium leading-snug text-foreground">
                              {item.title}
                            </div>
                            <div className="mt-1.5 flex flex-wrap items-center gap-1.5 text-xs text-muted-foreground">
                              <Badge variant="secondary">{item.theme}</Badge>
                              <Badge variant="muted">{item.category}</Badge>
                              <Badge variant={priorityVariant(item.priority)}>
                                {item.priority}优先
                              </Badge>
                              <Badge variant={statusVariant(item.status)}>
                                {item.status}
                              </Badge>
                              <span>{item.updated_at || item.created_at}</span>
                            </div>
                            {(item.tags && item.tags.length > 0) && (
                              <div className="mt-1.5 flex flex-wrap items-center gap-1">
                                <Tag className="h-3 w-3 text-muted-foreground" />
                                {item.tags.map((t) => (
                                  <Badge key={t} variant="outline" className="text-[10px]">
                                    {t}
                                  </Badge>
                                ))}
                              </div>
                            )}
                          </div>
                        </div>
                        <div className="flex shrink-0 items-center gap-1">
                          <Select
                            className="h-7 w-[84px] text-xs"
                            value={item.status}
                            onChange={(e) => void quickPatch(item, { status: e.target.value })}
                          >
                            {TOPIC_STATUSES.map((o) => (
                              <option key={o} value={o}>
                                {o}
                              </option>
                            ))}
                          </Select>
                          <Select
                            className="h-7 w-[64px] text-xs"
                            value={item.priority}
                            onChange={(e) => void quickPatch(item, { priority: e.target.value })}
                          >
                            {TOPIC_PRIORITIES.map((o) => (
                              <option key={o} value={o}>
                                {o}
                              </option>
                            ))}
                          </Select>
                        </div>
                      </div>

                      {item.content && (
                        <p className="mt-2 line-clamp-2 text-xs leading-relaxed text-muted-foreground">
                          {item.content.replace(/<font color="red">|<\/font>|\*\*|#/g, "")}
                        </p>
                      )}

                      <div className="mt-2 flex flex-wrap items-center justify-end gap-1">
                        {onProduce && (
                          <Button variant="ghost" size="xs" onClick={() => onProduce(item)}>
                            <Rocket className="mr-1 h-3 w-3" />
                            拿去生产
                          </Button>
                        )}
                        <Button
                          variant="ghost"
                          size="xs"
                          onClick={async () => {
                            try {
                              await navigator.clipboard?.writeText(
                                `${item.title}\n\n${item.content}`
                              );
                              toast("已复制", "success");
                            } catch {
                              toast("复制失败", "error");
                            }
                          }}
                        >
                          <Copy className="mr-1 h-3 w-3" />
                          复制
                        </Button>
                        <Button variant="ghost" size="xs" onClick={() => openEdit(item)}>
                          <Pencil className="mr-1 h-3 w-3" />
                          编辑
                        </Button>
                        <Button
                          variant="ghost"
                          size="xs"
                          className="text-destructive hover:text-destructive"
                          onClick={() => setPendingDelete(item)}
                        >
                          <Trash2 className="mr-1 h-3 w-3" />
                          删除
                        </Button>
                      </div>
                    </div>
                  );
                })}
              </div>
            )
          ) : trashLoading ? (
            <div className="flex items-center justify-center gap-2 py-12 text-sm text-muted-foreground">
              <Loader2 className="h-4 w-4 animate-spin" />
              加载中…
            </div>
          ) : trash.length === 0 ? (
            <EmptyState
              icon={Trash2}
              title="回收站是空的"
              description="在选题库里删除的选题会出现在这里，可随时恢复。"
            />
          ) : (
            <div className="space-y-2">
              {trash.map((item) => (
                <div
                  key={item.id}
                  className="rounded-lg border border-border bg-muted/20 p-3"
                >
                  <div className="flex items-start justify-between gap-3">
                    <div className="min-w-0 flex-1">
                      <div className="text-sm font-medium leading-snug text-foreground">
                        {item.title}
                      </div>
                      <div className="mt-1.5 flex flex-wrap items-center gap-1.5 text-xs text-muted-foreground">
                        <Badge variant="muted">{item.category}</Badge>
                        <Badge variant={priorityVariant(item.priority)}>
                          {item.priority}优先
                        </Badge>
                        <span>删除于 {item.deleted_at}</span>
                      </div>
                      {(item.tags && item.tags.length > 0) && (
                        <div className="mt-1.5 flex flex-wrap items-center gap-1">
                          <Tag className="h-3 w-3 text-muted-foreground" />
                          {item.tags.map((t) => (
                            <Badge key={t} variant="outline" className="text-[10px]">
                              {t}
                            </Badge>
                          ))}
                        </div>
                      )}
                    </div>
                  </div>
                  <div className="mt-2 flex flex-wrap items-center justify-end gap-1">
                    <Button variant="ghost" size="xs" onClick={() => void restoreTrashItem(item)}>
                      <Undo2 className="mr-1 h-3 w-3" />
                      恢复
                    </Button>
                    <Button
                      variant="ghost"
                      size="xs"
                      className="text-destructive hover:text-destructive"
                      onClick={() => setPendingTrashDelete(item)}
                    >
                      <Trash2 className="mr-1 h-3 w-3" />
                      彻底删除
                    </Button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>

        {onGoTopicPage && tab === "library" && (
          <div className="mt-4 flex justify-end">
            <Button variant="outline" onClick={onGoTopicPage}>
              <ExternalLink className="mr-1.5 h-4 w-4" />
              去选题与生产页
            </Button>
          </div>
        )}
      </Dialog>

      {/* 编辑弹窗 */}
      <Dialog
        open={!!editing}
        onClose={() => (saving ? undefined : setEditing(null))}
        className="max-w-2xl"
      >
        {editing && (
          <>
            <div className="mb-3 flex items-center justify-between">
              <h3 className="text-base font-semibold">编辑选题</h3>
              <Button variant="ghost" size="xs" onClick={openVersions}>
                <History className="mr-1 h-3 w-3" />
                版本历史（{versions.length}）
              </Button>
            </div>
            <div className="space-y-3">
              <div>
                <label className="mb-1 block text-xs text-muted-foreground">标题</label>
                <Input
                  value={editing.title}
                  onChange={(e) => setEditing({ ...editing, title: e.target.value })}
                />
              </div>
              <div className="grid grid-cols-3 gap-2">
                <div>
                  <label className="mb-1 block text-xs text-muted-foreground">分类</label>
                  <Select
                    value={editing.category}
                    onChange={(e) => setEditing({ ...editing, category: e.target.value })}
                  >
                    {TOPIC_CATEGORIES.map((o) => (
                      <option key={o} value={o}>
                        {o}
                      </option>
                    ))}
                  </Select>
                </div>
                <div>
                  <label className="mb-1 block text-xs text-muted-foreground">优先级</label>
                  <Select
                    value={editing.priority}
                    onChange={(e) => setEditing({ ...editing, priority: e.target.value })}
                  >
                    {TOPIC_PRIORITIES.map((o) => (
                      <option key={o} value={o}>
                        {o}
                      </option>
                    ))}
                  </Select>
                </div>
                <div>
                  <label className="mb-1 block text-xs text-muted-foreground">状态</label>
                  <Select
                    value={editing.status}
                    onChange={(e) => setEditing({ ...editing, status: e.target.value })}
                  >
                    {TOPIC_STATUSES.map((o) => (
                      <option key={o} value={o}>
                        {o}
                      </option>
                    ))}
                  </Select>
                </div>
              </div>
              <div>
                <label className="mb-1 block text-xs text-muted-foreground">标签</label>
                <TagInput value={editTags} onChange={setEditTags} />
              </div>
              <div>
                <label className="mb-1 block text-xs text-muted-foreground">
                  正文（Markdown）
                </label>
                <Textarea
                  className="h-64 font-mono text-xs"
                  value={editing.content}
                  onChange={(e) => setEditing({ ...editing, content: e.target.value })}
                />
              </div>
            </div>
            <div className="mt-4 flex justify-end gap-2">
              <Button variant="ghost" onClick={() => setEditing(null)} disabled={saving}>
                取消
              </Button>
              <Button onClick={saveEdit} disabled={saving}>
                {saving && <Loader2 className="mr-1.5 h-4 w-4 animate-spin" />}
                保存
              </Button>
            </div>
          </>
        )}
      </Dialog>

      {/* 版本历史弹窗 */}
      <Dialog open={versionOpen} onClose={() => setVersionOpen(false)} className="max-w-3xl">
        {versionOpen && (
          <>
            <div className="mb-3 flex items-center justify-between">
              <h3 className="flex items-center gap-2 text-base font-semibold">
                <History className="h-4 w-4" />
                版本历史
                <span className="text-xs font-normal text-muted-foreground">
                  {versionTopicTitle}
                </span>
              </h3>
              <Button variant="ghost" size="icon" onClick={() => setVersionOpen(false)}>
                <X className="h-4 w-4" />
              </Button>
            </div>

            <div className="grid grid-cols-1 gap-3 md:grid-cols-[200px_1fr]">
              {/* 版本列表 */}
              <div className="max-h-[50vh] space-y-1.5 overflow-y-auto border-border pr-1 md:border-r md:pr-3">
                {versionsLoading ? (
                  <div className="flex items-center gap-2 py-6 text-xs text-muted-foreground">
                    <Loader2 className="h-3.5 w-3.5 animate-spin" />
                    加载中…
                  </div>
                ) : versions.length === 0 ? (
                  <p className="py-6 text-xs text-muted-foreground">暂无历史版本。</p>
                ) : (
                  versions.map((v) => (
                    <button
                      key={v.version_id}
                      type="button"
                      onClick={() => void viewVersion(v.version_id)}
                      className={cn(
                        "w-full rounded-md border px-2.5 py-2 text-left text-xs transition-colors",
                        activeVersion?.version_id === v.version_id
                          ? "border-primary/60 bg-primary/5"
                          : "border-border hover:bg-muted/40"
                      )}
                    >
                      <div className="font-medium text-foreground">{v.saved_at}</div>
                      <div className="mt-0.5 line-clamp-1 text-muted-foreground">
                        {v.title || "（无标题）"}
                      </div>
                      <div className="mt-0.5 text-[10px] text-muted-foreground">
                        {v.content_len} 字
                      </div>
                    </button>
                  ))
                )}
              </div>

              {/* 预览 / 对比 */}
              <div className="max-h-[50vh] overflow-y-auto">
                {!activeVersion ? (
                  <div className="flex h-full items-center justify-center py-10 text-xs text-muted-foreground">
                    从左侧选择一个版本查看内容
                  </div>
                ) : (
                  <div className="space-y-2">
                    <div className="flex items-center justify-between">
                      <span className="text-xs text-muted-foreground">
                        版本 {activeVersion.saved_at}
                        {compareMode ? " · 与当前对比" : ""}
                      </span>
                      <div className="flex items-center gap-2">
                        {versions.length > 0 && (
                          <Button
                            size="xs"
                            variant="outline"
                            onClick={() => setCompareMode((m) => !m)}
                          >
                            <Eye className="mr-1 h-3 w-3" />
                            {compareMode ? "仅看版本" : "对比当前"}
                          </Button>
                        )}
                        <Button
                          size="xs"
                          variant="destructive"
                          onClick={() => setPendingRestoreVersion(activeVersion.version_id)}
                        >
                          <RotateCcw className="mr-1 h-3 w-3" />
                          回退到此版本
                        </Button>
                      </div>
                    </div>

                    {compareMode ? (
                      <div className="grid grid-cols-1 gap-2 md:grid-cols-2">
                        <div>
                          <div className="mb-1 text-[10px] font-medium text-muted-foreground">
                            当前（编辑中）
                          </div>
                          <Textarea
                            readOnly
                            className="h-64 bg-muted/30 font-mono text-xs"
                            value={versionCurrent}
                          />
                        </div>
                        <div>
                          <div className="mb-1 text-[10px] font-medium text-muted-foreground">
                            历史版本
                          </div>
                          <Textarea
                            readOnly
                            className="h-64 bg-muted/30 font-mono text-xs"
                            value={activeVersion.content}
                          />
                        </div>
                      </div>
                    ) : (
                      <Textarea
                        readOnly
                        className="h-64 bg-muted/30 font-mono text-xs"
                        value={activeVersion.content}
                      />
                    )}
                  </div>
                )}
              </div>
            </div>
          </>
        )}
      </Dialog>

      <ConfirmDialog
        open={!!pendingDelete}
        title="删除这条选题？"
        description={
          <>
            将把「<span className="text-foreground">{pendingDelete?.title}</span>
            」移入回收站，可在回收站里恢复。
          </>
        }
        confirmText="移入回收站"
        loading={deleting}
        onConfirm={confirmDelete}
        onCancel={() => setPendingDelete(null)}
      />

      <ConfirmDialog
        open={!!pendingTrashDelete}
        title="彻底删除这条选题？"
        description={
          <>
            将永久删除「<span className="text-foreground">{pendingTrashDelete?.title}</span>
            」，无法恢复。
          </>
        }
        confirmText="彻底删除"
        loading={purging}
        onConfirm={confirmPurge}
        onCancel={() => setPendingTrashDelete(null)}
      />

      <ConfirmDialog
        open={pendingEmptyTrash}
        title="清空回收站？"
        description="回收站里的所有选题都会被永久删除，无法恢复。"
        confirmText="清空"
        onConfirm={confirmEmptyTrash}
        onCancel={() => setPendingEmptyTrash(false)}
      />

      <ConfirmDialog
        open={!!pendingRestoreVersion}
        title="回退到该历史版本？"
        description="当前内容会先自动存档，再替换为正文历史版本，可再次回退。"
        confirmText="回退"
        loading={restoring}
        onConfirm={confirmRestoreVersion}
        onCancel={() => setPendingRestoreVersion(null)}
      />

      <ConfirmDialog
        open={pendingBatchDelete}
        title={`批量删除 ${selected.size} 条选题？`}
        description="选中的选题会被移入回收站，可在回收站里恢复。"
        confirmText="批量删除"
        loading={batchBusy}
        onConfirm={runBatchDelete}
        onCancel={() => setPendingBatchDelete(false)}
      />
    </>
  );
}
