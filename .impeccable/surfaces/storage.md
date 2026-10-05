# Shared storage

Mode: Operate. Inherits Hoard's charcoal surfaces, serif application name,
system UI text, restrained accent and local fonts. Backend/file-path behavior
is the authority; all demonstration content is synthetic.

The optional organization/interface questions remained unanswered during
backend work. Defaults follow the explicit shared-disk brief. Grounded
structures: (1) projects rail and file table, (2) project folder explorer,
(3) native Hoard folders, (4) deliverable dependencies, (5) recent edits,
(6) shared files first, (7) project creation workspace. Surface roll dealt
6, 3, 2; default 6 directly proves the user's shared PNG example. No replacement
visual identity; code-led extension of the family's existing file-management UI.

## Direction contract

THESIS: One real file, one visible path, available to every project member.

OWN-WORLD: Existing Hoard charcoal theme; serif name, system controls, ruled
file rows, familiar folder navigation. No remote fonts or decorative assets.

STORY: Select a project, see its shared/native folders, copy the path and
register a file saved there. Existing files remain usable in native tools.

FIRST VIEWPORT: Compact app header; secondary projects rail; shared-folder
path and copy action above a full-width file table. Inline project/file forms.

FORM: Shared files first, candidate 6, seed 39bcbe65; responsive file explorer.

FINISH: The implemented surface received a finish review with a ship disposition.
The scoped navigation-race finding was resolved. Root DESIGN.md records the
actual inherited world; this surface brief records its task behavior and
extensions. No raster assets ship in the UI.

## Built surface

The compact header exposes Nuevo proyecto. On desktop, a 250px projects rail
precedes a flexible working column. Project selection opens Compartidos first;
each project member has a separate native-folder button. The exact selected
folder path occupies a dark strip with Copiar ruta. A ruled semantic table
shows file name, relative path, registering app and a per-file path action.
The member list and shared-original explanation follow the table.

This is a local shared live filesystem, not a cloud library. A PNG remains at
one unchanged native filesystem path, usable from ordinary native applications.
Registration records a file already saved in the project and does not rewrite
its contents. Project/native app directories remain ordinary folders. No UI
action silently migrates existing projects; BookHoard and WatchHoard remain
independent. Sample projects and files in review screenshots are synthetic,
explicitly labelled demonstration data, never product defaults.

Creating a project opens an inline form above the workspace. Registering a
file opens an inline form within the current file area. Copy failure gives a
manual select-and-copy instruction. Empty and missing-file states explain the
next concrete action. Project loading replaces the stale workspace, marks it
busy and clears the active project; request generation and selected-project
checks prevent a late response from replacing the newest selection. A failed
load invites the user to select that project again. Submission buttons wait
while their request is in progress. Status feedback uses a polite live region.

## Surface extensions

These measurements describe this explorer; they do not prescribe every Atlas
surface. The inherited Hoard token definitions remain authoritative.

- Desktop: 32px main insets, 250px rail, 24px between title and folder controls.
- At max-width 760px: project navigation moves above the main area and can
  scroll horizontally; disk-root metadata hides; main insets become 20px;
  folder controls wrap; forms become one column. Table attribution hides while
  file identity and Copiar ruta remain visible. Normal document scrolling stays.
- Controls use the inherited 6px corner radius; project forms use 8px.
  Path strips and ruled file rows remain square. The surface applies no shadows.
- Focus: 2px accent outline, 3px offset on controls. Project selection uses
  accent-soft fill and accent-line stroke; folder selection uses accent stroke
  and accent-strong text. Preserve aria-current and aria-pressed respectively.
- Motion: background-color and border-color transitions of .12s ease-out only
  under prefers-reduced-motion: no-preference. No layout-motion requirement.
- Paths: inherited monospace at 12px, overflow-wrap:anywhere, user-select:all.
  File names also wrap. Numeric table content uses tabular figures.
- Error feedback currently uses #f3b3ad text on #321f1e. This is a local error
  state recipe, not a new global brand palette. Missing-file notices and archived
  project text use the inherited warning role.
- Imagery: no decorative or shipping raster assets; file marks are inline SVG.

## Evidence and review scope

The source authority is atlas_hoard/ui/index.html, style.css and app.js, with
atlas_hoard/hoard_link/ui/hoard-theme.css loaded first. There is no dedicated
Atlas palette selector in the inherited theme; its root charcoal/parchment
palette applies. No approved image comp exists, and no comp-fidelity claim is
made. No new global identity or metaphor is approved by this extraction.

The recorded surface roll is seed 39bcbe65, dealt indices 6, 3, 2; candidate 6
leads the actual shared-files-first structure. The roll evidence is
.impeccable/review/concept-roll.txt. Challenger imagery and unrelated visual
worlds were not adopted into the built theme.

Final direct browser review images are .impeccable/review/desktop.jpg
(actual 1366x1000), mobile.jpg (390x1200) and user-1280.jpg (1280x900).
The desktop file's actual width takes precedence over the older 1440px capture
description in storage-quality.md. These are review evidence, not shipped
raster assets. The finish reviewer matched the visual surface before the scoped
navigation-race correction, then confirmed that fix and issued a ship verdict.
The detector was degraded to regex-only scanning; computed CSS and contrast
were not tested, so this record makes no contrast certification.

Not canonized: synthetic demonstration facts, dormant shared-theme components,
unused shadow values, speculative palettes, challenger aesthetics and one-off
review data. They are not evidence of durable Atlas defaults.
