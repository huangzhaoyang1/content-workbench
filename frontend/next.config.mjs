/**
 * Next.js 配置
 *
 * 这个前端要同时满足两种跑法：
 *   1. 本地：`npm run dev` / `npm run build`，一切走根路径（http://localhost:3000/queue）。
 *   2. 线上演示：部署到 GitHub Pages 的「项目页」，
 *      地址是 https://<用户名>.github.io/content-workbench/ 这种带一段路径的，
 *      页面里的 JS/CSS 必须挂在 /content-workbench 前缀下，否则资源 404、页面白屏。
 *
 * 所以拆成两块，各管各的：
 *   - 静态导出：永远打开。本项目没有任何服务端能力（没有 route handler、
 *     没有 middleware、没有 Server Component 里的数据请求，10 个页面全是客户端组件），
 *     导出成纯静态站点就是它的自然形态；这样本地构建和 CI 构建也是同一套行为。
 *   - basePath / assetPrefix：只在 CI 构建时通过环境变量注入。
 *     本地不设这个变量，开发服务器仍是根路径，不会被前缀搞乱。
 */

/** @type {import('next').NextConfig} */
const nextConfig = {
  // 静态导出：构建产物落在 frontend/out/，可以直接丢给任意静态文件服务器
  output: "export",

  // 静态托管没有 Next 自带的图片优化服务，必须关掉；
  // 否则一旦有页面用了 next/image，构建期就会直接报错。
  images: { unoptimized: true },

  // 每个页面导出成 目录/index.html 的形式，让 /queue 和 /queue/ 两种写法都能打开。
  // GitHub Pages 不会替你做「无斜杠 → 有斜杠」的跳转，加上更稳。
  trailingSlash: true,

  // GitHub Pages 项目页需要的前缀，由 CI 注入；本地为空 → 保持根路径。
  // 取值形如 /content-workbench（开头有斜杠、结尾没有）。
  basePath: process.env.NEXT_PUBLIC_BASE_PATH || undefined,
  assetPrefix: process.env.NEXT_PUBLIC_BASE_PATH || undefined,
};

export default nextConfig;
