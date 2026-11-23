import type { Metadata } from "next";
import React from "react";

export const metadata: Metadata = {
  title: "Research Console",
  description:
    "Autonomous AI research console featuring iterative knowledge fusion, contradiction detection, and evidence reports.",
};

export default function AppLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return children;
}
