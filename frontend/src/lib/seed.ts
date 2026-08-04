// 页面之间传递「选题参考」的轻量中转层。
// 用 sessionStorage 而不是全局状态，是为了刷新页面后仍然保留，同时关掉标签页就自动清掉。
import type { TopicSeed } from "./types";

const KEY = "topic_seeds";

function safeParse(raw: string | null): TopicSeed[] {
  if (!raw) return [];
  try {
    const arr = JSON.parse(raw);
    return Array.isArray(arr) ? (arr as TopicSeed[]) : [];
  } catch {
    return [];
  }
}

export const topicSeeds = {
  /** 读取全部选题参考。 */
  all(): TopicSeed[] {
    if (typeof window === "undefined") return [];
    return safeParse(sessionStorage.getItem(KEY));
  },

  /** 追加一条，主题相同则跳过；返回追加后的总数。 */
  add(seed: TopicSeed): number {
    if (typeof window === "undefined") return 0;
    const list = safeParse(sessionStorage.getItem(KEY));
    if (!list.some((s) => s.topic === seed.topic)) list.push(seed);
    sessionStorage.setItem(KEY, JSON.stringify(list));
    return list.length;
  },

  /** 批量追加，返回追加后的总数。 */
  addMany(seeds: TopicSeed[]): number {
    if (typeof window === "undefined") return 0;
    const list = safeParse(sessionStorage.getItem(KEY));
    for (const s of seeds) {
      if (!list.some((x) => x.topic === s.topic)) list.push(s);
    }
    sessionStorage.setItem(KEY, JSON.stringify(list));
    return list.length;
  },

  remove(topic: string): TopicSeed[] {
    if (typeof window === "undefined") return [];
    const list = safeParse(sessionStorage.getItem(KEY)).filter(
      (s) => s.topic !== topic
    );
    sessionStorage.setItem(KEY, JSON.stringify(list));
    return list;
  },

  clear(): void {
    if (typeof window === "undefined") return;
    sessionStorage.removeItem(KEY);
  },
};

/** 队列页 / 选题页读取「预填表单」用的一次性草稿。 */
const DRAFT_KEY = "queue_draft";

export interface QueueDraft {
  topic: string;
  angle?: string;
  extra?: string;
}

export const queueDraft = {
  set(draft: QueueDraft): void {
    if (typeof window === "undefined") return;
    sessionStorage.setItem(DRAFT_KEY, JSON.stringify(draft));
  },
  /** 取出并清除（一次性）。 */
  take(): QueueDraft | null {
    if (typeof window === "undefined") return null;
    const raw = sessionStorage.getItem(DRAFT_KEY);
    if (!raw) return null;
    sessionStorage.removeItem(DRAFT_KEY);
    try {
      return JSON.parse(raw) as QueueDraft;
    } catch {
      return null;
    }
  },
};
