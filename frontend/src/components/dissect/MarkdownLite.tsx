"use client";

import * as React from "react";
import { cn } from "@/lib/utils";

/**
 * 极简 Markdown 渲染器，专门给公众号改写预览用。
 * 只认这套「高数据格式规范」会用到的语法，不引入完整 md 库：
 *   ## emoji 小标题   → h2
 *   ### 小标题        → h3（更小一号）
 *   > 引用金句        → blockquote
 *   - / * 列表项       → ul
 *   1. 列表项          → ol
 *   **加粗**           → strong
 *   `行内代码`         → code（bg-muted 底）
 *   ``` 代码块 ```     → pre > code（可横向滚动）
 *   --- / ***          → hr 分割线
 *   <font color="red">**红色加粗**</font> → 红色加粗（微信兼容写法，直接在预览里上色）
 *
 * 排版 CSS 方案提取自开源项目 mbeditor（https://github.com/aaaaanson/mbeditor）：
 *   - WeChat 阅读基线：正文 16px / 行高 ≈1.8 / 字间距 0.4px / 两端对齐（justify）
 *   - 标题六级字号梯度（h1 26 → h6 15），加粗、左对齐
 *   - 5 套主题调子（极简商务 / 文艺手札 / 活力撞色 / 杂志专栏 / 科技霓虹），
 *     各自有主色（accent）、正文色、引用底色、代码底色、字体族
 *   - 自动选版式：theme="auto" 时按正文关键词气质挑一套主题（mbeditor 同为「内容气质」驱动）
 *
 * 不用 dangerouslySetInnerHTML，自己把 <font>/<**> 解析成 React 节点，避免 XSS。
 */

type ThemeKey = "biz" | "literary" | "vibrant" | "magazine" | "tech";
export type ThemeProp = ThemeKey | "auto";

interface Theme {
  label: string;
  /** 容器背景；undefined = 透明（继承外层卡片，保持向后兼容默认观感） */
  pageBg?: string;
  text: string;
  heading: string;
  accent: string;
  accentSoft: string;
  blockquoteBg: string;
  codeBg: string;
  codeColor: string;
  fontFamily: string;
  /** h2 的装饰性附加样式（左边栏 / 下划线等） */
  h2: React.CSSProperties;
  h3: React.CSSProperties;
}

const SANS =
  '-apple-system, BlinkMacSystemFont, "PingFang SC", "Microsoft YaHei", "Hiragino Sans GB", system-ui, sans-serif';
const SERIF = 'Georgia, "Times New Roman", "Songti SC", "STSong", "Noto Serif SC", serif';
const MONO = 'ui-monospace, SFMono-Regular, Menlo, Consolas, "Liberation Mono", monospace';

const THEMES: Record<ThemeKey, Theme> = {
  // 极简商务：瑞士风，单一蓝强调色，大量留白，最接近原默认观感
  biz: {
    label: "极简商务",
    text: "#37352f",
    heading: "#1a1a1a",
    accent: "#2563eb",
    accentSoft: "#dbeafe",
    blockquoteBg: "#f5f8ff",
    codeBg: "#f3f4f6",
    codeColor: "#1f2937",
    fontFamily: SANS,
    h2: { borderLeft: "4px solid #2563eb", paddingLeft: "10px" },
    h3: {},
  },
  // 文艺手札：纸张米色底，赭石强调色，衬线字体，温润
  literary: {
    label: "文艺手札",
    pageBg: "#faf8f3",
    text: "#4a4540",
    heading: "#2b2620",
    accent: "#9c6b4f",
    accentSoft: "#efe6da",
    blockquoteBg: "#f3ece2",
    codeBg: "#efe9e0",
    codeColor: "#5b4636",
    fontFamily: SERIF,
    h2: { borderBottom: "2px solid #9c6b4f", paddingBottom: "6px", display: "inline-block" },
    h3: {},
  },
  // 活力撞色：暖珊瑚强调色，圆角卡片感，明快
  vibrant: {
    label: "活力撞色",
    pageBg: "#ffffff",
    text: "#44403c",
    heading: "#1f2937",
    accent: "#f97316",
    accentSoft: "#fff1e6",
    blockquoteBg: "#fff7ed",
    codeBg: "#fff1e6",
    codeColor: "#9a3412",
    fontFamily: SANS,
    h2: { borderBottom: "3px solid #f97316", paddingBottom: "6px" },
    h3: {},
  },
  // 杂志专栏：黑红编辑风，红色章节标签感，衬线正文
  magazine: {
    label: "杂志专栏",
    pageBg: "#ffffff",
    text: "#333333",
    heading: "#1a1a1a",
    accent: "#e74c3c",
    accentSoft: "#fdecea",
    blockquoteBg: "#f5f5f0",
    codeBg: "#f3f3f0",
    codeColor: "#333333",
    fontFamily: SERIF,
    h2: { color: "#e74c3c", borderBottom: "1px solid #eee", paddingBottom: "8px", letterSpacing: "2px" },
    h3: { color: "#1a1a1a" },
  },
  // 科技霓虹：深色底 + 霓虹青，等宽代码，发光标题
  tech: {
    label: "科技霓虹",
    pageBg: "#0b0f1a",
    text: "#cbd5e1",
    heading: "#e2e8f0",
    accent: "#22d3ee",
    accentSoft: "#0e2a33",
    blockquoteBg: "#111a24",
    codeBg: "#0d1420",
    codeColor: "#22d3ee",
    fontFamily: SANS,
    h2: { borderLeft: "4px solid #22d3ee", paddingLeft: "10px", textShadow: "0 0 8px rgba(34,211,238,0.35)" },
    h3: { color: "#22d3ee" },
  },
};

/** 自动选版式：按正文关键词气质挑主题（mbeditor 同为「内容气质」驱动选择）。 */
const THEME_KEYWORDS: Record<ThemeKey, string[]> = {
  tech: ["科技", "ai", "人工智能", "模型", "代码", "工程师", "发布", "芯片", "互联网", "算法", "智能", "数字", "编程", "开源", "算力", "agent"],
  magazine: ["深度", "专访", "人物", "报道", "故事", "采访", "品牌", "纪实", "调查", "专栏", "对话", "认知", "观点", "反思", "思考", "底层逻辑", "本质"],
  vibrant: ["生活", "清单", "好物", "种草", "打卡", "日常", "能量", "攻略", "测评", "推荐", "分享", "治愈", "周末", "美食"],
  literary: ["散文", "读书", "笔记", "随笔", "感悟", "心情", "日记", "文学", "手札", "随想", "诗"],
  biz: ["报告", "企业", "通告", "行业", "数据", "分析", "周报", "总结", "商业", "战略", "市场", "财报", "趋势"],
};

function detectTheme(content: string): ThemeKey {
  const lower = content.toLowerCase();
  let best: ThemeKey = "biz";
  let bestScore = 0;
  (Object.keys(THEME_KEYWORDS) as ThemeKey[]).forEach((k) => {
    const score = THEME_KEYWORDS[k].reduce(
      (s, kw) => s + (lower.includes(kw.toLowerCase()) ? 1 : 0),
      0,
    );
    if (score > bestScore) {
      bestScore = score;
      best = k;
    }
  });
  return best;
}

function renderBold(text: string, keyPrefix: string): React.ReactNode[] {
  const parts = text.split(/(\*\*[^*]+\*\*)/g);
  return parts.map((p, idx) => {
    if (p.length > 4 && p.startsWith("**") && p.endsWith("**")) {
      return <strong key={`${keyPrefix}-${idx}`}>{p.slice(2, -2)}</strong>;
    }
    return <React.Fragment key={`${keyPrefix}-${idx}`}>{p}</React.Fragment>;
  });
}

/** 把一段文字按行内代码 `code` 切块，非代码段再走加粗解析（代码内的 ** 不再当加粗）。 */
function renderSegments(text: string, keyPrefix: string, codeStyle: React.CSSProperties): React.ReactNode[] {
  const parts = text.split(/(`[^`]+`)/g);
  return parts.map((p, idx) => {
    if (p.length >= 2 && p.startsWith("`") && p.endsWith("`")) {
      return (
        <code
          key={`${keyPrefix}-c${idx}`}
          className="rounded px-1 py-0.5 text-[0.85em]"
          style={codeStyle}
        >
          {p.slice(1, -1)}
        </code>
      );
    }
    return (
      <React.Fragment key={`${keyPrefix}-t${idx}`}>
        {renderBold(p, `${keyPrefix}-t${idx}`)}
      </React.Fragment>
    );
  });
}

/** 把一段文字里的 <font color="red">…</font> 还原成红色加粗 span，并支持行内代码与加粗。 */
function renderInline(text: string, keyPrefix: string, codeStyle: React.CSSProperties): React.ReactNode[] {
  const nodes: React.ReactNode[] = [];
  const fontRe = /<font color="red">([\s\S]*?)<\/font>/g;
  let last = 0;
  let m: RegExpExecArray | null;
  let i = 0;
  while ((m = fontRe.exec(text))) {
    if (m.index > last) {
      nodes.push(...renderSegments(text.slice(last, m.index), `${keyPrefix}-b${i}`, codeStyle));
    }
    nodes.push(
      <span
        key={`${keyPrefix}-f${i}`}
        className="font-semibold text-red-400"
      >
        {renderSegments(m[1], `${keyPrefix}-f${i}`, codeStyle)}
      </span>
    );
    last = m.index + m[0].length;
    i += 1;
  }
  if (last < text.length) {
    nodes.push(...renderSegments(text.slice(last), `${keyPrefix}-e`, codeStyle));
  }
  return nodes;
}

function isSpecial(line: string): boolean {
  return (
    line.startsWith("## ") ||
    line.startsWith("### ") ||
    line.startsWith("```") ||
    line.startsWith("> ") ||
    /^[-*] /.test(line) ||
    /^\d+\.\s/.test(line) ||
    /^([-*_]){3,}$/.test(line)
  );
}

export function MarkdownLite({
  content,
  className,
  theme = "auto",
}: {
  content: string;
  className?: string;
  theme?: ThemeProp;
}) {
  const active: ThemeKey = theme === "auto" ? detectTheme(content) : theme;
  const T = THEMES[active];

  const h2Style: React.CSSProperties = {
    fontSize: "20px",
    fontWeight: 700,
    lineHeight: 1.4,
    color: T.heading,
    margin: "22px 0 12px",
    textAlign: "justify",
    ...T.h2,
  };
  const h3Style: React.CSSProperties = {
    fontSize: "17px",
    fontWeight: 700,
    lineHeight: 1.5,
    color: T.heading,
    margin: "18px 0 10px",
    textAlign: "justify",
    ...T.h3,
  };
  const pStyle: React.CSSProperties = {
    fontSize: "16px",
    lineHeight: 1.8,
    color: T.text,
    margin: "12px 0",
    textAlign: "justify",
    letterSpacing: "0.4px",
  };
  const quoteStyle: React.CSSProperties = {
    borderLeft: `4px solid ${T.accent}`,
    background: T.blockquoteBg,
    padding: "12px 16px",
    margin: "14px 0",
    color: T.text,
    borderRadius: "0 8px 8px 0",
    fontSize: "15px",
    lineHeight: 1.8,
  };
  const ulStyle: React.CSSProperties = {
    color: T.accent,
    paddingLeft: "22px",
    margin: "12px 0",
    fontSize: "16px",
    lineHeight: 1.8,
    listStyleType: "disc",
  };
  const olStyle: React.CSSProperties = {
    color: T.accent,
    paddingLeft: "22px",
    margin: "12px 0",
    fontSize: "16px",
    lineHeight: 1.8,
    listStyleType: "decimal",
  };
  const liStyle: React.CSSProperties = { color: T.text };
  const hrStyle: React.CSSProperties = {
    border: "none",
    borderTop: `1px solid ${T.accent}`,
    opacity: 0.45,
    margin: "20px 0",
  };
  const preStyle: React.CSSProperties = {
    background: T.codeBg,
    color: T.codeColor,
    padding: "14px 16px",
    borderRadius: "10px",
    fontSize: "13px",
    lineHeight: 1.7,
    overflowX: "auto",
    margin: "14px 0",
  };
  const codeStyle: React.CSSProperties = { background: T.codeBg, color: T.codeColor };

  const lines = content.split("\n");
  const blocks: React.ReactNode[] = [];
  let i = 0;
  let key = 0;

  while (i < lines.length) {
    const trimmed = lines[i].trim();
    if (trimmed === "") {
      i += 1;
      continue;
    }

    // 代码块 ```...```（围栏内的内容保持原样，不解析加粗/字体）
    if (trimmed.startsWith("```")) {
      const codeLines: string[] = [];
      i += 1; // 跳过起始围栏
      while (i < lines.length && !lines[i].trim().startsWith("```")) {
        codeLines.push(lines[i]);
        i += 1;
      }
      i += 1; // 跳过结束围栏（若存在）
      blocks.push(
        <pre key={key} style={preStyle}>
          <code>{codeLines.join("\n")}</code>
        </pre>
      );
      key++;
      continue;
    }

    // 三级标题 ###（比 ## 更小一号）
    if (trimmed.startsWith("### ")) {
      blocks.push(
        <h3 key={key} style={h3Style}>
          {renderInline(trimmed.slice(4), `h3-${key}`, codeStyle)}
        </h3>
      );
      key++;
      i += 1;
      continue;
    }

    // 分割线 --- / *** / ___
    if (/^([-*_]){3,}$/.test(trimmed)) {
      blocks.push(<hr key={key} style={hrStyle} />);
      key++;
      i += 1;
      continue;
    }

    if (trimmed.startsWith("## ")) {
      blocks.push(
        <h2 key={key} style={h2Style}>
          {renderInline(trimmed.slice(3), `h${key}`, codeStyle)}
        </h2>
      );
      key++;
      i += 1;
      continue;
    }

    if (trimmed.startsWith("> ")) {
      const quote: string[] = [];
      while (i < lines.length && lines[i].trim().startsWith("> ")) {
        quote.push(lines[i].trim().slice(2).trim());
        i += 1;
      }
      blocks.push(
        <blockquote key={key} style={quoteStyle}>
          {renderInline(quote.join(" "), `q${key}`, codeStyle)}
        </blockquote>
      );
      key++;
      continue;
    }

    if (/^[-*] /.test(trimmed)) {
      const items: string[] = [];
      while (i < lines.length && /^[-*] /.test(lines[i].trim())) {
        items.push(lines[i].trim().slice(2).trim());
        i += 1;
      }
      blocks.push(
        <ul key={key} className="list-disc" style={ulStyle}>
          {items.map((it, idx) => (
            <li key={idx} style={liStyle}>
              {renderInline(it, `ul${key}-${idx}`, codeStyle)}
            </li>
          ))}
        </ul>
      );
      key++;
      continue;
    }

    if (/^\d+\.\s/.test(trimmed)) {
      const items: string[] = [];
      while (i < lines.length && /^\d+\.\s/.test(lines[i].trim())) {
        items.push(lines[i].trim().replace(/^\d+\.\s/, ""));
        i += 1;
      }
      blocks.push(
        <ol key={key} className="list-decimal" style={olStyle}>
          {items.map((it, idx) => (
            <li key={idx} style={liStyle}>
              {renderInline(it, `ol${key}-${idx}`, codeStyle)}
            </li>
          ))}
        </ol>
      );
      key++;
      continue;
    }

    // 普通段落：把连续的非特殊行合并
    const para: string[] = [];
    while (i < lines.length && lines[i].trim() !== "" && !isSpecial(lines[i].trim())) {
      para.push(lines[i].trim());
      i += 1;
    }
    blocks.push(
      <p key={key} style={pStyle}>
        {renderInline(para.join(" "), `p${key}`, codeStyle)}
      </p>
    );
    key++;
  }

  return (
    <div
      className={cn(className)}
      style={{
        fontFamily: T.fontFamily,
        fontSize: "16px",
        lineHeight: 1.8,
        letterSpacing: "0.4px",
        color: T.text,
        textAlign: "justify",
        ...(T.pageBg
          ? {
              background: T.pageBg,
              padding: "20px 22px",
              borderRadius: "12px",
              maxWidth: "680px",
              margin: "0 auto",
            }
          : { maxWidth: "100%" }),
      }}
    >
      {blocks}
    </div>
  );
}
