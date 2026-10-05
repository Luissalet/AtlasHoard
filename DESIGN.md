---
name: "Atlas's Hoard"
description: "The inherited Hoard visual system for a local shared filesystem workspace."
colors:
  deep: "#171919"
  sunken: "#121414"
  surface: "#1e2121"
  elevated: "#282b2c"
  hover: "#303334"
  border: "#3a3d3e"
  border-hover: "#5e6364"
  text: "#e1eaec"
  text-muted: "#b4bcbe"
  text-dim: "#9ba4a6"
  accent: "#d5b575"
  accent-strong: "#dfc694"
  accent-ink: "#161818"
  accent-soft: "rgba(213, 181, 117, 0.14)"
  accent-line: "rgba(213, 181, 117, 0.38)"
typography:
  application-name:
    fontFamily: "'Cinzel', 'Iowan Old Style', Charter, Georgia, 'Liberation Serif', 'Noto Serif', 'Times New Roman', serif"
    fontSize: "25px"
    fontWeight: 500
    lineHeight: 1.5
  title:
    fontFamily: "'Source Sans 3', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Noto Sans', 'Liberation Sans', Arial, sans-serif"
    fontSize: "22px"
    fontWeight: 600
    lineHeight: 1.3
  body:
    fontFamily: "'Source Sans 3', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Noto Sans', 'Liberation Sans', Arial, sans-serif"
    fontSize: "15px"
    lineHeight: 1.5
  metadata:
    fontFamily: "'Source Sans 3', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Noto Sans', 'Liberation Sans', Arial, sans-serif"
    fontSize: "12px"
    lineHeight: 1.5
  path:
    fontFamily: "'JetBrains Mono', ui-monospace, SFMono-Regular, Menlo, Consolas, 'Liberation Mono', monospace"
    fontSize: "12px"
    lineHeight: 1.5
rounded:
  sm: "6px"
  md: "8px"
spacing:
  compact: "6px"
  tight: "8px"
  control: "10px"
  row-inset: "12px"
  standard: "16px"
  group: "20px"
  section: "24px"
  workspace: "32px"
components:
  button:
    backgroundColor: "{colors.elevated}"
    textColor: "{colors.text}"
    rounded: "{rounded.sm}"
    padding: "9px 16px"
  button-hover:
    backgroundColor: "{colors.hover}"
  button-quiet:
    backgroundColor: "transparent"
    textColor: "{colors.text}"
    rounded: "{rounded.sm}"
  input:
    backgroundColor: "{colors.sunken}"
    textColor: "{colors.text}"
    rounded: "{rounded.sm}"
    padding: "10px"
  project-selected:
    backgroundColor: "{colors.accent-soft}"
    textColor: "{colors.text}"
    rounded: "{rounded.sm}"
  form-panel:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.text}"
    rounded: "{rounded.md}"
    padding: "24px"
---

# Design System: Atlas's Hoard

## Overview

**Creative North Star: "The inherited Hoard workspace"**

Atlas extends the existing Hoard family: charcoal surfaces, a serif application name, locally available UI fonts and a restrained warm accent. The implemented world is practical and quiet. File-management controls and readable rows carry the experience; imagery does not carry navigation or meaning.

This is an extraction from the finished HTML/CSS/JavaScript, not a replacement identity. `atlas_hoard/hoard_link/ui/hoard-theme.css` remains authoritative for family tokens. The current `data-hoard-app="atlas"` has no dedicated palette selector in that file, so it inherits the root palette. The values above record that current result; do not create a separate Atlas palette from this document. Surface topology, operating mode and workflow belong in `.impeccable/surfaces/storage.md`.

**Key Characteristics:**

- Charcoal tonal layers and fine rules establish hierarchy.
- Serif naming, sans-serif work text and monospace filesystem paths have distinct jobs.
- Warm accent marks current location, focus and file outlines.
- Controls remain recognizable and explicit; content can wrap instead of being truncated.

## Colors

Warm parchment accent sits against slightly cool charcoal neutrals. Token values are recorded in frontmatter; the inherited stylesheet owns their definitions.

### Primary

- **Parchment accent:** current-folder strokes, keyboard focus and the outline file icon.
- **Light parchment:** selected-folder labels and links.
- **Translucent parchment:** selected-project fill and border; status feedback uses the soft fill.
- **Accent ink:** selection text when the accent becomes the background.

### Neutral

- **Deep charcoal:** the page and main working surface.
- **Sunken charcoal:** inputs and the selected-folder path strip.
- **Surface charcoal:** the projects rail and project form panel.
- **Elevated charcoal / hover charcoal:** ordinary button rest and hover states.
- **Quiet rule / emphasized rule:** row dividers, panel boundaries and control strokes.
- **Light ink / muted ink / dim ink:** primary text, supporting content and field placeholders.

**The Inherited Palette Rule.** Resolve colors through the existing Hoard custom properties. Keep local mappings in agreement with the shared theme rather than maintaining an independent color definition.

## Typography

**Display Font:** the inherited Hoard serif stack, reserved here for the application name.

**Body Font:** the inherited Hoard sans-serif stack for task titles, file names, labels and controls.

**Label/Mono Font:** the inherited Hoard monospace stack for exact filesystem paths.

**Character:** a modest serif signature identifies the application while straightforward sans-serif text supports scanning. Font names are local fallbacks, not a guarantee that a named font is installed; the UI adds no remote font dependency.

### Hierarchy

- **Application name:** modest serif heading; it reduces to (22px) on the narrow surface.
- **Title:** medium-weight sans-serif for project names and form titles.
- **Section:** sans-serif (16px, 600) with the file-section heading at (17px).
- **Body:** comfortable work text with goal descriptions capped at (72ch).
- **Labels:** form labels use (14px); supporting metadata and table headings use the compact metadata role. Table headings use (500), ordinary file names use (500), and numbers use tabular figures.
- **Paths:** compact monospace, selectable in full and allowed to wrap anywhere.

**The Path Legibility Rule.** Keep paths as text, preserve their exact content and allow wrapping; a narrow viewport must not turn a path into an unexplained abbreviation.

## Layout

Group related work with spacing and thin boundaries. Use the available width for records instead of placing each record in a card. Controls align beside their context where space permits and wrap or stack when it does not.

The current explorer uses a (250px) projects rail and a flexible main column, with (32px) desktop working insets. At the observed (760px) breakpoint the rail moves above the content, project buttons form a horizontally scrollable row, working insets reduce to (20px), folder controls wrap, and forms become one column. The file table keeps name and access visible while dropping the attribution column. These are this surface's implementation facts, not a mandatory composition for every future Atlas screen.

Full-width paths and long file names wrap. The table wrapper can scroll if content still requires it. The app uses normal document scrolling; content is not forced into a fixed-height viewport.

## Elevation & Depth

This surface conveys depth with darker wells, lighter control fills and fine borders. Its own stylesheet applies no card or panel shadows. The inherited theme exposes a shadow token, but that unused capability is not made a requirement for Atlas. Selected states remain in place; hover changes color rather than moving the control.

## Shapes

Controls and fields use gently rounded corners from the small radius token; the project form uses the medium radius. Working rows and the path strip remain square-edged. One-pixel rules divide table rows and separate sections. The outline document icon is real inline SVG and is hidden from assistive technology because the adjacent file name supplies its meaning.

## Components

### Buttons

Ordinary task controls are restrained bordered buttons with elevated fill. The default minimum height is (42px); row-level path actions use (36px) and a smaller type size (13px). Quiet actions are transparent at rest. Hover changes the fill; keyboard focus receives an accent outline (2px) with an offset (3px). Disabled submit controls reduce opacity and use a waiting cursor.

There is no filled primary CTA in the current explorer. The family's optional primary-button recipe is not evidence that Atlas uses one.

### Inputs / Fields

Fields sit in the sunken neutral well, with a fine border, small rounded corners, visible labels and supporting text where needed. The caret uses the accent. Input, select and button typography inherits the working font. Focus shares the same visible outline treatment as other controls.

### Navigation

Project buttons communicate selection through `aria-current` and a soft accent fill with an accent border. Folder buttons communicate selection through `aria-pressed`, an accent stroke and lighter accent text. The two levels remain visually and semantically distinct. Folder labels are words, not icon-only guesses.

### File rows

One semantic table organizes file identity, registration attribution and the path action. A small document outline leads a file name with the relative path below it. Rows are ruled rather than raised. Missing-file text appears alongside the corresponding record instead of erasing it.

### Containers and feedback

The project form is an inline bordered surface; file registration opens inline within the selected project. Empty-folder guidance occupies the file area. A page-level polite live region carries success or error feedback. Error colors are a local state treatment, not an additional brand accent.

### Motion

Buttons transition background and border colors for (0.12s, ease-out) only when reduced motion is not requested. Keep motion tied to the control state; this implementation does not animate layout or navigation.

## Do's and Don'ts

### Do:

- **Do** use the inherited Hoard tokens and local font stacks as the visual authority.
- **Do** preserve the roles of serif naming, sans-serif task text and monospace paths.
- **Do** show current location with both explicit labels and selected-control styling.
- **Do** keep focus visible and retain readable wrapping for long paths and names.
- **Do** document surface-specific topology and behavior in its surface brief.

### Don't:

- **Don't** promote a synthetic demonstration's project name, file name, app membership or disk path into a product default.
- **Don't** replace ordinary file rows with decorative asset cards merely to express the brand.
- **Don't** introduce a separate Atlas palette or a remote font dependency from this extraction.
- **Don't** infer computed contrast compliance from the regex-only detector result.

