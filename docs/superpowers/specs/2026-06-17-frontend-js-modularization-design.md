# Frontend JS Modularization (Option B)

## Goal

`index.html` currently embeds a single 2147-line `<script>` block (no modules,
no build step) containing ~150 functions and ~20 module-level `let`/`const`
state variables. Split this into multiple native ES module files under a new
`js/` directory so the code is organized by feature area, without changing
any behavior, output, styling, or interaction, and without introducing any
build tooling.

## Non-goals

- No React, Vue, or any UI framework
- No Vite, webpack, esbuild, or any bundler
- No npm/Node dependency of any kind
- No test framework
- No changes to `server.py`
- No behavior, copy, styling, or interaction changes of any kind — this is a
  pure structural refactor

## Why no backend changes are needed

`server.py`'s `Handler.do_GET` only intercepts specific `/api/*` paths; every
other path falls through to `SimpleHTTPRequestHandler`'s default static file
serving via the existing `translate_path` override (which resolves any
relative path under `ROOT`). Requesting `/js/main.js` will resolve to
`ROOT/js/main.js` and be served with a correct JavaScript MIME type
automatically. No route or handler changes required.

## Pre-migration inventory (required first step)

Before moving any code, produce a complete inventory of:

1. Every top-level function name declared in the current `<script>` block
2. Every top-level `let`/`const` module-level state variable
3. Every function name referenced via inline `onclick=`/`onchange=`/`oninput=`
   attributes — both in static HTML markup and inside JS template-literal
   strings that get injected via `innerHTML`

This inventory is the checklist used to verify nothing is dropped when
writing `import`/`export` statements across the new files. A first pass
already identified the onclick-invoked set (20 functions) and the top-level
state variables (~20), but the full enumeration must be re-verified
immediately before the split, against the actual current file, not against
this design doc, since the file may have moved on by then.

## Target module layout

All files live under `js/`, loaded from `index.html` via:

```html
<script type="module" src="js/main.js"></script>
```

replacing the current inline `<script>...</script>` block.

| File | Responsibility |
| --- | --- |
| `state.js` | Shared mutable state (`matches`, `activeView`, `simAccount`, `calc*`, etc.) and the `scheduleMatch`/fixture data that seeds it |
| `utils.js` | Generic helpers: `escapeHtml`, date formatting (`cnDate`/`cnDateTime`), odds math (`americanToDecimal`, `probsFromDecimal`, etc.) |
| `odds-feed.js` | Sporttery data ingestion, parsing, odds trend rendering |
| `calculator.js` | Parlay ticket calculator (largest single area, ~700 lines today) |
| `simulation.js` | Simulated funding account, bet simulation, ledger rendering |
| `llm.js` | LLM bet history, auto-bet plan application, post-game review rendering |
| `view.js` | View/tab switching, results page rendering and pagination, top-level `render()` |
| `main.js` | Entry point: imports from the above, re-attaches the ~20 onclick-invoked functions to `window`, and runs the bottom-of-script init code (event listener wiring, `loadResults()`, `boot()`) |

Module boundaries follow the functional clusters already visible in the
current code (grep'd by function name prefix/purpose), not an idealized
redesign — the point is to mirror existing structure into separate files,
not to redesign responsibilities.

## State sharing mechanism

`state.js` exports its `let` bindings directly (e.g. `export let activeView
= 'predictions'`). ES module bindings are live: when one module assigns to
an imported `let` binding it owns, every other module that imported that
binding observes the updated value immediately. This preserves today's
"implicit shared globals" behavior exactly, without introducing a state
container, store, or pub/sub mechanism — that would be a behavior-risking
redesign, not a refactor.

Each module imports only the specific names it actually uses from
`state.js`/`utils.js`, making today's implicit dependencies explicit in the
`import` statements.

## window exposure for inline HTML handlers

`index.html` markup (static and dynamically generated via `innerHTML`)
invokes ~20 functions through inline `onclick=` attributes (e.g.
`toggleSimPanel`, `loadResults`, `selectCalculatorMarket`,
`toggleCalculatorCandidate`, `setResultsPage`, ...). Top-level functions
declared inside an ES module are not implicitly global, so `main.js` must
explicitly assign each of these to `window` after importing it (e.g.
`window.toggleSimPanel = toggleSimPanel;`). This is the only intentional
global surface area introduced by the migration; every other function
becomes module-private unless another module explicitly imports it.

## Migration approach

Single-pass move, not incremental per-function changes: the functions are
heavily interdependent (shared state, shared DOM IDs, call into each other
across what will become module boundaries), so a partially-migrated state
would leave the page non-functional. The work is a verbatim cut of existing
code into the new files plus the `import`/`export` plumbing — no logic
changes, no formatting churn beyond what's needed to add module syntax.

## Verification

No automated frontend test suite exists today (no `package.json`, no test
framework) and none is introduced by this refactor. Verification is manual.

Deliverable: after the split, produce a verification checklist enumerating
every page/view and every interactive control that needs manual
click-through, with special attention to the 20 onclick-bound functions
(since those are the ones most likely to silently break if `window`
exposure is missed). The checklist is handed to the user (or driven via
browser automation if available at that time) to confirm the refactored
page behaves identically to the pre-refactor page.
