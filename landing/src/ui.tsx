import { useEffect, useRef, useState, type ReactNode } from "react";
import {
  animate,
  motion,
  useInView,
  useScroll,
  useTransform,
  type MotionValue,
} from "motion/react";

export const asset = (file: string) => `${import.meta.env.BASE_URL}assets/${file}`;

export const EASE = [0.22, 1, 0.36, 1] as const;

/* ---------- Icons (Phosphor paths, 256 grid) ---------- */

const P = {
  arrowRightLight:
    "M220.24,132.24l-72,72a6,6,0,0,1-8.48-8.48L201.51,134H40a6,6,0,0,1,0-12H201.51L139.76,60.24a6,6,0,0,1,8.48-8.48l72,72A6,6,0,0,1,220.24,132.24Z",
  arrowRight:
    "M221.66,133.66l-72,72a8,8,0,0,1-11.32-11.32L196.69,136H40a8,8,0,0,1,0-16H196.69L138.34,61.66a8,8,0,0,1,11.32-11.32l72,72A8,8,0,0,1,221.66,133.66Z",
  trendUp:
    "M238,56v64a6,6,0,0,1-12,0V70.48l-85.76,85.76a6,6,0,0,1-8.48,0L96,120.49,28.24,188.24a6,6,0,0,1-8.48-8.48l72-72a6,6,0,0,1,8.48,0L136,143.51,217.52,62H168a6,6,0,0,1,0-12h64A6,6,0,0,1,238,56Z",
  rocket:
    "M150,224a6,6,0,0,1-6,6H112a6,6,0,0,1,0-12h32A6,6,0,0,1,150,224ZM128,110a10,10,0,1,0-10-10A10,10,0,0,0,128,110Zm93.67,45.4L209.31,211A14,14,0,0,1,187,219l-27.79-21H96.82L69,219a14,14,0,0,1-22.34-8L34.33,155.4a14.06,14.06,0,0,1,2.910-12l29-34.76a121.28,121.28,0,0,1,8.48-36.710c12.72-31.88,35.52-51.88,44.73-59a14,14,0,0,1,17.16,0c9.21,7.12,32,27.12,44.73,59a121.280,121.280,0,0,1,8.48,36.71l29,34.76A14.060,14.060,0,0,1,221.67,155.4ZM98.26,186h59.48c21.93-38.46,26.12-75.33,12.43-109.62-11.95-30-34.35-48.87-40.93-54a2,2,0,0,0-2.48,0c-6.58,5.09-29,24-40.93,54C72.14,110.67,76.33,147.54,98.26,186ZM87,190.4c-12-21.49-18.9-42.6-20.62-63.19L46.46,151.08a2,2,0,0,0-.42,1.71l12.37,55.64a2,2,0,0,0,3.2,1.130l.13-.11Zm122.57-39.32-19.89-23.87c-1.72,20.59-8.6,41.7-20.62,63.19l25.230,19,.13.11a2,2,0,0,0,3.2-1.130L210,152.79A2,2,0,0,0,209.54,151.08Z",
  quotes:
    "M116,72v88a48.05,48.05,0,0,1-48,48,8,8,0,0,1,0-16,32,32,0,0,0,32-32v-8H40a16,16,0,0,1-16-16V72A16,16,0,0,1,40,56h60A16,16,0,0,1,116,72ZM216,56H156a16,16,0,0,0-16,16v64a16,16,0,0,0,16,16h60v8a32,32,0,0,1-32,32,8,8,0,0,0,0,16,48.05,48.05,0,0,0,48-48V72A16,16,0,0,0,216,56Z",
  timer:
    "M128,40a96,96,0,1,0,96,96A96.11,96.11,0,0,0,128,40Zm0,176a80,80,0,1,1,80-80A80.09,80.09,0,0,1,128,216ZM173.66,90.34a8,8,0,0,1,0,11.32l-40,40a8,8,0,0,1-11.32-11.32l40-40A8,8,0,0,1,173.66,90.34ZM96,16a8,8,0,0,1,8-8h48a8,8,0,0,1,0,16H104A8,8,0,0,1,96,16Z",
  xFill:
    "M215,219.85a8,8,0,0,1-7,4.15H160a8,8,0,0,1-6.75-3.71l-40.49-63.63L53.92,221.38a8,8,0,0,1-11.84-10.76l61.77-68L41.25,44.3A8,8,0,0,1,48,32H96a8,8,0,0,1,6.75,3.71l40.49,63.63,58.84-64.72a8,8,0,0,1,11.84,10.76l-61.77,67.95,62.6,98.38A8,8,0,0,1,215,219.85Z",
  github:
    "M216,104v8a56.06,56.06,0,0,1-48.44,55.47A39.8,39.8,0,0,1,176,192v40a8,8,0,0,1-8,8H104a8,8,0,0,1-8-8V216H72a40,40,0,0,1-40-40A24,24,0,0,0,8,152a8,8,0,0,1,0-16,40,40,0,0,1,40,40,24,24,0,0,0,24,24H96v-8a39.8,39.8,0,0,1,8.44-24.53A56.06,56.06,0,0,1,56,112v-8a58.14,58.14,0,0,1,7.69-28.32A59.78,59.78,0,0,1,69.07,28,8,8,0,0,1,76,24a59.75,59.75,0,0,1,48,24h24a59.75,59.75,0,0,1,48-24,8,8,0,0,1,6.93,4,59.74,59.74,0,0,1,5.37,47.68A58,58,0,0,1,216,104Z",
  check:
    "M229.66,77.66l-128,128a8,8,0,0,1-11.32,0l-56-56a8,8,0,0,1,11.32-11.32L96,188.69,218.34,66.34a8,8,0,0,1,11.32,11.32Z",
  plusBold:
    "M228,128a12,12,0,0,1-12,12H140v76a12,12,0,0,1-24,0V140H40a12,12,0,0,1,0-24h76V40a12,12,0,0,1,24,0v76h76A12,12,0,0,1,228,128Z",
  xLogo:
    "M214.75,211.71l-62.6-98.38,61.77-67.950a8,8,0,0,0-11.84-10.76L143.24,99.34,102.75,35.71A8,8,0,0,0,96,32H48a8,8,0,0,0-6.75,12.3l62.6,98.37-61.77,68a8,8,0,1,0,11.84,10.76l58.84-64.72,40.49,63.63A8,8,0,0,0,160,224h48a8,8,0,0,0,6.75-12.29ZM164.39,208,62.57,48h29L193.43,208Z",
  linkedin:
    "M216,24H40A16,16,0,0,0,24,40V216a16,16,0,0,0,16,16H216a16,16,0,0,0,16-16V40A16,16,0,0,0,216,24Zm0,192H40V40H216V216ZM96,112v64a8,8,0,0,1-16,0V112a8,8,0,0,1,16,0Zm88,28v36a8,8,0,0,1-16,0V140a20,20,0,0,0-40,0v36a8,8,0,0,1-16,0V112a8,8,0,0,1,15.79-1.78A36,36,0,0,1,184,140ZM100,84A12,12,0,1,1,88,72,12,12,0,0,1,100,84Z",
  youtube:
    "M164.44,121.34l-48-32A8,8,0,0,0,104,96v64a8,8,0,0,0,12.44,6.66l48-32a8,8,0,0,0,0-13.32ZM120,145.05V111l25.58,17ZM234.33,69.52a24,24,0,0,0-14.49-16.4C185.56,39.88,131,40,128,40s-57.56-.12-91.84,13.12a24,24,0,0,0-14.49,16.4C19.08,79.5,16,97.74,16,128s3.08,48.5,5.67,58.48a24,24,0,0,0,14.49,16.41C69,215.56,120.4,216,127.34,216h1.32c6.94,0,58.37-.44,91.18-13.11a24,24,0,0,0,14.49-16.41c2.59-10,5.67-28.22,5.670-58.48S236.92,79.5,234.33,69.52Zm-15.49,113a8,8,0,0,1-4.77,5.49c-31.65,12.22-85.48,12-86,12H128c-.54,0-54.33.2-86-12a8,8,0,0,1-4.77-5.49C34.8,173.39,32,156.57,32,128s2.8-45.39,5.16-54.47A8,8,0,0,1,41.93,68c30.52-11.79,81.66-12,85.85-12h.27c.54,0,54.38-.18,86,12a8,8,0,0,1,4.77,5.49C221.2,82.61,224,99.43,224,128S221.2,173.39,218.84,182.47Z",
  instagram:
    "M128,80a48,48,0,1,0,48,48A48.050,48.050,0,0,0,128,80Zm0,80a32,32,0,1,1,32-32A32,32,0,0,1,128,160ZM176,24H80A56.06,56.06,0,0,0,24,80v96a56.06,56.06,0,0,0,56,56h96a56.06,56.06,0,0,0,56-56V80A56.06,56.06,0,0,0,176,24Zm40,152a40,40,0,0,1-40,40H80a40,40,0,0,1-40-40V80A40,40,0,0,1,80,40h96a40,40,0,0,1,40,40ZM192,76a12,12,0,1,1-12-12A12,12,0,0,1,192,76Z",
} as const;

export type IconName = keyof typeof P;

export function Icon({ name, size = 24, className }: { name: IconName; size?: number; className?: string }) {
  return (
    <svg viewBox="0 0 256 256" width={size} height={size} className={className} aria-hidden fill="currentColor">
      <path d={P[name]} />
    </svg>
  );
}

/** Two pixel chevrons ("»") drawn on a 3px grid, as in the original buttons. */
const CHEVRON: [number, number][] = [
  [0, 0], [1, 1], [2, 2], [1, 3], [0, 4],
];
export function PixelArrow() {
  return (
    <svg className="px-arrow" viewBox="0 0 30 15" width={30} height={15} aria-hidden>
      {[1, 4].map((dx, k) => (
        <g key={k} className={`px-chev px-chev-${k}`}>
          {CHEVRON.map(([x, y]) => (
            <rect key={`${x}${y}`} x={(x + dx) * 3} y={y * 3} width={3} height={3} fill="currentColor" />
          ))}
        </g>
      ))}
    </svg>
  );
}

export function Asterisk({ size, color }: { size: number; color: string }) {
  return (
    <svg className="asterisk" viewBox="0 0 151 151" width={size} height={size} aria-hidden overflow="visible">
      {[0, 30, 60, 90, 120, 150].map((r) => (
        <path key={r} d="M75.5 0 L75.5 151" stroke={color} strokeWidth={17} transform={`rotate(${r} 75.5 75.5)`} />
      ))}
    </svg>
  );
}

export function PillLogo({ size = "md", light = false }: { size?: "sm" | "md" | "lg"; light?: boolean }) {
  return <img className={`rio-mark mark-${size}`} src={asset(light ? "rio-mark-white.svg" : "rio-mark-black.svg")} alt="" aria-hidden />;
}

/* ---------- Buttons ---------- */

type BtnVariant = "dark" | "light" | "ghost";
export function Btn({
  label,
  href = "#",
  variant = "dark",
  size = "lg",
  className = "",
  onClick,
  busy = false,
}: {
  label: string;
  href?: string;
  variant?: BtnVariant;
  size?: "lg" | "sm";
  className?: string;
  /** Renders a <button> instead of a link. */
  onClick?: () => void;
  busy?: boolean;
}) {
  const inner = (
    <>
      <span className="btn-box">
        <PixelArrow />
      </span>
      <span className="btn-label">
        <span className="btn-label-inner" data-label={label}>
          {label}
        </span>
      </span>
    </>
  );
  const cls = `btn btn-${variant} btn-${size} ${busy ? "is-busy" : ""} ${className}`;
  if (onClick)
    return (
      <button type="button" className={cls} onClick={onClick} disabled={busy} aria-busy={busy}>
        {inner}
      </button>
    );
  return (
    <a href={href} className={cls}>
      {inner}
    </a>
  );
}

/* ---------- Section label: pill — line — LABEL ---------- */

export function Label({
  text,
  pillFirst = false,
  light = true,
  className = "",
}: {
  text: string;
  pillFirst?: boolean;
  light?: boolean;
  className?: string;
}) {
  const pill = <PillLogo size="sm" light={light} />;
  const label = <span className="mono-12">{text}</span>;
  return (
    <Reveal className={`label-row ${light ? "on-dark" : "on-light"} ${className}`}>
      {pillFirst ? pill : label}
      <motion.span
        className="label-line"
        initial={{ scaleX: 0 }}
        whileInView={{ scaleX: 1 }}
        viewport={{ once: true, margin: "-10% 0px" }}
        transition={{ duration: 1.2, ease: EASE, delay: 0.15 }}
        style={{ originX: pillFirst ? 0 : 0 }}
      />
      {pillFirst ? label : pill}
    </Reveal>
  );
}

/* ---------- Motion helpers ---------- */

export function Reveal({
  children,
  className,
  delay = 0,
  y = 30,
  as = "div",
}: {
  children: ReactNode;
  className?: string;
  delay?: number;
  y?: number;
  as?: "div" | "p" | "h2" | "h3" | "h6" | "span" | "li";
}) {
  const M = motion[as];
  return (
    <M
      className={className}
      initial={{ opacity: 0, y, filter: "blur(8px)" }}
      whileInView={{ opacity: 1, y: 0, filter: "blur(0px)" }}
      viewport={{ once: true, margin: "-8% 0px" }}
      transition={{ duration: 0.9, ease: EASE, delay }}
    >
      {children}
    </M>
  );
}

function Char({ c, progress, range }: { c: string; progress: MotionValue<number>; range: [number, number] }) {
  const opacity = useTransform(progress, range, [0.1, 1]);
  return <motion.span style={{ opacity }}>{c}</motion.span>;
}

/** Text whose characters light up one by one as the block scrolls through the viewport. */
export function ScrollRevealText({ text, className, as = "h2" }: { text: string; className?: string; as?: "h2" | "p" }) {
  const ref = useRef<HTMLHeadingElement>(null);
  const { scrollYProgress } = useScroll({ target: ref, offset: ["start 0.9", "end 0.35"] });
  const words = text.split(" ");
  const total = text.replace(/ /g, "").length;
  let i = 0;
  const Tag = as;
  return (
    <Tag ref={ref} className={className} aria-label={text}>
      {words.map((w, wi) => (
        <span className="word" key={wi} aria-hidden>
          {[...w].map((c, ci) => {
            const start = i / total;
            i += 1;
            return <Char key={ci} c={c} progress={scrollYProgress} range={[start, Math.min(1, start + 1.5 / total)]} />;
          })}
          {wi < words.length - 1 ? " " : ""}
        </span>
      ))}
    </Tag>
  );
}

/** Number that counts up the first time it enters the viewport. */
export function CountUp({ to, prefix = "", suffix = "", format = (n: number) => String(Math.round(n)) }: {
  to: number;
  prefix?: string;
  suffix?: string;
  format?: (n: number) => string;
}) {
  const ref = useRef<HTMLSpanElement>(null);
  const inView = useInView(ref, { once: true, margin: "-10% 0px" });
  const [val, setVal] = useState(0);
  useEffect(() => {
    if (!inView) return;
    const c = animate(0, to, { duration: 1.8, ease: EASE, onUpdate: setVal });
    return () => c.stop();
  }, [inView, to]);
  return (
    <span ref={ref}>
      {prefix}
      {format(val)}
      {suffix}
    </span>
  );
}

/** Infinite horizontal loop; children are rendered twice so the -50% translate is seamless. */
export function Marquee({
  children,
  duration = 30,
  reverse = false,
  className = "",
  pauseOnHover = false,
}: {
  children: ReactNode;
  duration?: number;
  reverse?: boolean;
  className?: string;
  pauseOnHover?: boolean;
}) {
  return (
    <div className={`marquee ${pauseOnHover ? "marquee-pause" : ""} ${className}`}>
      <div className="marquee-track" style={{ animationDuration: `${duration}s`, animationDirection: reverse ? "reverse" : "normal" }}>
        <div className="marquee-group">{children}</div>
        <div className="marquee-group" aria-hidden>
          {children}
        </div>
      </div>
    </div>
  );
}

export function BigMarquee({ word, star = "#f0f0f0", reverse = false }: { word: string; star?: string; reverse?: boolean }) {
  const item = (
    <>
      <span className="giant">{word}</span>
      <Asterisk size={212} color={star} />
    </>
  );
  return (
    <Marquee duration={26} reverse={reverse} className="big-marquee">
      {item}
      {item}
    </Marquee>
  );
}

export function Ticker({ brand = "//RIO" }: { brand?: string }) {
  const msg =
    "Rio is in early access: Blender, LibreOffice Calc, Docker and Finder tutorials are live, and any desktop app works with a typed goal.";
  return (
    <Marquee duration={40} className="ticker">
      <span className="ticker-brand">{brand}</span>
      <span className="ticker-msg">{msg}</span>
    </Marquee>
  );
}
