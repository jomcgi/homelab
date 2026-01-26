# Brutalist Visual Aesthetic Alignment

## Overview

Align Claude Code's visual design with the brutalist aesthetic used across other homelab websites, creating a cohesive and striking visual identity.

## Design Principles

### Core Brutalist Elements

- **Typography**: Monospace fonts (Courier New) throughout
- **Colors**: Stark black and white with high contrast
- **Borders**: Bold 2px solid borders, no border-radius
- **Layout**: Raw, geometric shapes with clear hierarchy
- **Spacing**: Generous whitespace with intentional gaps
- **Effects**: No gradients, shadows, or smooth transitions

## Implementation

### CSS Variables

```css
:root {
  --bg: #fff;
  --fg: #000;
  --border-width: 2px;
  --font-mono: "Courier New", Courier, monospace;
  --letter-spacing-header: 3px;
  --letter-spacing-normal: 0.05em;
}

body.dark {
  --bg: #000;
  --fg: #fff;
}
```

### Component Styling

#### Header Bar

- Inverted colors (black background, white text)
- Uppercase text with wide letter spacing
- Fixed height with no padding variations
- Sharp corners, no rounded edges

#### Chat Interface

- Monospace font for all text
- Clear message boundaries with borders
- Timestamp in military format
- No avatars or profile pictures
- Raw markdown display option

#### Forms and Inputs

- Black borders on white background
- No focus glow effects
- Uppercase labels
- Monospace placeholder text
- Clear disabled states

#### Buttons

- Solid black or white backgrounds
- No hover animations, only opacity changes
- Uppercase text with letter spacing
- Consistent padding and height

### Layout Structure

```
┌─────────────────────────────────────┐
│ CLAUDE CODE             [DARK] [?] │ <- Header (inverted)
├─────────────────────────────────────┤
│ ┌─────────┬───────────────────────┐ │
│ │ FILES   │ CONVERSATION          │ │ <- Main content
│ │         │                       │ │
│ │ > src/  │ User: Hello           │ │
│ │   app.ts│ Claude: Hi there      │ │
│ │         │                       │ │
│ └─────────┴───────────────────────┘ │
│ ┌─────────────────────────────────┐ │
│ │ [TYPE MESSAGE HERE...]          │ │ <- Input area
│ └─────────────────────────────────┘ │
└─────────────────────────────────────┘
```

## Mobile Responsive Design

- Stack layout on small screens
- Maintain brutalist aesthetic
- Larger touch targets
- Simplified navigation
- Same stark visual style

## Dark Mode

- True black (#000) background
- Pure white (#fff) text
- Inverted borders and controls
- High contrast maintained
- Toggle in header bar

## Animation Philosophy

- No smooth transitions
- Instant state changes
- Binary visibility (show/hide)
- No loading spinners (use text: "LOADING...")
- No progress bars (use percentages: "75% COMPLETE")

## Typography Scale

```css
.text-xs {
  font-size: 10px;
}
.text-sm {
  font-size: 11px;
}
.text-base {
  font-size: 13px;
}
.text-lg {
  font-size: 16px;
}
.text-xl {
  font-size: 20px;
}
```

## Benefits

- **Brand Consistency**: Unified aesthetic across all services
- **Performance**: Minimal CSS, no animations or effects
- **Accessibility**: High contrast, clear hierarchy
- **Memorable**: Distinctive, bold visual style
- **Honest**: Form follows function, no decoration

## Inspiration Sources

- hikes.jomcgi.dev
- Classic terminal interfaces
- Brutalist web design movement
- Early computer UIs (DOS, early Unix)

## Implementation Checklist

- [ ] Remove all border-radius properties
- [ ] Replace system fonts with Courier New
- [ ] Implement black/white color scheme
- [ ] Add 2px solid borders
- [ ] Remove all animations/transitions
- [ ] Add dark mode toggle
- [ ] Uppercase all headers
- [ ] Add letter-spacing to headers
- [ ] Simplify form controls
- [ ] Remove decorative elements
