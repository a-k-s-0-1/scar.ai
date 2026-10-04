# Design System: Self-Correcting Research Agent MVP V1

## 1. Design Philosophy

### Core Principles

**1. Clarity First**
- Every interaction should be obvious
- Users should understand what's happening at all times
- Real-time progress, no waiting in the dark

**2. Deep Work Aesthetic**
- Professional, focused feel
- Minimal distraction
- Supports long research sessions
- Dark mode as primary (eyesight protection)

**3. Data-Centric**
- Visualizations support understanding, not decoration
- Every UI element shows something meaningful
- Evidence and sources always visible

**4. Responsive & Accessible**
- Works on desktop, tablet (mobile secondary)
- High contrast for readability
- Keyboard navigation supported
- WCAG 2.1 AA compliant

---

## 2. Color Palette

### Primary Colors

```
Dark Background:    #0F172A (slate-950)
Secondary BG:       #1E293B (slate-900)
Tertiary BG:        #334155 (slate-700)
Border:             #475569 (slate-600)
```

### Accent Colors

```
Primary Blue:       #3B82F6 (blue-500)  — Actions, progress
Success Green:      #10B981 (emerald-500) — High confidence
Warning Yellow:     #F59E0B (amber-500)  — Medium confidence
Danger Red:         #EF4444 (red-500)   — Low confidence, errors
```

### Text Colors

```
Primary Text:       #F1F5F9 (slate-100) — Main content
Secondary Text:     #CBD5E1 (slate-400) — Labels, metadata
Tertiary Text:      #94A3B8 (slate-500) — Disabled, inactive
```

### Semantic Colors

```
High Confidence:    #10B981 (emerald-500)
Medium Confidence:  #F59E0B (amber-500)
Low Confidence:     #EF4444 (red-500)
Neutral:            #6B7280 (gray-500)
```

### Color Palette (Tailwind Reference)

```
Background: slate-950, slate-900, slate-800
Text: slate-100, slate-400, slate-500
Borders: slate-700, slate-600
Accents: blue-500, emerald-500, amber-500, red-500
```

---

## 3. Typography

### Font Family

```css
/* Primary: Inter (system font fallback) */
font-family: "Inter", -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;

/* Monospace: Fira Code (for code/JSON) */
font-family: "Fira Code", "Courier New", monospace;
```

### Font Sizes & Weights

| Usage | Size | Weight | Line Height | Tailwind Class |
|-------|------|--------|------------|---|
| Page Title | 2.25rem (36px) | 700 | 1.2 | `text-4xl font-bold` |
| Section Header | 1.875rem (30px) | 700 | 1.2 | `text-3xl font-bold` |
| Subsection | 1.5rem (24px) | 600 | 1.3 | `text-2xl font-semibold` |
| Card Title | 1.125rem (18px) | 600 | 1.3 | `text-lg font-semibold` |
| Body Text | 1rem (16px) | 400 | 1.5 | `text-base leading-relaxed` |
| Small Label | 0.875rem (14px) | 500 | 1.4 | `text-sm font-medium` |
| Tiny | 0.75rem (12px) | 500 | 1.3 | `text-xs font-medium` |
| Code | 0.875rem (14px) | 400 | 1.4 | `font-mono text-sm` |

### Font Rendering

```css
/* Ensure crisp text rendering */
-webkit-font-smoothing: antialiased;
-moz-osx-font-smoothing: grayscale;
font-feature-settings: "kern" 1;
```

---

## 4. Spacing Scale

```
2px   → 0.125rem  (spacing-0.5)
4px   → 0.25rem   (spacing-1)
8px   → 0.5rem    (spacing-2)
12px  → 0.75rem   (spacing-3)
16px  → 1rem      (spacing-4)
24px  → 1.5rem    (spacing-6)
32px  → 2rem      (spacing-8)
48px  → 3rem      (spacing-12)
64px  → 4rem      (spacing-16)
```

### Padding Defaults

```
Button:     px-4 py-2.5 (16px x 10px)
Card:       p-6 (24px all sides)
Section:    py-8 px-6 (32px vertical, 24px horizontal)
```

### Margin Defaults

```
Between sections:   mb-12 (48px)
Between components: mb-6 (24px)
Between items:      mb-4 (16px)
```

---

## 5. Border & Radius

### Border Radius

```
Sharp edges:        rounded-none (0px)
Button/Small:       rounded-lg (8px)
Card/Medium:        rounded-lg (8px)
Large surfaces:     rounded-xl (12px)
Full rounded:       rounded-full (999px)
```

### Border Widths

```
Thin:       border (1px)
Medium:     border-2 (2px)
Thick:      border-4 (4px)
```

### Border Colors

```
Subtle:     border-slate-700
Active:     border-blue-500
Success:    border-emerald-500
Error:      border-red-500
```

---

## 6. Shadows & Elevation

### Shadow Levels

```css
/* Subtle elevation for interactive elements */
.shadow-sm {
  box-shadow: 0 1px 2px 0 rgba(0, 0, 0, 0.05);
}

/* Cards and dialogs */
.shadow-md {
  box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1);
}

/* Modals, dropdowns */
.shadow-lg {
  box-shadow: 0 10px 15px -3px rgba(0, 0, 0, 0.2);
}

/* Floating elements (floating action buttons) */
.shadow-xl {
  box-shadow: 0 20px 25px -5px rgba(0, 0, 0, 0.2);
}
```

---

## 7. Component Specifications

### 7.1 Header

```
Height: 64px (4rem)
Background: slate-900
Border-bottom: 1px solid slate-700
Padding: px-6

Contents:
- Logo (24x24px, left-aligned)
- Title (text-lg font-semibold, left-aligned)
- User profile / Settings (right-aligned)

Implementation:
<header className="flex h-16 items-center justify-between bg-slate-900 border-b border-slate-700 px-6">
  <div className="flex items-center gap-3">
    <Logo size={24} />
    <h1 className="text-lg font-semibold">Self-Correcting Research</h1>
  </div>
  <UserMenu />
</header>
```

### 7.2 Buttons

#### Primary Button (Call-to-action)

```
Background: bg-blue-600
Hover: bg-blue-700
Active: bg-blue-800
Text: text-white font-semibold
Padding: px-6 py-2.5
Radius: rounded-lg
Border: 1px border-blue-500 (subtle)
Transition: bg-color 200ms ease-in-out

Tailwind:
className="px-6 py-2.5 bg-blue-600 hover:bg-blue-700 active:bg-blue-800 text-white font-semibold rounded-lg border border-blue-500 transition-colors duration-200"
```

#### Secondary Button (Alternative)

```
Background: bg-slate-800
Hover: bg-slate-700
Text: text-slate-100
Padding: px-6 py-2.5
Radius: rounded-lg
Border: 1px border-slate-600

Tailwind:
className="px-6 py-2.5 bg-slate-800 hover:bg-slate-700 text-slate-100 font-semibold rounded-lg border border-slate-600"
```

#### Icon Button

```
Size: 40x40px
Background: bg-slate-800 (optional)
Hover: bg-slate-700
Padding: p-2
Radius: rounded-lg

Tailwind:
className="p-2 hover:bg-slate-700 rounded-lg transition-colors"
```

### 7.3 Input Fields

```
Background: bg-slate-800
Border: 1px solid border-slate-600
Border-focus: 2px solid border-blue-500
Text: text-slate-100
Placeholder: placeholder-slate-500
Padding: px-4 py-2.5
Radius: rounded-lg
Transition: all 200ms ease-in-out

Tailwind:
className="w-full px-4 py-2.5 bg-slate-800 border border-slate-600 text-slate-100 placeholder-slate-500 rounded-lg focus:border-2 focus:border-blue-500 focus:outline-none transition-all"
```

### 7.4 Cards

```
Background: bg-slate-800
Border: 1px border-slate-700
Padding: p-6
Radius: rounded-lg
Shadow: shadow-sm

Tailwind:
className="bg-slate-800 border border-slate-700 p-6 rounded-lg shadow-sm"
```

### 7.5 Progress Bars

```
Height: 8px
Background: bg-slate-700
Filled: bg-blue-500
Radius: rounded-full
Transition: width 300ms ease-out

Tailwind:
className="w-full h-2 bg-slate-700 rounded-full overflow-hidden">
  <div className="h-full bg-blue-500 rounded-full transition-all duration-300" />
</div>
```

### 7.6 Badges & Status Indicators

#### High Confidence

```
Background: bg-emerald-900/30
Border: border-emerald-700
Text: text-emerald-200
Padding: px-3 py-1
Radius: rounded-full
Font-size: text-xs font-medium
```

#### Medium Confidence

```
Background: bg-amber-900/30
Border: border-amber-700
Text: text-amber-200
```

#### Low Confidence

```
Background: bg-red-900/30
Border: border-red-700
Text: text-red-200
```

---

## 8. Layout Patterns

### Main Layout (with sidebar)

```tsx
<div className="flex h-screen bg-slate-950">
  {/* Sidebar (optional) */}
  <aside className="w-64 bg-slate-900 border-r border-slate-700 p-6 overflow-y-auto">
    {/* Navigation */}
  </aside>
  
  {/* Main content */}
  <main className="flex-1 overflow-y-auto">
    {/* Header */}
    {/* Content */}
  </main>
</div>
```

### Card Grid

```tsx
<div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
  <Card />
  <Card />
  <Card />
</div>
```

### Full-Width Section

```tsx
<section className="py-12 px-6 max-w-7xl mx-auto">
  <h2 className="text-3xl font-bold mb-8">Section Title</h2>
  <div className="space-y-6">
    {/* Content */}
  </div>
</section>
```

---

## 9. Interactive States

### Hover Effects

```
Buttons:     brightness increase + slight lift (shadow)
Cards:       slight background brighten
Links:       text underline + color change
```

### Active/Selected States

```
Buttons:     darker background
Tabs:        border-bottom blue + bold text
Links:       text color change to blue
```

### Disabled States

```
Opacity:     opacity-50
Cursor:      cursor-not-allowed
Colors:      text-slate-500 (dimmed)
No hover:    no background change
```

### Focus States (Accessibility)

```
All interactive:    2px solid blue-500 ring
Inputs:            border-2 border-blue-500 outline-none
Buttons:           ring-2 ring-blue-500 ring-offset-2 ring-offset-slate-900
```

---

## 10. Dark Mode Strategy

### Why Dark Mode First?

1. **Eye strain reduction** during long research sessions
2. **Battery savings** on OLED screens
3. **Professional aesthetics** for analysis/research work
4. **Modern UI expectation** for technical tools

### Color Hierarchy (Dark)

```
Background:  slate-950 (darkest)
Surface:     slate-900 (containers)
Overlay:     slate-800 (cards, dialogs)
Border:      slate-700 (dividers)
Text:        slate-100 (primary)
Text:        slate-400 (secondary)
Text:        slate-500 (tertiary)
```

### No Light Mode in V1

Light mode is explicitly excluded from Phase 1. Can be added in V1.1 if needed.

---

## 11. Animations & Transitions

### Entrance Animations

```css
/* Fade in */
@keyframes fadeIn {
  from {
    opacity: 0;
  }
  to {
    opacity: 1;
  }
}

/* Slide up */
@keyframes slideUp {
  from {
    opacity: 0;
    transform: translateY(16px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

/* Scale in */
@keyframes scaleIn {
  from {
    opacity: 0;
    transform: scale(0.95);
  }
  to {
    opacity: 1;
    transform: scale(1);
  }
}
```

### Transition Durations

```
Fast interactions:    200ms
Standard:             300ms
Slow transitions:     500ms
Slow animations:      800ms
```

### Usage

```tsx
{/* Fade in on mount */}
<div className="animate-fade-in">Content</div>

{/* Slide up on appear */}
<div className="animate-slide-up">Content</div>

{/* Smooth color transitions */}
<button className="transition-colors duration-200 hover:bg-slate-700">
  Click me
</button>
```

---

## 12. Responsive Design

### Breakpoints (Tailwind)

```
sm: 640px   (tablets)
md: 768px   (small desktop)
lg: 1024px  (desktop)
xl: 1280px  (large desktop)
2xl: 1536px (extra large)
```

### Mobile-First Approach

```tsx
{/* Stack on mobile, grid on desktop */}
<div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
  {/* Cards */}
</div>

{/* Hide on mobile, show on desktop */}
<aside className="hidden lg:block">
  {/* Sidebar */}
</aside>
```

### Touch-Friendly Design

```
Minimum tap target: 44x44px
Padding around buttons: 8px
No hover-only interactions
Clear visual feedback
```

---

## 13. Page Templates

### Template 1: Research Form (Home)

```
┌─────────────────────────────────────┐
│          HEADER (64px)              │
├─────────────────────────────────────┤
│                                     │
│   Welcome to Research Agent         │
│                                     │
│   ┌───────────────────────────┐    │
│   │ Enter research question:  │    │
│   │ [                       ] │    │
│   │                           │    │
│   │ [Advanced Options ▼]      │    │
│   │                           │    │
│   │        [Start Research]   │    │
│   └───────────────────────────┘    │
│                                     │
│   Recent research                   │
│   ┌────────────┐ ┌────────────┐   │
│   │ Question 1 │ │ Question 2 │   │
│   └────────────┘ └────────────┘   │
│                                     │
└─────────────────────────────────────┘
```

### Template 2: Research Session (Progress)

```
┌─────────────────────────────────────┐
│          HEADER (64px)              │
├─────────────────────────────────────┤
│                                     │
│ Research Progress        [Stop]     │
│                                     │
│ ┌─────────────────────────────────┐ │
│ │ Iteration 3/8                   │ │
│ │                                 │ │
│ │ Current step: Extracting claims │ │
│ │ ███████░░░░░░░░░░░░░ 35%       │ │
│ │                                 │ │
│ │ Sources: 14  Claims: 32         │ │
│ │ Time: 2:45 / 10:00              │ │
│ └─────────────────────────────────┘ │
│                                     │
│ Knowledge Graph:                    │
│ ┌─────────────────────────────────┐ │
│ │          o                      │ │
│ │         /|\                     │ │
│ │        o-+-o                    │ │
│ │       / | \                     │ │
│ │      o  o  o                    │ │
│ └─────────────────────────────────┘ │
│                                     │
│ Recent claims:                      │
│ • Biomass can reduce coal use      │ │
│ • Economic viability unclear       │ │
│                                     │
└─────────────────────────────────────┘
```

### Template 3: Final Report

```
┌─────────────────────────────────────┐
│          HEADER (64px)              │
├─────────────────────────────────────┤
│                                     │
│ [Report] [Knowledge] [Contradictions]
│                                     │
│ Research Question                   │
│                                     │
│ ┌─────────────────────────────────┐ │
│ │ EXECUTIVE SUMMARY               │ │
│ │                                 │ │
│ │ Based on 18 sources, this       │ │
│ │ report finds that...            │ │
│ └─────────────────────────────────┘ │
│                                     │
│ EVIDENCE TABLE                      │
│ ┌────────────────────────────────┐ │
│ │ Claim | Source | Confidence    │ │
│ ├────────────────────────────────┤ │
│ │ ...  | ...    | High           │ │
│ │ ...  | ...    | Medium         │ │
│ └────────────────────────────────┘ │
│                                     │
│ [Export JSON] [Export HTML] [Share] │
│                                     │
└─────────────────────────────────────┘
```

---

## 14. Accessibility

### WCAG 2.1 AA Compliance

1. **Contrast Ratio**: All text meets 4.5:1 (normal) / 3:1 (large)
   - Text on background: verified
   - UI components: verified
   
2. **Keyboard Navigation**:
   - Tab order logical
   - Focus indicators visible (blue ring)
   - No keyboard traps

3. **Screen Readers**:
   - Semantic HTML (`<button>`, `<form>`, `<nav>`)
   - ARIA labels where needed
   - Form labels associated

4. **Motion**:
   - Animations respectful of `prefers-reduced-motion`
   - No auto-playing video/audio

### Implementation

```tsx
// Keyboard accessible button
<button
  onClick={handleClick}
  className="focus:ring-2 focus:ring-blue-500 focus:ring-offset-2"
  aria-label="Submit research question"
>
  Submit
</button>

// Reduced motion support
<div className="motion-safe:animate-slide-up">
  Content animates on devices that support it
</div>

// Form labels
<label htmlFor="question" className="block text-sm font-medium">
  Research Question
</label>
<input
  id="question"
  type="text"
  aria-describedby="question-help"
/>
<p id="question-help" className="text-xs text-slate-500">
  Ask a clear, specific question for best results
</p>
```

---

## 15. Icon Set

### Icons Used (Heroicons)

```
Search:             MagnifyingGlassIcon
Settings:           Cog6ToothIcon
Menu:               Bars3Icon
Close:              XMarkIcon
Check:              CheckIcon
Clock:              ClockIcon
Lightning:          BoltIcon
Error:              ExclamationCircleIcon
Info:               InformationCircleIcon
Link:               LinkIcon
Download:           ArrowDownTrayIcon
Share:              ShareIcon
```

### Icon Sizing

```
Tiny (16px):   used in labels
Small (20px):  inline with text
Medium (24px): standalone button icons
Large (32px):  prominent actions
```

---

## 16. Tailwind Configuration

```javascript
// tailwind.config.js
module.exports = {
  content: [
    './app/**/*.{js,ts,jsx,tsx}',
    './components/**/*.{js,ts,jsx,tsx}',
  ],
  theme: {
    extend: {
      colors: {
        slate: {
          950: '#0F172A',
          900: '#1E293B',
          800: '#334155',
          700: '#475569',
          600: '#64748B',
          500: '#64748B',
          400: '#CBD5E1',
          100: '#F1F5F9',
        },
      },
      fontFamily: {
        sans: ['Inter', 'system-ui', '-apple-system'],
        mono: ['Fira Code', 'monospace'],
      },
      animation: {
        'fade-in': 'fadeIn 300ms ease-out',
        'slide-up': 'slideUp 300ms ease-out',
        'scale-in': 'scaleIn 300ms ease-out',
      },
      keyframes: {
        fadeIn: { ... },
        slideUp: { ... },
        scaleIn: { ... },
      },
    },
  },
  plugins: [
    require('@tailwindcss/forms'),
  ],
};
```

---

## 17. Design Assets

### Figma Link
*(Created during design phase, not part of V1)*

### Logo Specifications

```
Primary Logo:   Horizontal lockup, minimum 120px width
Icon Only:      24x24px, scalable to 64x64px
Usage:          Header, favicon, social sharing
Color:          White (#F1F5F9) on dark background
Spacing:        Minimum 8px clearspace on all sides
```

### Favicon

```
Size: 32x32px, 64x64px (for retina)
Format: PNG or SVG
Color: Blue circle (#3B82F6) with white element
```

---

## 18. Component Library Setup

### Using shadcn/ui (Optional but Recommended)

```bash
# Install shadcn/ui components as needed
npx shadcn-ui@latest add button
npx shadcn-ui@latest add input
npx shadcn-ui@latest add card
npx shadcn-ui@latest add tabs
npx shadcn-ui@latest add dialog
npx shadcn-ui@latest add progress
npx shadcn-ui@latest add table
```

### Custom Components Folder

```
components/
├── ui/                    (base components)
│   ├── Button.tsx
│   ├── Input.tsx
│   ├── Card.tsx
│   └── Badge.tsx
├── forms/                 (form components)
│   └── ResearchForm.tsx
├── session/               (session-specific)
│   ├── ProgressWidget.tsx
│   └── ControlPanel.tsx
└── report/                (report display)
    ├── ReportView.tsx
    ├── EvidenceTable.tsx
    └── KnowledgeGraph.tsx
```

---

## 19. Dark Mode CSS Variables (Optional Enhancement)

For future expansion to light mode:

```css
:root {
  /* Light mode */
  --bg-primary: #FFFFFF;
  --bg-secondary: #F9FAFB;
  --text-primary: #1F2937;
  --text-secondary: #6B7280;
  --border: #E5E7EB;
  --accent: #3B82F6;
}

@media (prefers-color-scheme: dark) {
  :root {
    /* Dark mode */
    --bg-primary: #0F172A;
    --bg-secondary: #1E293B;
    --text-primary: #F1F5F9;
    --text-secondary: #CBD5E1;
    --border: #475569;
    --accent: #3B82F6;
  }
}

/* Usage in components */
.card {
  background-color: var(--bg-secondary);
  color: var(--text-primary);
  border: 1px solid var(--border);
}
```

---

## 20. Design System Documentation

### For Team Reference

This design system should be referenced when:
- Creating new components
- Updating existing components
- Designing new features
- Reviewing pull requests

### Updates to Design System

Any changes to colors, spacing, or component specs must be:
1. Documented in this file
2. Reviewed by design/dev leads
3. Applied consistently across codebase
4. Tested for accessibility

---

## Quick Reference Checklist

Before deploying a new page/component:

- [ ] Uses colors from the palette (no custom hex values)
- [ ] Text contrast ≥4.5:1 (WCAG AA)
- [ ] Spacing uses the defined scale
- [ ] Buttons follow button specs (padding, radius, colors)
- [ ] Forms use Input component
- [ ] Cards use Card component
- [ ] Responsive breakpoints applied
- [ ] Focus states visible (ring)
- [ ] Hover states appropriate
- [ ] Icons from approved set
- [ ] Typography follows hierarchy
- [ ] No placeholder text in production
- [ ] Loading states defined
- [ ] Error states defined
- [ ] Success states defined

---

**Document Version:** 1.0  
**Last Updated:** September 26, 2026  
**Owner:** MASTER  
**Status:** Ready for Implementation  
**Design Lead:** TBD  
**Figma File:** TBD (to be created during design phase)
