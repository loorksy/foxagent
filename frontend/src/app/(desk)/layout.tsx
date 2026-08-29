"use client";

import { Suspense } from "react";
import { AuthGate } from "@/components/AuthGate";
import { DeskLayout } from "@/components/DeskLayout";

export default function DeskRouteLayout({ children }: { children: React.ReactNode }) {
  return (
    <AuthGate>
      <Suspense fallback={null}>
        <DeskLayout>{children}</DeskLayout>
      </Suspense>
    </AuthGate>
  );
}
