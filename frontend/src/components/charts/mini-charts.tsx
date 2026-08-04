"use client";

import * as React from "react";
import { cn } from "@/lib/utils";

// 极简 SVG 图表：不引第三方图表库，避免额外依赖与打包体积。
// 只覆盖工作台需要的两种：单折线（趋势）+ 分组柱状（对比）。

export interface ChartPoint {
  label: string;
  values: number[];
}

interface ChartBaseProps {
  data: ChartPoint[];
  /** 每个系列的名字，用于图例与 tooltip。 */
  series: string[];
  /** 每个系列的颜色，长度需与 series 对齐。 */
  colors?: string[];
  height?: number;
  className?: string;
  /** 数值格式化，默认千分位。 */
  format?: (v: number) => string;
}

const DEFAULT_COLORS = ["#38bdf8", "#a78bfa", "#34d399", "#fbbf24"];

function fmtNum(v: number): string {
  if (!Number.isFinite(v)) return "-";
  if (Math.abs(v) >= 10000) return `${(v / 10000).toFixed(1)}w`;
  return v.toLocaleString("zh-CN");
}

/** 计算「好看的」Y 轴上界与刻度。 */
function niceScale(max: number, ticks = 4): { top: number; steps: number[] } {
  if (max <= 0) return { top: 10, steps: [0, 2.5, 5, 7.5, 10] };
  const raw = max / ticks;
  const mag = Math.pow(10, Math.floor(Math.log10(raw)));
  const norm = raw / mag;
  const step = (norm <= 1 ? 1 : norm <= 2 ? 2 : norm <= 5 ? 5 : 10) * mag;
  const top = step * ticks;
  return {
    top,
    steps: Array.from({ length: ticks + 1 }, (_, i) => step * i),
  };
}

function Legend({ series, colors }: { series: string[]; colors: string[] }) {
  return (
    <div className="mb-2 flex flex-wrap items-center gap-x-4 gap-y-1 text-[11px] text-muted-foreground">
      {series.map((s, i) => (
        <span key={s} className="inline-flex items-center gap-1.5">
          <span
            className="inline-block h-2 w-2 rounded-full"
            style={{ background: colors[i % colors.length] }}
          />
          {s}
        </span>
      ))}
    </div>
  );
}

/** 折线图（支持多条线，工作台目前只用单条阅读量趋势）。 */
export function LineChart({
  data,
  series,
  colors = DEFAULT_COLORS,
  height = 220,
  className,
  format = fmtNum,
}: ChartBaseProps) {
  const [hover, setHover] = React.useState<number | null>(null);

  const W = 720;
  const H = height;
  const padL = 48;
  const padR = 12;
  const padT = 12;
  const padB = 28;
  const innerW = W - padL - padR;
  const innerH = H - padT - padB;

  const maxVal = Math.max(
    1,
    ...data.flatMap((d) => d.values.filter((v) => Number.isFinite(v)))
  );
  const { top, steps } = niceScale(maxVal);

  const x = (i: number) =>
    data.length <= 1 ? padL + innerW / 2 : padL + (innerW * i) / (data.length - 1);
  const y = (v: number) => padT + innerH - (innerH * v) / top;

  // X 轴标签抽稀，避免拥挤
  const labelStride = Math.max(1, Math.ceil(data.length / 8));

  return (
    <div className={className}>
      <Legend series={series} colors={colors} />
      <div className="relative">
        <svg
          viewBox={`0 0 ${W} ${H}`}
          className="w-full"
          style={{ height }}
          onMouseLeave={() => setHover(null)}
        >
          {/* 网格与 Y 轴刻度 */}
          {steps.map((s) => (
            <g key={s}>
              <line
                x1={padL}
                x2={W - padR}
                y1={y(s)}
                y2={y(s)}
                stroke="currentColor"
                className="text-border"
                strokeWidth={1}
                strokeDasharray={s === 0 ? "0" : "3 4"}
              />
              <text
                x={padL - 8}
                y={y(s) + 3.5}
                textAnchor="end"
                className="fill-muted-foreground text-[10px]"
              >
                {format(s)}
              </text>
            </g>
          ))}

          {/* 折线 + 面积 */}
          {series.map((_, si) => {
            const color = colors[si % colors.length];
            const pts = data.map((d, i) => `${x(i)},${y(d.values[si] ?? 0)}`);
            const area = `M ${padL},${y(0)} L ${pts.join(" L ")} L ${x(
              data.length - 1
            )},${y(0)} Z`;
            return (
              <g key={si}>
                {data.length > 1 && (
                  <path d={area} fill={color} opacity={0.08} />
                )}
                <polyline
                  points={pts.join(" ")}
                  fill="none"
                  stroke={color}
                  strokeWidth={2}
                  strokeLinejoin="round"
                  strokeLinecap="round"
                />
                {data.map((d, i) => (
                  <circle
                    key={i}
                    cx={x(i)}
                    cy={y(d.values[si] ?? 0)}
                    r={hover === i ? 4 : data.length > 30 ? 0 : 2.5}
                    fill={color}
                  />
                ))}
              </g>
            );
          })}

          {/* X 轴标签 */}
          {data.map((d, i) =>
            i % labelStride === 0 || i === data.length - 1 ? (
              <text
                key={i}
                x={x(i)}
                y={H - 8}
                textAnchor="middle"
                className="fill-muted-foreground text-[10px]"
              >
                {d.label.slice(5)}
              </text>
            ) : null
          )}

          {/* hover 命中区 */}
          {data.map((d, i) => (
            <rect
              key={`hit-${i}`}
              x={x(i) - innerW / Math.max(1, data.length) / 2}
              y={padT}
              width={innerW / Math.max(1, data.length)}
              height={innerH}
              fill="transparent"
              onMouseEnter={() => setHover(i)}
            />
          ))}

          {hover !== null && (
            <line
              x1={x(hover)}
              x2={x(hover)}
              y1={padT}
              y2={padT + innerH}
              stroke="currentColor"
              className="text-muted-foreground"
              strokeWidth={1}
              strokeDasharray="3 3"
            />
          )}
        </svg>

        {hover !== null && data[hover] && (
          <div
            className="pointer-events-none absolute top-2 rounded-lg border border-border bg-card px-2.5 py-1.5 text-[11px] shadow-lg"
            style={{
              left: `calc(${(x(hover) / W) * 100}% + 8px)`,
              transform:
                x(hover) / W > 0.72 ? "translateX(calc(-100% - 16px))" : undefined,
            }}
          >
            <div className="font-medium">{data[hover].label}</div>
            {series.map((s, si) => (
              <div key={s} className="mt-0.5 flex items-center gap-1.5">
                <span
                  className="inline-block h-1.5 w-1.5 rounded-full"
                  style={{ background: colors[si % colors.length] }}
                />
                <span className="text-muted-foreground">{s}</span>
                <span className="ml-auto font-medium tabular-nums">
                  {format(data[hover].values[si] ?? 0)}
                </span>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

/** 分组柱状图（在看 / 分享对比）。 */
export function BarChart({
  data,
  series,
  colors = ["#a78bfa", "#34d399"],
  height = 220,
  className,
  format = fmtNum,
}: ChartBaseProps) {
  const [hover, setHover] = React.useState<number | null>(null);

  const W = 720;
  const H = height;
  const padL = 48;
  const padR = 12;
  const padT = 12;
  const padB = 28;
  const innerW = W - padL - padR;
  const innerH = H - padT - padB;

  const maxVal = Math.max(
    1,
    ...data.flatMap((d) => d.values.filter((v) => Number.isFinite(v)))
  );
  const { top, steps } = niceScale(maxVal);

  const groupW = innerW / Math.max(1, data.length);
  const barGap = 3;
  const barW = Math.max(
    2,
    Math.min(18, (groupW * 0.62 - barGap * (series.length - 1)) / series.length)
  );
  const y = (v: number) => padT + innerH - (innerH * v) / top;
  const labelStride = Math.max(1, Math.ceil(data.length / 8));

  return (
    <div className={className}>
      <Legend series={series} colors={colors} />
      <div className="relative">
        <svg
          viewBox={`0 0 ${W} ${H}`}
          className="w-full"
          style={{ height }}
          onMouseLeave={() => setHover(null)}
        >
          {steps.map((s) => (
            <g key={s}>
              <line
                x1={padL}
                x2={W - padR}
                y1={y(s)}
                y2={y(s)}
                stroke="currentColor"
                className="text-border"
                strokeWidth={1}
                strokeDasharray={s === 0 ? "0" : "3 4"}
              />
              <text
                x={padL - 8}
                y={y(s) + 3.5}
                textAnchor="end"
                className="fill-muted-foreground text-[10px]"
              >
                {format(s)}
              </text>
            </g>
          ))}

          {data.map((d, i) => {
            const cx = padL + groupW * i + groupW / 2;
            const totalW = barW * series.length + barGap * (series.length - 1);
            const startX = cx - totalW / 2;
            return (
              <g key={i}>
                {hover === i && (
                  <rect
                    x={padL + groupW * i}
                    y={padT}
                    width={groupW}
                    height={innerH}
                    className="fill-muted"
                    opacity={0.35}
                  />
                )}
                {series.map((_, si) => {
                  const v = d.values[si] ?? 0;
                  const h = Math.max(0, y(0) - y(v));
                  return (
                    <rect
                      key={si}
                      x={startX + si * (barW + barGap)}
                      y={y(v)}
                      width={barW}
                      height={h}
                      rx={2}
                      fill={colors[si % colors.length]}
                    />
                  );
                })}
                <rect
                  x={padL + groupW * i}
                  y={padT}
                  width={groupW}
                  height={innerH}
                  fill="transparent"
                  onMouseEnter={() => setHover(i)}
                />
              </g>
            );
          })}

          {data.map((d, i) =>
            i % labelStride === 0 || i === data.length - 1 ? (
              <text
                key={`lb-${i}`}
                x={padL + groupW * i + groupW / 2}
                y={H - 8}
                textAnchor="middle"
                className="fill-muted-foreground text-[10px]"
              >
                {d.label.slice(5)}
              </text>
            ) : null
          )}
        </svg>

        {hover !== null && data[hover] && (
          <div
            className={cn(
              "pointer-events-none absolute top-2 rounded-lg border border-border bg-card px-2.5 py-1.5 text-[11px] shadow-lg"
            )}
            style={{
              left: `calc(${((padL + groupW * hover + groupW / 2) / W) * 100}% + 8px)`,
              transform:
                (padL + groupW * hover) / W > 0.72
                  ? "translateX(calc(-100% - 16px))"
                  : undefined,
            }}
          >
            <div className="font-medium">{data[hover].label}</div>
            {series.map((s, si) => (
              <div key={s} className="mt-0.5 flex items-center gap-1.5">
                <span
                  className="inline-block h-1.5 w-1.5 rounded-full"
                  style={{ background: colors[si % colors.length] }}
                />
                <span className="text-muted-foreground">{s}</span>
                <span className="ml-auto font-medium tabular-nums">
                  {format(data[hover].values[si] ?? 0)}
                </span>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
