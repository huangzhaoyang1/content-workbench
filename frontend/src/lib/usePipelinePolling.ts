"use client";

import * as React from "react";
import { api } from "@/lib/api";
import type { PipelineStatus } from "@/lib/types";

interface UsePipelinePollingOptions {
  /** 任务 id；为 null 时不轮询（例如尚未启动或已离开运行态）。 */
  taskId: string | null;
  /** 每次拿到状态后回调（用于就地刷新日志/进度）。 */
  onStatus?: (st: PipelineStatus) => void;
  /** 终态（success/failed）或异常时回调，参数为最终状态（异常为 null）。 */
  onDone?: (st: PipelineStatus | null) => void;
  /** 轮询间隔，默认 1500ms，对齐热点线 /topic。 */
  intervalMs?: number;
}

/**
 * 流水线状态轮询钩子：
 *  - 每 intervalMs 调一次 api.pipelineStatus；
 *  - 返回 success / failed 或抛异常时自动停止轮询并触发 onDone；
 *  - 抖音线 DissectPanel 与热点线 /topic 共用，避免双线重复实现轮询逻辑。
 * onStatus / onDone 通过 ref 持有最新值，避免回调变化导致重复订阅。
 */
export function usePipelinePolling({
  taskId,
  onStatus,
  onDone,
  intervalMs = 1500,
}: UsePipelinePollingOptions) {
  const [running, setRunning] = React.useState(false);
  const onStatusRef = React.useRef(onStatus);
  const onDoneRef = React.useRef(onDone);

  React.useEffect(() => {
    onStatusRef.current = onStatus;
    onDoneRef.current = onDone;
  });

  React.useEffect(() => {
    if (!taskId) {
      setRunning(false);
      return;
    }
    let active = true;
    setRunning(true);
    const timer = setInterval(async () => {
      if (!active) return;
      try {
        const st = await api.pipelineStatus(taskId);
        onStatusRef.current?.(st);
        if (st.status === "success" || st.status === "failed") {
          active = false;
          clearInterval(timer);
          setRunning(false);
          onDoneRef.current?.(st);
        }
      } catch {
        active = false;
        clearInterval(timer);
        setRunning(false);
        onDoneRef.current?.(null);
      }
    }, intervalMs);
    return () => {
      active = false;
      clearInterval(timer);
      setRunning(false);
    };
  }, [taskId, intervalMs]);

  return { running };
}
