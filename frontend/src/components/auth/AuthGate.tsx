"use client";

import { useCallback, useEffect, useState } from "react";
import { api, clearAuthToken, friendlyMessage, getAuthToken, setAuthToken } from "@/lib/api";

/**
 * 访问鉴权门：
 * - 挂载时查询后端 /api/auth/status；
 * - 若后端开启了鉴权且本地没有令牌，弹出登录框要求输入访问令牌；
 * - 令牌自动存入 localStorage，api.ts 的 request 会附带到每个请求；
 * - 任意请求返回 401 时，api.ts 会清空令牌并广播 workbench:unauthorized，
 *   这里重新弹窗提示。
 * 后端默认（本地）关闭鉴权，此组件不会拦截任何操作。
 */
export function AuthGate({ children }: { children: React.ReactNode }) {
  const [checked, setChecked] = useState(false);
  const [needLogin, setNeedLogin] = useState(false);
  const [token, setToken] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const check = useCallback(async () => {
    try {
      const status = await api.authStatus();
      if (status.enabled && !getAuthToken()) {
        setNeedLogin(true);
      } else {
        setNeedLogin(false);
      }
    } catch {
      // 状态接口拿不到（网络/后端未起）：本地默认关鉴权，直接放行
      setNeedLogin(false);
    } finally {
      setChecked(true);
    }
  }, []);

  useEffect(() => {
    void check();
    const onUnauth = () => {
      clearAuthToken();
      setError("访问令牌已失效，请重新输入");
      setNeedLogin(true);
    };
    window.addEventListener("workbench:unauthorized", onUnauth);
    return () => window.removeEventListener("workbench:unauthorized", onUnauth);
  }, [check]);

  const submit = async () => {
    setError("");
    const value = token.trim();
    if (!value) {
      setError("请输入访问令牌");
      return;
    }
    setBusy(true);
    try {
      setAuthToken(value);
      // 用一个受保护接口验证令牌（鉴权关闭时也会 200，不影响本地使用）
      await api.getConfig();
      setError("");
      setNeedLogin(false);
    } catch (e) {
      clearAuthToken();
      const err = e as { status?: number };
      if (err?.status === 401) {
        setError("访问令牌不正确，请重试");
      } else {
        setError(friendlyMessage(e, "验证失败，请重试"));
      }
    } finally {
      setBusy(false);
    }
  };

  return (
    <>
      {/* 检查中（checked=false）或需要登录（needLogin=true）时不渲染业务内容，
          避免子组件（侧边栏/页面）提前发起大量请求导致控制台刷 401、页面闪烁。
          仅当 checked && !needLogin 才正常渲染 children。 */}
      {checked && !needLogin ? children : null}

      {/* 检查中：全屏 loading，挡在内容之前 */}
      {!checked && (
        <div className="fixed inset-0 z-40 flex items-center justify-center bg-background">
          <div className="h-10 w-10 animate-spin rounded-full border-4 border-muted border-t-primary" />
        </div>
      )}

      {/* 需要登录：只弹登录框，背后不渲染 children（已在上方置为 null） */}
      {checked && needLogin && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4">
          <div className="w-full max-w-sm rounded-xl border border-border bg-card p-6 shadow-2xl">
            <h2 className="text-lg font-semibold text-foreground">需要登录</h2>
            <p className="mt-1 text-sm text-muted-foreground">
              该工作台已开启访问鉴权，请输入部署时配置的访问令牌。
            </p>
            <input
              type="password"
              autoFocus
              value={token}
              onChange={(e) => setToken(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !busy) void submit();
              }}
              placeholder="访问令牌"
              className="mt-4 w-full rounded-lg border border-border bg-background px-3 py-2 text-foreground outline-none focus:border-primary"
            />
            {error && (
              <p className="mt-2 text-sm text-destructive">{error}</p>
            )}
            <button
              type="button"
              disabled={busy}
              onClick={() => void submit()}
              className="mt-4 w-full rounded-lg bg-primary px-4 py-2 font-medium text-primary-foreground transition-colors hover:opacity-90 disabled:opacity-50"
            >
              {busy ? "验证中…" : "进入工作台"}
            </button>
          </div>
        </div>
      )}
    </>
  );
}
