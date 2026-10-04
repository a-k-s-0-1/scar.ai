"use client";

import {
  useEffect,
  useId,
  useLayoutEffect,
  useRef,
  useState,
  type ReactNode,
} from "react";
import { motion, useReducedMotion } from "motion/react";
import { useTheme } from "@/lib/preferences";

function cn(...parts: Array<string | undefined | false>) {
  return parts.filter(Boolean).join(" ");
}

type SvgPathDrawingTextAnimationProps = {
  text: string;
  fromColor?: string;
  toColor?: string;
  strokeWidth?: number;
  /** Seconds for one full draw pass */
  durationSec?: number;
  /** Restart from the beginning as soon as the draw finishes */
  loop?: boolean;
  viewBoxWidth?: number;
  viewBoxHeight?: number;
  fontSize?: number;
  className?: string;
};

function loadImage(url: string): Promise<HTMLImageElement> {
  return new Promise((resolve, reject) => {
    const img = new Image();
    img.onload = () => resolve(img);
    img.onerror = () => reject(new Error("svg raster failed"));
    img.src = url;
  });
}

function countOpaque(ctx: CanvasRenderingContext2D, w: number, h: number): number {
  const data = ctx.getImageData(0, 0, w, h).data;
  let n = 0;
  for (let i = 3; i < data.length; i += 4) {
    if (data[i] > 12) n += 1;
  }
  return n;
}

async function rasterInk(
  source: SVGSVGElement,
  apply: (text: SVGTextElement) => void,
): Promise<number> {
  const clone = source.cloneNode(true) as SVGSVGElement;
  clone.setAttribute("xmlns", "http://www.w3.org/2000/svg");
  const text = clone.querySelector("text");
  if (!text) return 0;
  apply(text as SVGTextElement);
  text.setAttribute("stroke", "#ffffff");
  (text as SVGTextElement).style.stroke = "#ffffff";

  const vb = source.viewBox.baseVal;
  const w = Math.max(1, Math.round(vb.width || 800));
  const h = Math.max(1, Math.round(vb.height || 160));
  clone.setAttribute("width", String(w));
  clone.setAttribute("height", String(h));
  clone.style.visibility = "visible";

  const xml = new XMLSerializer().serializeToString(clone);
  const blob = new Blob([xml], { type: "image/svg+xml;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  try {
    const img = await loadImage(url);
    const cw = Math.max(1, Math.round(w * 0.45));
    const ch = Math.max(1, Math.round(h * 0.45));
    const canvas = document.createElement("canvas");
    canvas.width = cw;
    canvas.height = ch;
    const ctx = canvas.getContext("2d", { willReadFrequently: true });
    if (!ctx) return 0;
    ctx.clearRect(0, 0, cw, ch);
    ctx.drawImage(img, 0, 0, cw, ch);
    return countOpaque(ctx, cw, ch);
  } finally {
    URL.revokeObjectURL(url);
  }
}

/** Smallest dash length that renders the same ink as the finished glyph */
async function measureExactDashLength(svg: SVGSVGElement): Promise<number> {
  const full = await rasterInk(svg, (text) => {
    text.style.strokeDasharray = "none";
    text.style.strokeDashoffset = "0";
  });
  if (full <= 0) {
    throw new Error("empty ink");
  }

  const covered = async (dash: number) => {
    const ink = await rasterInk(svg, (text) => {
      text.style.strokeDasharray = `${dash} 100000`;
      text.style.strokeDashoffset = "0";
    });
    return ink >= full * 0.994;
  };

  let hi = 64;
  while (hi < 24000 && !(await covered(hi))) {
    hi *= 2;
  }

  let lo = 1;
  while (lo < hi) {
    const mid = (lo + hi) >> 1;
    if (await covered(mid)) hi = mid;
    else lo = mid + 1;
  }

  return Math.max(1, lo);
}

/**
 * Draws SVG text via stroke-dashoffset. The loop restarts exactly when the
 * real glyph is fully drawn, so it never idles on the finished shape.
 */
function SvgPathDrawingTextAnimation({
  text,
  fromColor,
  toColor,
  strokeWidth = 2,
  durationSec = 5.5,
  loop = false,
  viewBoxWidth = 800,
  viewBoxHeight = 160,
  fontSize = 88,
  className,
}: SvgPathDrawingTextAnimationProps) {
  const { resolved } = useTheme();
  const isDark = resolved === "dark";
  const startGradient = fromColor ?? (isDark ? "#cda9e2" : "#8754a1");
  const endGradient = toColor ?? (isDark ? "#9b71b2" : "#321630");

  const reactId = useId().replace(/:/g, "");
  const gradientId = `pathGradient-${reactId}`;
  const svgRef = useRef<SVGSVGElement>(null);
  const textRef = useRef<SVGTextElement>(null);
  const [dashLength, setDashLength] = useState(0);
  const reduceMotion = useReducedMotion();
  const display = text.trim();

  useEffect(() => {
    if (!display || reduceMotion) return;
    const svg = svgRef.current;
    if (!svg) return;

    let cancelled = false;
    const run = async () => {
      try {
        await document.fonts.ready;
        if (cancelled || !svgRef.current) return;
        const dash = await measureExactDashLength(svgRef.current);
        if (!cancelled) setDashLength(dash);
      } catch {
        const el = textRef.current;
        if (!el || cancelled) return;
        const width = el.getComputedTextLength() || display.length * fontSize * 0.62;
        setDashLength(Math.max(1, Math.ceil(width * 1.15)));
      }
    };

    void run();
    return () => {
      cancelled = true;
    };
  }, [display, fontSize, viewBoxWidth, strokeWidth, reduceMotion]);

  useLayoutEffect(() => {
    const el = textRef.current;
    if (!el) return;
    if (reduceMotion || dashLength <= 0) {
      el.style.strokeDashoffset = "0";
      el.style.strokeDasharray = "none";
      return;
    }

    el.style.strokeDasharray = `${dashLength} ${dashLength}`;
    el.style.strokeDashoffset = String(dashLength);

    const drawMs = Math.max(0.8, durationSec) * 1000;
    const unitsPerMs = dashLength / drawMs;
    let offset = dashLength;
    let last = performance.now();
    let raf = 0;

    const tick = (now: number) => {
      const dt = Math.min(48, now - last);
      last = now;
      offset -= unitsPerMs * dt;
      if (offset <= 0) {
        el.style.strokeDashoffset = "0";
        if (!loop) {
          return;
        }
        offset = dashLength;
      }
      el.style.strokeDashoffset = String(offset);
      raf = window.requestAnimationFrame(tick);
    };

    raf = window.requestAnimationFrame(tick);
    return () => window.cancelAnimationFrame(raf);
  }, [dashLength, durationSec, loop, reduceMotion]);

  if (!display) return null;

  const ready = dashLength > 0 || Boolean(reduceMotion);

  return (
    <div
      className={cn(
        "flex min-h-[200px] w-full items-center justify-center",
        className,
      )}
    >
      <svg
        ref={svgRef}
        width="1000"
        height="420"
        viewBox={`0 0 ${viewBoxWidth} ${viewBoxHeight}`}
        className="h-auto w-full max-w-full"
        role="img"
        aria-label={display}
        style={{ visibility: ready ? "visible" : "hidden" }}
      >
        <defs>
          <linearGradient id={gradientId} x1="0%" y1="0%" x2="100%" y2="0%">
            <stop offset="0%" stopColor={startGradient} />
            <stop offset="100%" stopColor={endGradient} />
          </linearGradient>
        </defs>

        <text
          ref={textRef}
          x="50%"
          y="50%"
          textAnchor="middle"
          dominantBaseline="middle"
          fill="none"
          stroke={`url(#${gradientId})`}
          strokeWidth={strokeWidth}
          strokeLinejoin="round"
          strokeLinecap="round"
          fontSize={fontSize}
          fontWeight="bold"
          fontFamily="system-ui, -apple-system, sans-serif"
          letterSpacing="0.04em"
        >
          {display}
        </text>
      </svg>
    </div>
  );
}

export type PathDrawingPortfolioHeroProps = {
  /** Display name (brand / person) drawn large as an SVG path */
  brand: string;
  /** Short role or tagline under the name */
  tagline?: string;
  /** Small label above the name (e.g. RESEARCH AI) */
  eyebrow?: string;
  /** Gradient start color */
  fromColor?: string;
  /** Gradient end color */
  toColor?: string;
  /** Restart drawing loop on finish */
  loop?: boolean;
  /** Seconds for one full draw pass */
  durationSec?: number;
  /** Extra slot (for follow-up sections) */
  children?: ReactNode;
  className?: string;
};

/**
 * Portfolio hero: path-drawn name on entrance + soft entrance fade.
 * Pauses after one complete cycle and re-runs on page reload.
 */
export default function PathDrawingPortfolioHero({
  brand,
  tagline = "Self-Correcting Agent for Autonomous Research",
  eyebrow = "AUTONOMOUS KNOWLEDGE FUSION",
  fromColor,
  toColor,
  loop = false,
  durationSec = 4.5,
  children,
  className,
}: PathDrawingPortfolioHeroProps) {
  const name = brand.trim();
  const reduceMotion = useReducedMotion();
  const [ready, setReady] = useState(false);

  useEffect(() => {
    setReady(true);
  }, []);

  if (!name) return null;

  const instant = Boolean(reduceMotion) || !ready;

  return (
    <section
      data-path-drawing-hero
      className={cn(
        "relative flex min-h-screen w-full flex-col items-center justify-center",
        "bg-transparent text-[var(--text-primary)]",
        className,
      )}
    >
      <div className="relative z-10 flex w-full max-w-6xl flex-col items-center px-6 pb-10 pt-20 text-center sm:px-10 sm:pb-12">
        {eyebrow ? (
          <motion.p
            className="mb-6 text-[0.7rem] font-medium uppercase tracking-[0.35em] text-[var(--text-muted)] sm:mb-8 sm:text-xs"
            initial={instant ? false : { opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.7, ease: [0.22, 1, 0.36, 1] }}
          >
            {eyebrow}
          </motion.p>
        ) : null}

        <h1 className="sr-only">{name}</h1>
        <motion.div
          className="w-full"
          initial={instant ? false : { opacity: 0, scale: 0.985 }}
          animate={{ opacity: 1, scale: 1 }}
          transition={{ duration: 0.9, delay: 0.12, ease: [0.22, 1, 0.36, 1] }}
        >
          <SvgPathDrawingTextAnimation
            text={name}
            fromColor={fromColor}
            toColor={toColor}
            className="w-full min-h-[220px] sm:min-h-[300px] md:min-h-[380px]"
            fontSize={name.length > 12 ? 72 : name.length > 8 ? 96 : 148}
            viewBoxWidth={name.length > 8 ? 1100 : 860}
            viewBoxHeight={name.length > 8 ? 200 : 240}
            strokeWidth={2.4}
            durationSec={durationSec}
            loop={loop}
          />
        </motion.div>

        {tagline ? (
          <motion.p
            className="mt-4 max-w-md text-sm leading-relaxed text-[var(--text-secondary)] sm:mt-6 sm:text-base"
            initial={instant ? false : { opacity: 0, y: 16 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{
              duration: 0.75,
              delay: 0.55,
              ease: [0.22, 1, 0.36, 1],
            }}
          >
            {tagline}
          </motion.p>
        ) : null}
      </div>

      <motion.a
        href="#pipeline"
        aria-label="Scroll to pipeline"
        className="absolute bottom-8 left-1/2 z-10 flex -translate-x-1/2 flex-col items-center gap-2 text-[var(--text-muted)] transition-colors hover:text-[var(--text-primary)]"
        initial={instant ? false : { opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={{ duration: 0.6, delay: 1.1 }}
      >
        <span className="text-[0.65rem] uppercase tracking-[0.28em]">Scroll</span>
        <span
          aria-hidden
          className="path-drawing-scroll-cue block h-8 w-px origin-top bg-gradient-to-b from-[var(--text-muted)] to-transparent"
        />
      </motion.a>

      {children}
      <style>{`
        @keyframes path-drawing-scroll-cue {
          0%, 100% { transform: scaleY(1); opacity: 0.55; }
          50% { transform: scaleY(0.55); opacity: 0.2; }
        }
        [data-path-drawing-hero] .path-drawing-scroll-cue {
          animation: path-drawing-scroll-cue 1.8s ease-in-out infinite;
        }
        @media (prefers-reduced-motion: reduce) {
          [data-path-drawing-hero] .path-drawing-scroll-cue {
            animation: none;
            opacity: 0.45;
          }
        }
      `}</style>
    </section>
  );
}

export { PathDrawingPortfolioHero };

