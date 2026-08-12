"use client";

import { PageShell, PageHeader } from "@/components/layout/PageShell";
import { DissectPanel } from "@/components/dissect/DissectPanel";

export default function DissectPage() {
  return (
    <PageShell width="xl">
      <PageHeader
        title="即时拆解"
        description="把抖音知识科普类爆款视频，拆出核心素材清单，再自动改写成 3 篇角度完全不同的公众号文章。"
      />
      <DissectPanel embedded />
    </PageShell>
  );
}
