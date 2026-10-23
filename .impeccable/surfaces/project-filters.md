# Project filters

Primary target: atlas_hoard/ui/app.js. Related: ui/index.html, ui/style.css.
Mode: Operate. Narrow refinement of the inherited Atlas workspace; PRODUCT,
DESIGN and storage.md remain authoritative, including charcoal/parchment and
Spanish text. No imagery, palette replacement, new dependency or visual world.

The existing project rail gains a labelled name/goal search, state/sphere native
selects, Filter/Clear actions and polite result/loading/error feedback. Desktop
uses the250px rail and stacked fields; below760px the rail remains above the
workspace and filters use two columns with full-width query/actions. Existing
horizontal project navigation and document scrolling remain. Fields/notes wrap,
buttons keep42px touch target,13px metadata matches existing explanatory controls.

Filters affect only project navigation. The open project stays open with drafts;
an explicit notice identifies it when hidden by the filters. Search invokes native
atlas_projects with case/accent-insensitive all-word name/goal matching, state and
sphere. Debounced typing, generation checks, error/Retry and Clear do not replace
the project editor. Copilot context captures active filters before its first await.

The native operation lists all accessible matching metadata; former global1000
cutoff removed before access/filtering. No file-content search or filesystem scan,
model, permission expansion, new API shape or MCP count. Preview/demo examples
are fictional fixtures only. Mechanical detector is regex-only DEGRADED: advisory
font sizes13/14/16 match incumbent typography documented in DESIGN prose; no claim
of computed contrast from the detector. Build pipeline absent by design: assets
ship directly, Python/JS syntax and normal native server are the shipping path.

Verification/evidence: C:/Users/luism/.codex/scratch/hoard-loop23/atlasprojects23/.
Existing32tests passed once before the added focused cutoff regression1PASS; final
context capture checked separately. Native SDK14 and HTTP8cases match; all five
fixture SQL tables exact. SDK2 changed Python attribute names; the initial harness
failure and corrected native receipt are retained, with no product workaround.
