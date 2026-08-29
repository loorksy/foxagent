"use client";

import { FormEvent, useState } from "react";
import { useRouter } from "next/navigation";
import { api } from "@/lib/api";
import { useT } from "@/i18n";

export default function LoginPage() {
  const router = useRouter();
  const t = useT();
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      await api.login(password);
      router.replace("/agents");
    } catch (err) {
      setError(err instanceof Error ? err.message : t("login.failed"));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex min-h-dvh items-center justify-center bg-background px-4">
      <form onSubmit={onSubmit} className="w-full max-w-sm space-y-4 rounded-2xl border border-border bg-card p-6">
        <h1 className="font-serif text-2xl font-medium">{t("login.title")}</h1>
        <p className="text-sm text-muted-foreground">{t("login.intro")}</p>
        <label className="block space-y-1.5">
          <span className="text-[11px] font-medium text-muted-foreground">{t("login.password")}</span>
          <input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            className="w-full rounded-lg border border-border bg-input px-3 py-2 text-sm outline-none focus-visible:ring-2 focus-visible:ring-ring"
            autoFocus
          />
        </label>
        {error ? <p className="text-xs text-sell">{error}</p> : null}
        <button
          type="submit"
          disabled={busy || !password.trim()}
          className="w-full rounded-xl bg-foreground py-2.5 text-sm font-semibold text-background disabled:opacity-40"
        >
          {t("login.submit")}
        </button>
      </form>
    </div>
  );
}
