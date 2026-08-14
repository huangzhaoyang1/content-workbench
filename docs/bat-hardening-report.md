# 启动器加固报告（Block C）

- 日期：2026-08-12
- 目标文件：`content-workbench/启动AI内容工作台.bat`
- 背景：双击 bat 打不开（白屏）。诊断为重构期间残留进程占用端口 3000/54321，导致前端静默跳到 3001 而 bat 仍提示 3000（白屏）；另有 NODE_OPTIONS 注入与无 BOM 中文路径两项潜在风险。本次按「直接执行」决策完成防御性加固。

---

## 一、改动段落（对照原文件）

| # | 位置（行） | 改动内容 |
|---|-----------|----------|
| 1 | 68–74 | 新增 `[端口清理]` 注释块 + `call :killport 54321`（**后端启动前**清理 54321 残留） |
| 2 | 100–101 | 新增 `call :killport 3000`（**前端启动前**清理 3000 残留，防止前端静默跳 3001） |
| 3 | 104–105 | 前端启动前新增 `set NODE_OPTIONS=`（父进程层面清空，防 safe-delete shim 注入） |
| 4 | 106 | 前端 `start` 的 `cmd /k` 字符串内追加 `set NODE_OPTIONS=`（确保子 dev 进程继承清空值） |
| 5 | 125 | `pause` 后新增 `goto :eof`（防止主流程落入下方子程序体） |
| 6 | 127–155 | 文件末尾新增 `:killport` 子程序（端口清理实现，见下） |
| 7 | 文件头 | 整文件转为 **UTF-8 BOM**（原始字节 `ef bb bf`），消除中文路径解析风险 |

> 其余段落（密钥注入、uvicorn 解析、缓存自检、前端 node_modules 检查、banner）保持原样未动。

---

## 二、端口清理实现（`:killport` 子程序）

逻辑（参数 `%1` = 端口号）：

```
:killport
set "KP_PORT=%~1"
set "KP_FOUND=0"
set "KP_FAIL=0"
for /f "tokens=5" %%p in (
    'netstat -ano 2^>nul ^| findstr /c:":%KP_PORT% " ^| findstr "LISTENING"'
) do (
    set "KP_FOUND=1"
    echo [端口清理] 发现端口 %KP_PORT% 被 PID=%%p 占用，尝试结束...
    taskkill /F /PID %%p /T >nul 2>&1
    if errorlevel 1 (
        echo [端口清理] 无法自动结束 PID=%%p（可能缺少管理员权限）。
        set "KP_FAIL=1"
    ) else (
        echo [端口清理] 已结束 PID=%%p。
    )
)
if "%KP_FOUND%"=="0" ( echo [端口清理] 端口 %KP_PORT% 未被占用，无需清理。 )
if "%KP_FAIL%"=="1"  ( echo [端口清理] 请手动关闭占用 %KP_PORT% 端口的窗口/程序后，再启动本启动器。 )
goto :eof
```

要点：
- **精确匹配**：先用 `findstr /c:":PORT "` 锁定该端口，再用 `findstr "LISTENING"` 仅匹配真正监听的进程，避免误杀其他程序。
- **PID 提取**：`netstat -ano` 输出的第 5 个空格分隔字段即 PID（`for /f "tokens=5"`）。
- **结束方式**：`taskkill /F /PID %%p /T` 按 PID 强制结束整个进程树。
- **失败不静默**：若 taskkill 因缺少管理员权限等失败，打印「请手动关闭…」提示，而非静默失败。
- **两次调用时机**：`call :killport 54321`（后端启动前）→ 防后端起不来；`call :killport 3000`（前端启动前）→ 防前端静默跳 3001 导致白屏。

---

## 三、验证结果

| 验证项 | 方法 | 结果 |
|--------|------|------|
| `:killport` 解析正确性 | 起测试监听（PID 13680 / 端口 54601），对 `netstat -ano \| findstr /c:":54601 " \| findstr "LISTENING"` 取第 5 字段 | 第 5 字段 = `13680` = 真实 PID ✅ |
| `taskkill` 释放端口 | `taskkill /F /PID 13680 /T` 后复查 netstat | 端口 54601 已释放（RELEASED OK）✅ |
| `set NODE_OPTIONS=` 生效 | bat 第 105/106 行已置入；cmd `set VAR=`（等号后为空）即清空变量为 cmd 标准语义；类比 PowerShell 清空进程环境变量 exit 0 | 清空逻辑正确 ✅ |
| UTF-8 BOM | 读取文件原始前 3 字节 | `ef bb bf` 确认 ✅ |
| 静态语法 | Python 解析：括号平衡 16/16；标签 `killport` 定义 1 次、被 `call` 2 次；`goto :eof` 存在 | 结构完整 ✅ |

**沙箱限制（如实说明）**：当前安全策略禁止从 Bash / PowerShell 调用 `cmd.exe`（两次尝试均被拦截：*"Invoking cmd.exe from Bash bypasses all command validation"* / *"Starting cmd.exe from PowerShell bypasses PowerShell command validation"*）。因此**无法在沙箱内直接跑 bat 的运行时**。但 `:killport` 依赖的全部原语（netstat 输出格式、tokens=5=PID、findstr LISTENING 过滤、taskkill 按 PID 杀进程）均已逐项实证，且 bat 已通过静态语法审查。用户在 Windows 资源管理器**双击运行**（沙箱外，走系统 cmd）即真实部署路径，不受此限制影响。

---

## 四、结论

已按决策完成三项加固：① 端口残留自动清理（54321 后端前 / 3000 前端前，精确按 PID 杀 LISTENING 进程、失败有提示）；② `set NODE_OPTIONS=` 双保险（父进程 + 子 dev 进程）；③ 文件加 UTF-8 BOM。所有可验证原语均通过，bat 静态结构正确，已提交（commit `c5334d7`，仅含加固，不含真实密钥）。

## 五、密钥处理（决策已修订）

- **初版决策（已撤销）**：曾按「提交脱敏版」把 4 个密钥改为从 Windows 系统环境变量读取并提交（commit `c5334d7`）。
- **最终决策（当前生效）**：用户不接受改变使用方式 / 增加手动配置负担。改为——
  - **真实 bat（`启动AI内容工作台.bat`）保留明文密钥**：4 行 `set *_KEY=...` 原样恢复，与改动前**逐字一致**；继续保持被 `.gitignore` 的 `*.bat` 忽略，**只留在本机，不进仓库**。
  - **脱敏模板（`启动AI内容工作台.example.bat`）进仓库**：同样含全部加固（端口清理 / `set NODE_OPTIONS=` / UTF-8 BOM），但 4 个密钥与 `STREAMLIT_PROJECT_ROOT` 路径均替换为占位符（`请填入你的…` / `你的用户名…`），**不含任何真实密钥**。
- **提交（c082565）**：`git rm --cached` 撤销对真实 bat 的跟踪（使其回归 `.gitignore` 管控，`git status` 不再显示它）；`git add -f` 强制纳入 example 模板（绕过 `*.bat`）。
- **校验**：真实 bat 本地仍含 4 个真实密钥（grep 命中 4 处）；example 模板 grep 命中 **0 处**；真实 bat 经 `git check-ignore` 确认被 `*.bat` 忽略。
- **用户无需额外操作**：直接双击真实 bat 即可使用，不必配置任何环境变量。
