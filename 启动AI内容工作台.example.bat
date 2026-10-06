@echo off
chcp 65001 >nul
title AI内容运营工作台 - 启动器

REM 统一 Python 标准输出 UTF-8 编码（避免 Windows CMD 默认 GBK 导致 emoji/中文报错）
set PYTHONIOENCODING=utf-8

REM ============================================================
REM 密钥通过环境变量注入（不写入 workbench_config.json，防止落盘泄露）
REM 如需更高安全性，可改为在 Windows「系统环境变量」里设置，删掉下面这几行即可。
REM ============================================================
set STREAMLIT_PROJECT_ROOT=C:\Users\你的用户名\WorkBuddy\你的side-hustle目录
set DEEPSEEK_API_KEY=请填入你的DeepSeek_API_KEY
set SERPAPI_KEY=请填入你的SerpAPI_KEY
set BAIDU_OCR_API_KEY=请填入你的百度OCR_API_KEY
set BAIDU_OCR_SECRET_KEY=请填入你的百度OCR_SECRET_KEY


REM ============================================================
REM 路径与命令解析（优先用明确路径，找不到再 fallback 到 PATH）
REM   - 后端 uvicorn：优先用 managed venv 里的 uvicorn.exe，
REM     其次 PATH 上的 uvicorn，最后回退 python -m uvicorn。
REM     （.python-version 当前为 3.11.9，仅作约定参考；实际服务解释器由上面解析决定）
REM   - 前端 npm：依赖 node_modules 存在；缺失则自动 npm install。
REM ============================================================
set "ROOT=%~dp0"
set "FE_DIR=%ROOT%frontend"
REM 首次使用请把下行改成你自己的虚拟环境路径
set "VENV_SCRIPTS=<改成你自己的 venv Scripts 路径>"

REM ---- 解析后端 uvicorn 命令 ----
set "UVICORN="
if exist "%VENV_SCRIPTS%\uvicorn.exe" ( set "UVICORN=%VENV_SCRIPTS%\uvicorn.exe" )
if not defined UVICORN ( where uvicorn >nul 2>&1 && set "UVICORN=uvicorn" )
if not defined UVICORN ( where python >nul 2>&1 && set "UVICORN=python -m uvicorn" )
if not defined UVICORN (
    echo [错误] 未找到 uvicorn，也无法回退到 python -m uvicorn。
    echo        请先安装：pip install uvicorn fastapi，或在系统环境变量 PATH 中加入 Python/Scripts。
    pause
    exit /b 1
)

echo ========================================
echo    AI 内容运营工作台 - 一键启动
echo ========================================
echo.

REM ============================================================
REM [缓存自检] 检测前端 .next 是否为「损坏的过期缓存」（白屏根因）。
REM   判据（见下方代码）：webpack-runtime.js 已生成、但 vendor-chunks 目录缺失，
REM   即判定缓存损坏 → 删除 .next 让前端重新构建。
REM   若前端仍白屏 / 报 MODULE_NOT_FOUND，也可直接运行同目录「修复前端缓存.bat」强制清理。
REM ============================================================
set "NEED_REBUILD=0"
REM 判定：若构建产物 webpack-runtime.js 已生成、但 vendor-chunks 目录缺失，
REM 说明 .next 是损坏的过期缓存（依赖已变但缓存未重建 → 白屏/MODULE_NOT_FOUND），
REM 需删除让前端重新构建。
REM 注：当前 Next 的 webpack-runtime.js 内并不含字面量 "vendor-chunks"，
REM 故改用「vendor-chunks 目录是否存在」作为可靠判据（有效构建必含该目录）。
if exist "%FE_DIR%\.next\server\webpack-runtime.js" (
    if not exist "%FE_DIR%\.next\server\vendor-chunks" set "NEED_REBUILD=1"
)
if "%NEED_REBUILD%"=="1" (
    echo [自检] 检测到前端构建缓存(.next)损坏，正在删除以便重建...
    rmdir /s /q "%FE_DIR%\.next" >nul 2>&1
) else (
    echo [自检] 前端构建缓存正常，跳过清理。
)

REM ============================================================
REM [端口清理] 自动清理残留端口占用，防止白屏
REM   若上一次没关干净的 CMD / 崩溃残留仍占着 8000，会导致后端起不来；
REM   占着 3000 会导致前端静默跳到 3001 而本启动器仍提示 3000（白屏）。
REM   下面按 PID 精确结束「仅监听在该端口」的进程，避免误杀其他程序。
REM ============================================================
call :killport 8000

REM ============================================================
REM 启动后端
REM ============================================================
echo [1/2] 正在启动后端（%UVICORN%）...
start "🔧 后端服务" cmd /k "cd /d %ROOT% && %UVICORN% backend.main:app --reload --port 8000"

timeout /t 2 /nobreak >nul

REM ============================================================
REM 启动前端（先确认 node_modules 存在，缺失则自动 npm install）
REM ============================================================
if not exist "%FE_DIR%\node_modules" (
    echo [前端] 未检测到 node_modules，正在自动执行 npm install...
    pushd "%FE_DIR%"
    call npm install
    if errorlevel 1 (
        echo [前端] npm install 失败，请手动在 frontend 目录执行 npm install 后重启本启动器。
        popd
        pause
        exit /b 1
    )
    popd
)

REM [端口清理] 自动清理 3000 残留占用，防止前端静默跳 3001 导致白屏
call :killport 3000

echo [2/2] 正在启动前端...
REM 清除任何被注入的 NODE_OPTIONS，防止 safe-delete shim 导致 next dev 在清理 .next 时崩溃
set NODE_OPTIONS=
start "🎨 前端页面" cmd /k "cd /d %FE_DIR% && set NODE_OPTIONS= && npm run dev"

echo.
echo ========================================
echo    启动完成！
echo ========================================
echo.
echo 前端地址：http://localhost:3000
echo 后端地址：http://localhost:8000
echo.
echo 等前端启动完成后，在浏览器里打开前端地址即可使用
echo.
echo 关闭本窗口不会停止前后端服务
echo 要停止服务，直接关闭对应的 CMD 窗口即可
echo.
echo 提示：若前端白屏/报 MODULE_NOT_FOUND，运行同目录「修复前端缓存.bat」清缓存后重启。
echo.
pause

goto :eof

REM ============================================================
REM 端口清理子程序：结束监听在指定端口的进程（按 PID 精确杀，避免误杀）
REM   参数 %1 = 端口号
REM   仅匹配 LISTENING 状态的占用（确保是真正占着端口的监听进程），
REM   用 tokens=5 取 PID，再 taskkill /F /PID /T 结束其进程树。
REM   若 taskkill 因缺少管理员权限等失败，则打印提示让用户手动处理，不静默失败。
REM ============================================================
:killport
set "KP_PORT=%~1"
set "KP_FOUND=0"
set "KP_FAIL=0"
for /f "tokens=5" %%p in ('netstat -ano 2^>nul ^| findstr /c:":%KP_PORT% " ^| findstr "LISTENING"') do (
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
if "%KP_FOUND%"=="0" (
    echo [端口清理] 端口 %KP_PORT% 未被占用，无需清理。
)
if "%KP_FAIL%"=="1" (
    echo [端口清理] 请手动关闭占用 %KP_PORT% 端口的窗口/程序后，再启动本启动器。
)
goto :eof
