/**
 * Inhale dot + wordmark. Not a logo copy of breatheesg.com — a typographic
 * homage. The dot is the only place we use the brand green at full strength
 * in the chrome; everything else stays ink.
 */
export function Wordmark({ size = "md" }: { size?: "sm" | "md" | "lg" }) {
  const px = size === "lg" ? 28 : size === "sm" ? 18 : 22;
  const dotR = px * 0.27;
  const ringR = px * 0.46;
  const text = size === "lg" ? "text-lg" : size === "sm" ? "text-[13px]" : "text-[14.5px]";
  return (
    <span className="inline-flex items-baseline gap-2 select-none">
      <svg width={px} height={px} viewBox={`0 0 ${px} ${px}`} aria-hidden="true"
           className="translate-y-[2px]">
        <circle cx={px / 2} cy={px / 2} r={ringR} fill="none"
                stroke="#39B54A" strokeOpacity={0.22} strokeWidth={1.6} />
        <circle cx={px / 2} cy={px / 2} r={dotR} fill="#39B54A" />
      </svg>
      <span className={`${text} font-display font-semibold tracking-tightish text-brand-ink`}>
        Breathe<span className="text-brand-green-700">.</span>ESG
      </span>
    </span>
  );
}
