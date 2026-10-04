import React from "react";
import { LandingNavbar } from "@/components/landing/LandingNavbar";
import { HeroSection } from "@/components/landing/HeroSection";
import { PipelineVisualizer } from "@/components/landing/PipelineVisualizer";
import { ComparisonMatrix } from "@/components/landing/ComparisonMatrix";
import { ArchitectureTopology } from "@/components/landing/ArchitectureTopology";
import { SelfHostingSection } from "@/components/landing/SelfHostingSection";
import { FaqSection } from "@/components/landing/FaqSection";
import { LandingFooter } from "@/components/landing/LandingFooter";

export default function LandingPage() {
  return (
    <div className="landing-wrapper">
      <LandingNavbar />
      <main>
        <HeroSection />
        <PipelineVisualizer />
        <ComparisonMatrix />
        <ArchitectureTopology />
        <SelfHostingSection />
        <FaqSection />
      </main>
      <LandingFooter />
    </div>
  );
}
