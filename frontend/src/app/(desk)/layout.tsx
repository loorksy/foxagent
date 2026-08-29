"use client";

import { Suspense } from "react";
import { DeskLayout } from "@/components/DeskLayout";

export default function DeskRouteLayout({ children }: { children: React.ReactNode }) {
  return (
    <Suspense fallback={null}>
      <DeskLayout>{children}</DeskLayout>
    </Suspense>
  );
}
