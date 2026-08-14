import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { vi, describe, it, expect, beforeEach, type Mock } from "vitest";
import { api } from "@/lib/api";
import { ConfirmPublishDialog } from "@/components/tasks/ConfirmPublishDialog";

vi.mock("@/lib/api", () => ({
  api: { regenerateCover: vi.fn() },
  friendlyMessage: (_e: unknown, m: string) => m,
}));

describe("ConfirmPublishDialog（发布三步弹窗）", () => {
  beforeEach(() => vi.clearAllMocks());

  it("预览就绪前确认按钮禁用；生成预览就绪后可点击并回调 onConfirm", async () => {
    (api.regenerateCover as unknown as Mock).mockResolvedValue({
      ok: true,
      cover_base64: "data:image/png;base64,AAA",
    });
    const onConfirm = vi.fn();
    const onClose = vi.fn();

    render(
      <ConfirmPublishDialog open issue={3} onConfirm={onConfirm} onClose={onClose} />
    );

    // ① 期号输入渲染（默认「第 3 期」）
    const input = screen.getByLabelText(/封面期号标识/) as HTMLInputElement;
    expect(input.value).toBe("第 3 期");

    // ③ 预览未就绪：确认按钮禁用，文案为「请先生成封面预览」
    const confirmBtn = screen.getByRole("button", {
      name: /请先生成封面预览/,
    }) as HTMLButtonElement;
    expect(confirmBtn).toBeDisabled();

    // ② 点「生成封面预览」→ 调 regenerateCover(issue, label)
    fireEvent.click(screen.getByRole("button", { name: /^生成封面预览$/ }));
    await waitFor(() =>
      expect(api.regenerateCover).toHaveBeenCalledWith(3, "第 3 期")
    );

    // 预览就绪：确认按钮可用，文案变为「确认发布」
    const readyBtn = (await screen.findByRole("button", {
      name: "确认发布",
    })) as HTMLButtonElement;
    expect(readyBtn).toBeEnabled();

    // 点击确认 → 回调 onConfirm(label) 并关闭
    fireEvent.click(readyBtn);
    expect(onConfirm).toHaveBeenCalledWith("第 3 期");
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("预览失败时不阻塞，仍提供「直接发布（无预览）」入口", async () => {
    (api.regenerateCover as unknown as Mock).mockResolvedValue({
      ok: false,
      reason: "封面生成失败",
    });
    const onConfirm = vi.fn();
    const onClose = vi.fn();

    render(
      <ConfirmPublishDialog open issue={5} onConfirm={onConfirm} onClose={onClose} />
    );

    fireEvent.click(screen.getByRole("button", { name: /^生成封面预览$/ }));
    const directBtn = await screen.findByRole("button", {
      name: /直接发布（无预览）/,
    });
    expect(directBtn).toBeEnabled();
    fireEvent.click(directBtn);
    expect(onConfirm).toHaveBeenCalledWith("第 5 期");
  });
});
