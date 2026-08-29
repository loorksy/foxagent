export function AgentAvatar({ thinking = false, size = 22 }: { thinking?: boolean; size?: number }) {
  return (
    <span
      className="mt-1.5 inline-flex shrink-0 items-center justify-center rounded-full bg-foreground text-background"
      style={{ width: size, height: size }}
      aria-hidden
    >
      <span className={thinking ? "animate-pulse" : undefined} style={{ fontSize: size * 0.42, fontWeight: 700 }}>
        F
      </span>
    </span>
  );
}
