"use client";

import * as React from "react";

/**
 * 专属线稿标记库（品牌图标）。
 * 约定：stroke=1.5、圆角、stroke=currentColor、可缩放（默认用 h-/w- 控制尺寸）。
 * 全部用内联 SVG，避免外链资源；主色由父级 text-* 控制（如 text-accent / text-ink）。
 */

type MarkProps = React.SVGProps<SVGSVGElement> & { className?: string };

function Svg({ className, children, ...rest }: MarkProps) {
  return (
    <svg
      viewBox="0 0 48 48"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.5}
      strokeLinecap="round"
      strokeLinejoin="round"
      className={className}
      aria-hidden="true"
      {...rest}
    >
      {children}
    </svg>
  );
}

/** 抖音线：三条上升脉冲波形（拆解→生成→发布 的节奏感）。 */
export function MarkDouyin({ className, ...rest }: MarkProps) {
  return (
    <Svg className={className} {...rest}>
      <path d="M6 32c3 0 3-8 6-8s3 12 6 12 3-16 6-16 3 10 6 10 3-6 6-6" />
      <path d="M6 38c3 0 3-4 6-4s3 6 6 6 3-8 6-8 3 5 6 5 3-3 6-3" opacity={0.5} />
      <circle cx="38" cy="12" r="3" />
    </Svg>
  );
}

/** 热点线：同心圆 + 中心焦点（抓取热点、锁定方向）。 */
export function MarkHotspot({ className, ...rest }: MarkProps) {
  return (
    <Svg className={className} {...rest}>
      <circle cx="24" cy="24" r="16" opacity={0.5} />
      <circle cx="24" cy="24" r="9" opacity={0.8} />
      <circle cx="24" cy="24" r="3.5" />
      <path d="M24 4v6M24 38v6M4 24h6M38 24h6" opacity={0.6} />
    </Svg>
  );
}

/** 生产：三个箭头渐进流动（拆解→生成→封面）。 */
export function MarkProduce({ className, ...rest }: MarkProps) {
  return (
    <Svg className={className} {...rest}>
      <path d="M8 30c4-10 10-10 14 0" />
      <path d="M22 30c4-10 10-10 14 0" />
      <path d="M34 18l6-2-2 6" />
      <path d="M8 38h28" opacity={0.5} />
    </Svg>
  );
}

/** 审核：回字印章，内嵌「扬」字（人审把关）。 */
export function MarkReview({ className, ...rest }: MarkProps) {
  return (
    <Svg className={className} {...rest}>
      <rect x="9" y="9" width="30" height="30" rx="4" />
      <rect x="16" y="16" width="16" height="16" rx="2" opacity={0.6} />
      <path d="M21 24h6M24 21v6" />
    </Svg>
  );
}

/** 数据分析：折线 + 柱。 */
export function MarkAnalytics({ className, ...rest }: MarkProps) {
  return (
    <Svg className={className} {...rest}>
      <path d="M8 36V20M18 36V12M28 36V26M38 36V16" opacity={0.55} />
      <path d="M8 24l9-6 11 4 12-10" />
      <path d="M36 10l4 2-2 4" />
    </Svg>
  );
}

/** 历史任务：三本竖排书脊。 */
export function MarkHistory({ className, ...rest }: MarkProps) {
  return (
    <Svg className={className} {...rest}>
      <path d="M12 10v28M12 10c4 0 6 2 8 2v26c-2 0-4 2-8 2" />
      <path d="M22 10v28M22 10c4 0 6 2 8 2v26c-2 0-4 2-8 2" />
      <path d="M32 10v28M32 10c3 0 5 1 6 2v26c-1 1-3 2-6 2" />
    </Svg>
  );
}

/** 工作台：菱形罗盘（总入口、定方向）。 */
export function MarkWorkbench({ className, ...rest }: MarkProps) {
  return (
    <Svg className={className} {...rest}>
      <rect x="24" y="6" width="24" height="24" rx="3" transform="rotate(45 24 24)" />
      <path d="M24 16v16M16 24h16" opacity={0.5} />
      <circle cx="24" cy="24" r="3" />
    </Svg>
  );
}

/** 空状态：稿纸 + 笔（精细线稿，用于无数据的克制提示）。 */
export function MarkEmpty({ className, ...rest }: MarkProps) {
  return (
    <Svg className={className} {...rest}>
      <path d="M14 8h16l6 6v26a2 2 0 0 1-2 2H14a2 2 0 0 1-2-2V10a2 2 0 0 1 2-2z" />
      <path d="M30 8v6h6" />
      <path d="M18 20h12M18 26h12M18 32h8" opacity={0.5} />
      <path d="M34 30l6 6M36 34l3-3 2 2-3 3z" />
    </Svg>
  );
}
