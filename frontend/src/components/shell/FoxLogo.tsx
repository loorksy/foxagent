import { cn } from "@/lib/utils";

export function FoxLogo({
  size = 32,
  showName = false,
  nameClassName,
}: {
  size?: number;
  showName?: boolean;
  nameClassName?: string;
}) {
  return (
    <span className="inline-flex max-w-full items-center gap-2 overflow-visible">
      <span
        className="relative inline-flex shrink-0 items-center justify-center rounded-lg bg-foreground text-background"
        style={{ width: size, height: size }}
      >
        <svg viewBox="0 0 32 32" width={size * 0.72} height={size * 0.72} aria-hidden>
          <path
            fill="currentColor"
            d="M6 10 16 5l10 5-3.2 6.4L16 27 9.2 16.4 6 10Zm10 2.2L12.6 18h6.8L16 12.2Z"
          />
        </svg>
      </span>
      {showName ? (
        <span className={cn("font-semibold tracking-tight text-foreground", nameClassName)}>FoxAgent</span>
      ) : null}
    </span>
  );
}
