import type { Metadata } from "next";
import { Inter, Fira_Code } from "next/font/google";
import { THEME_BOOTSTRAP_SCRIPT } from "@/lib/theme-script";
import "./globals.css";

const inter = Inter({
  subsets: ["latin"],
  weight: ["400", "500", "600", "700", "800"],
  display: "swap",
  variable: "--font-inter",
});

// Monospaced companion for metrics, iteration counters, and log timestamps;
// tabular figures keep live-updating numbers from shifting width.
const firaCode = Fira_Code({
  subsets: ["latin"],
  weight: ["400", "500", "600"],
  display: "swap",
  variable: "--font-fira-code",
});

export const metadata: Metadata = {
  title: "SCAR — Self-Correcting Agent for Research",
  description:
    "Autonomous AI research agent with iterative knowledge fusion, contradiction detection, and evidence-grounded reports.",
  keywords: ["SCAR", "AI research", "knowledge graph", "autonomous agent", "IKF", "JEV"],
  openGraph: {
    title: "SCAR — Self-Correcting Agent for Research",
    description: "Self-correcting AI research powered by multi-LLM reasoning",
    type: "website",
  },
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html
      lang="en"
      className={`h-full ${inter.variable} ${firaCode.variable}`}
      suppressHydrationWarning
    >
      <head>
        {/* Inline and synchronous on purpose: the stored choice must land on
            <html> before the first paint, otherwise the page flashes the wrong
            theme. Kept as a plain script so it runs at parse time. */}
        <script dangerouslySetInnerHTML={{ __html: THEME_BOOTSTRAP_SCRIPT }} />
      </head>
      <body className="min-h-full" suppressHydrationWarning>
        <div className="noise-overlay" aria-hidden="true" />
        {children}
      </body>
    </html>
  );
}
