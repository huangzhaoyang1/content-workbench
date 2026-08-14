import { describe, it, expect, vi, beforeEach, afterEach, type Mock } from "vitest";
import { renderHook, act } from "@testing-library/react";
import { api } from "@/lib/api";
import { usePipelinePolling } from "@/lib/usePipelinePolling";
import type { PipelineStatus } from "@/lib/types";

vi.mock("@/lib/api", () => ({
  api: { pipelineStatus: vi.fn() },
}));

const running = {
  status: "running",
  task_id: "t1",
  logs: "step1",
} as unknown as PipelineStatus;
const success = {
  status: "success",
  task_id: "t1",
  logs: "done",
} as unknown as PipelineStatus;

describe("usePipelinePolling（队列轮询逻辑）", () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });
  afterEach(() => {
    vi.useRealTimers();
    vi.clearAllMocks();
  });

  it("每 1500ms 轮询一次，success 终态后停止轮询", async () => {
    let i = 0;
    (api.pipelineStatus as unknown as Mock).mockImplementation(
      async () => [running, success][i++]
    );
    const onStatus = vi.fn();
    const onDone = vi.fn();

    renderHook(() =>
      usePipelinePolling({ taskId: "t1", onStatus, onDone, intervalMs: 1500 })
    );

    // 首次轮询在 1500ms 后触发
    await act(async () => {
      await vi.advanceTimersByTimeAsync(1500);
    });
    expect(api.pipelineStatus).toHaveBeenCalledTimes(1);
    expect(onStatus).toHaveBeenCalledTimes(1);
    expect(onDone).not.toHaveBeenCalled();

    // 第二次轮询 → success → 停止
    await act(async () => {
      await vi.advanceTimersByTimeAsync(1500);
    });
    expect(api.pipelineStatus).toHaveBeenCalledTimes(2);
    expect(onDone).toHaveBeenCalledTimes(1);
    expect(onDone).toHaveBeenCalledWith(success);

    // 继续推进时间，不应再发起轮询
    await act(async () => {
      await vi.advanceTimersByTimeAsync(5000);
    });
    expect(api.pipelineStatus).toHaveBeenCalledTimes(2);
  });

  it("taskId 为 null 时不轮询", async () => {
    (api.pipelineStatus as unknown as Mock).mockResolvedValue(running);
    const onStatus = vi.fn();
    const onDone = vi.fn();

    renderHook(() =>
      usePipelinePolling({ taskId: null, onStatus, onDone, intervalMs: 1500 })
    );
    await act(async () => {
      await vi.advanceTimersByTimeAsync(3000);
    });
    expect(api.pipelineStatus).not.toHaveBeenCalled();
  });
});
