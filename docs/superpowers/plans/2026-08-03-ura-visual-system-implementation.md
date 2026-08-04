# URA Visual System Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Re-skin the existing internal transaction application into an URA-aligned enterprise visual system using the approved blue/yellow palette and Gotham-first typography without changing application behavior.

**Architecture:** Keep the existing HTML structure, navigation, forms, drawers, tables, and Dashboard information architecture. Implement the redesign primarily in `app/static/css/app.css`, using explicit URA design tokens and semantic status tokens. Only touch templates/JavaScript if a class hook is genuinely required; the current code already exposes the classes needed for the approved redesign.

**Tech Stack:** FastAPI/Jinja shell, vanilla JavaScript, CSS, pytest, Python 3.9. No CSS framework, React, npm, font package, or public CDN dependency.

## Global Constraints

- Primary brand blue: `#1850A1`.
- Secondary blue: `#5287C1`.
- Primary brand yellow: `#FDF22C`.
- Soft yellow surface: `#FCF59A`.
- Muted yellow hover: `#F0E964`.
- Main pale surface: `#E2E9F0`.
- Pale blue surface: `#B1C6E0`.
- Muted olive: `#BFB86A` and use only sparingly.
- Primary text: `#212529`; secondary text: `#4B4C4D`; cards/surfaces: `#FFFFFF`.
- Sidebar is solid `#1850A1`; active navigation is `#FDF22C` with dark text.
- Primary task buttons are URA yellow with dark text; secondary buttons are white with URA blue border/text.
- Semantic status colours remain separate from brand colours: successful green, pending amber, reversed/error red, healthy green.
- Preferred font stack starts with `"Gotham-Book"` and falls back to system fonts; do not add, package, download, or redistribute Gotham font files.
- Keep the approved Dashboard information architecture unchanged.
- Keep operational behavior, APIs, Oracle/CDC/Kafka/ClickHouse/Power BI integration, navigation structure, and form workflows unchanged.
- Do not add a URA logo, Font Awesome CDN, CSS framework, React, npm, or any public CDN dependency.
- Preserve readable focus, hover, active, disabled, and semantic action states.
- Dark text on yellow; white text on `#1850A1`.

---

### Task 1: Establish URA design tokens, typography, and application shell

**Files:**
- Create: `tests/test_ura_visual_contracts.py`
- Modify: `app/static/css/app.css`

**Interfaces:**
- Consumes: existing global selectors (`:root`, `body`, `.sidebar`, `.nav-item`, `.topbar`, `.avatar`, `.eyebrow`).
- Produces: canonical URA CSS variables and Gotham-first typography that all later styling tasks reuse.

- [ ] **Step 1: Write failing visual token tests**

Create `tests/test_ura_visual_contracts.py`:

```python
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CSS_PATH = ROOT / "app/static/css/app.css"


def css_text():
    return CSS_PATH.read_text()


def compact(value: str) -> str:
    return "".join(value.split()).lower()


def test_ura_brand_tokens_are_source_of_truth():
    css = compact(css_text())

    assert "--ura-blue:#1850a1" in css
    assert "--ura-blue-2:#5287c1" in css
    assert "--ura-yellow:#fdf22c" in css
    assert "--ura-yellow-soft:#fcf59a" in css
    assert "--ura-yellow-hover:#f0e964" in css
    assert "--ura-surface:#e2e9f0" in css
    assert "--ura-blue-soft:#b1c6e0" in css
    assert "--text:#212529" in css
    assert "--muted:#4b4c4d" in css


def test_gotham_first_font_stack_has_system_fallbacks_without_font_face():
    css = css_text()
    normalized = compact(css)

    assert 'font-family:"gotham-book",system-ui,-apple-system,"segoeui",arial,helvetica,sans-serif' in normalized
    assert "@font-face" not in css.lower()


def test_sidebar_and_active_navigation_use_ura_brand_colours():
    css = compact(css_text())

    sidebar = css.split(".sidebar{", 1)[1].split("}", 1)[0]
    active = css.split(".nav-item.active{", 1)[1].split("}", 1)[0]

    assert "background:var(--ura-blue)" in sidebar
    assert "background:var(--ura-yellow)" in active
    assert "color:var(--text)" in active
```

- [ ] **Step 2: Run the focused tests and verify RED**

Run:

```bash
python -m pytest tests/test_ura_visual_contracts.py -v
```

Expected before implementation: failures because the current stylesheet still uses `--navy`, `--yellow`, the navy gradient sidebar, and the `Inter`-first font stack.

- [ ] **Step 3: Replace legacy global colour variables with URA tokens**

At the top of `app/static/css/app.css`, replace the existing `:root` block with:

```css
:root{
  --ura-blue:#1850A1;
  --ura-blue-2:#5287C1;
  --ura-yellow:#FDF22C;
  --ura-yellow-soft:#FCF59A;
  --ura-yellow-hover:#F0E964;
  --ura-surface:#E2E9F0;
  --ura-blue-soft:#B1C6E0;
  --ura-olive:#BFB86A;
  --surface:#FFFFFF;
  --text:#212529;
  --muted:#4B4C4D;
  --border:#D5DFE9;
  --success:#15803D;
  --success-hover:#166534;
  --warning:#B45309;
  --danger:#B91C1C;
  --danger-hover:#991B1B;
  --radius:14px;
}
```

Do not preserve `--navy`, `--navy-2`, `--yellow`, or `--yellow-hover` as aliases. Later tasks must use the URA/semantic tokens directly so the old palette is no longer the visual source of truth.

- [ ] **Step 4: Apply Gotham-first typography and URA workspace surface**

Replace the current body rule with:

```css
*{box-sizing:border-box}
body{
  margin:0;
  font-family:"Gotham-Book",system-ui,-apple-system,"Segoe UI",Arial,Helvetica,sans-serif;
  background:#F5F8FB;
  color:var(--text);
  font-size:15px;
  font-weight:400;
}
```

Keep `button,input,select{font:inherit}` immediately after the body rule.

- [ ] **Step 5: Re-style the sidebar, brand area, navigation, and top bar**

Use these exact shell rules as the design baseline:

```css
.sidebar{
  background:var(--ura-blue);
  color:#fff;
  padding:26px 18px 20px;
  display:flex;
  flex-direction:column;
  position:sticky;
  top:0;
  height:100vh;
}
.brand-text{padding:0 10px 24px}
.brand-text strong{display:block;font-size:19px;font-weight:600}
.brand-kicker{font-size:10px;letter-spacing:.16em;color:var(--ura-yellow);font-weight:600}
.nav-list{display:flex;flex-direction:column;gap:4px}
.nav-section{font-size:10px;letter-spacing:.12em;color:#D6E3F2;margin:20px 10px 7px;font-weight:600}
.nav-item{
  border:0;
  background:transparent;
  color:#F3F7FC;
  padding:11px 12px;
  border-radius:8px;
  text-align:left;
  cursor:pointer;
  display:flex;
  gap:11px;
  align-items:center;
  font-weight:500;
  font-size:14px;
}
.nav-item:hover{background:rgba(255,255,255,.12);color:#fff}
.nav-item.active{background:var(--ura-yellow);color:var(--text)}
.topbar{
  height:92px;
  background:#fff;
  border-bottom:1px solid var(--border);
  display:flex;
  justify-content:space-between;
  align-items:center;
  padding:0 34px;
}
.topbar h1{margin:2px 0 0;font-size:27px;font-weight:600;color:var(--text)}
.eyebrow{margin:0;font-size:11px;color:var(--ura-blue);text-transform:uppercase;letter-spacing:.1em;font-weight:600}
.avatar{width:38px;height:38px;border-radius:50%;display:grid;place-items:center;background:var(--ura-blue);color:#fff;font-weight:600}
```

Retain existing layout/grid behavior and `.workspace`, `.user-chip`, and `.content` structure.

- [ ] **Step 6: Run focused token/shell tests**

```bash
python -m pytest tests/test_ura_visual_contracts.py -v
```

Expected: all Task 1 tests pass.

- [ ] **Step 7: Commit Task 1**

```bash
git add app/static/css/app.css tests/test_ura_visual_contracts.py
git commit -m "style: establish URA visual tokens and shell"
```

---

### Task 2: Re-style operational components, forms, tables, and drawers

**Files:**
- Modify: `tests/test_ura_visual_contracts.py`
- Modify: `app/static/css/app.css`

**Interfaces:**
- Consumes: URA tokens from Task 1 and existing operational classes (`.btn`, `.btn-primary`, `.btn-success`, `.btn-danger`, `.input`, `.select`, `table`, `.link-btn`, `.badge-*`, `.drawer`, `.detail`).
- Produces: consistent URA operational UI without changing markup or JavaScript behavior.

- [ ] **Step 1: Add failing operational component contract tests**

Append:

```python
def test_primary_and_secondary_actions_follow_ura_roles():
    css = compact(css_text())

    primary = css.split(".btn-primary{", 1)[1].split("}", 1)[0]
    secondary = css.split(".btn{", 1)[1].split("}", 1)[0]

    assert "background:var(--ura-yellow)" in primary
    assert "color:var(--text)" in primary
    assert "border-color:var(--ura-yellow)" in primary
    assert "background:#fff" in secondary
    assert "color:var(--ura-blue)" in secondary
    assert "border:1pxsolidvar(--ura-blue)" in secondary


def test_semantic_actions_remain_green_and_red():
    css = compact(css_text())

    success = css.split(".btn-success{", 1)[1].split("}", 1)[0]
    danger = css.split(".btn-danger{", 1)[1].split("}", 1)[0]

    assert "background:var(--success)" in success
    assert "color:#fff" in success
    assert "color:var(--danger)" in danger


def test_forms_tables_and_links_use_ura_blue_system():
    css = compact(css_text())

    assert ".input:focus,.select:focus" in css
    focus = css.split(".input:focus,.select:focus{", 1)[1].split("}", 1)[0]
    assert "border-color:var(--ura-blue-2)" in focus
    assert ".link-btn" in css
    link = css.split(".link-btn{", 1)[1].split("}", 1)[0]
    assert "color:var(--ura-blue)" in link
```

- [ ] **Step 2: Run the new tests and verify RED**

```bash
python -m pytest tests/test_ura_visual_contracts.py -v
```

Expected before Task 2 implementation: failures because the current button/link/focus rules still use generic borders, navy-era values, and heavier weights.

- [ ] **Step 3: Apply URA button hierarchy while preserving semantic controls**

Replace the generic button section with:

```css
.btn{
  border:1px solid var(--ura-blue);
  background:#fff;
  color:var(--ura-blue);
  padding:10px 15px;
  border-radius:8px;
  font-weight:500;
  cursor:pointer;
  transition:background .15s ease,border-color .15s ease,color .15s ease,box-shadow .15s ease;
}
.btn:hover{background:#F0F5FA;border-color:var(--ura-blue-2)}
.btn:disabled{opacity:.55;cursor:not-allowed}
.btn-primary{background:var(--ura-yellow);border-color:var(--ura-yellow);color:var(--text);font-weight:600}
.btn-primary:hover{background:var(--ura-yellow-hover);border-color:var(--ura-yellow-hover);color:var(--text)}
.btn-danger{color:var(--danger);border-color:#F0B9B9;background:#FFF8F8}
.btn-danger:hover{color:#fff;border-color:var(--danger-hover);background:var(--danger-hover)}
.btn-success{color:#fff;background:var(--success);border-color:var(--success)}
.btn-success:hover{color:#fff;background:var(--success-hover);border-color:var(--success-hover)}
```

- [ ] **Step 4: Re-style fields, focus rings, links, tables, and operational cards**

Use:

```css
.page-head h2{margin:0 0 7px;font-size:23px;font-weight:600;color:var(--text)}
.page-head p{margin:0;color:var(--muted)}
.kpi-card{background:#fff;border:1px solid var(--border);border-radius:var(--radius);padding:18px 20px;box-shadow:0 2px 7px rgba(24,80,161,.04)}
.kpi-card span{color:var(--muted);font-size:12px;font-weight:500}
.kpi-card strong{display:block;font-size:25px;font-weight:600;margin-top:8px;color:var(--ura-blue)}
.kpi-card small{color:#6E7781}
.panel{background:#fff;border:1px solid var(--border);border-radius:var(--radius);box-shadow:0 2px 7px rgba(24,80,161,.04);overflow:hidden}
.input,.select{width:100%;border:1px solid #C9D6E3;border-radius:8px;padding:10px 12px;background:#fff;color:var(--text);outline:none}
.input:focus,.select:focus{border-color:var(--ura-blue-2);box-shadow:0 0 0 3px rgba(82,135,193,.18)}
th{background:#F0F5FA;text-transform:uppercase;letter-spacing:.05em;font-size:11px;font-weight:600;color:#5A6570;text-align:left;padding:12px 16px;border-bottom:1px solid var(--border)}
td{padding:14px 16px;border-bottom:1px solid #E7EDF3;font-size:13px}
tr:hover td{background:#F5F8FC}
.money{font-weight:600}
.muted{color:var(--muted)}
.link-btn{border:0;background:none;color:var(--ura-blue);font-weight:600;cursor:pointer;padding:0}
```

Keep badge background/text semantics green/amber/red. Lower badge font weight from the current heavy setting to `600`.

- [ ] **Step 5: Re-style drawers and detail tiles**

Use:

```css
.drawer{position:fixed;top:0;right:0;height:100vh;width:min(460px,95vw);background:#fff;z-index:30;transform:translateX(100%);transition:.22s ease;box-shadow:-14px 0 40px rgba(24,80,161,.14);padding:26px;overflow:auto}
.drawer-head h3{margin:0;color:var(--ura-blue);font-weight:600}
.close-btn{border:0;background:#EEF3F8;color:var(--ura-blue);width:34px;height:34px;border-radius:50%;cursor:pointer}
.field label{display:block;font-size:13px;font-weight:500;color:var(--muted);margin-bottom:7px}
.detail{padding:13px;background:#F1F5F9;border:1px solid #E2E9F0;border-radius:9px}
.detail span{display:block;color:var(--muted);font-size:11px}
.detail strong{display:block;margin-top:5px;font-weight:600;color:var(--text)}
```

Do not alter drawer markup or form submission code.

- [ ] **Step 6: Run Task 2 tests**

```bash
python -m pytest tests/test_ura_visual_contracts.py -v
```

Expected: all visual contract tests pass through Task 2.

- [ ] **Step 7: Commit Task 2**

```bash
git add app/static/css/app.css tests/test_ura_visual_contracts.py
git commit -m "style: align operational UI with URA design system"
```

---

### Task 3: Re-style the approved Dashboard with URA brand roles

**Files:**
- Modify: `tests/test_ura_visual_contracts.py`
- Modify: `app/static/css/app.css`
- Inspect only: `app/static/js/dashboard.js`

**Interfaces:**
- Consumes: existing Dashboard markup/classes emitted by `DashboardPage` and the URA tokens established in Task 1.
- Produces: URA blue/yellow KPI/card/bar styling while keeping semantic donut status colours unchanged.

- [ ] **Step 1: Add failing Dashboard visual contract tests**

Append:

```python
def test_dashboard_uses_ura_brand_for_kpis_and_station_bars():
    css = compact(css_text())

    amount = css.split(".dashboard-kpi-money{", 1)[1].split("}", 1)[0]
    bar = css.split(".dashboard-bar{", 1)[1].split("}", 1)[0]
    primary_bar = css.split(".dashboard-bar-primary{", 1)[1].split("}", 1)[0]

    assert "background:var(--ura-blue)" in amount
    assert "fill:var(--ura-blue)" in bar
    assert "fill:var(--ura-yellow)" in primary_bar


def test_dashboard_status_donut_remains_semantic():
    css = compact(css_text())

    assert ".donut-successful{stroke:var(--success)}" in css
    assert ".donut-pending{stroke:var(--warning)}" in css
    assert ".donut-reversed{stroke:var(--danger)}" in css
```

- [ ] **Step 2: Run the Dashboard contract tests and verify RED**

```bash
python -m pytest tests/test_ura_visual_contracts.py -v
```

Expected before Task 3 implementation: failures because Dashboard still references the legacy navy/yellow variables and pending donut currently shares the brand yellow token.

- [ ] **Step 3: Re-style Dashboard KPI cards**

Use these baseline rules:

```css
.dashboard-kpi-card{position:relative;overflow:hidden;background:#fff;border:1px solid var(--border);border-radius:16px;padding:24px 24px 22px;min-height:154px;box-shadow:0 7px 20px rgba(24,80,161,.07)}
.dashboard-kpi-accent{position:absolute;left:0;top:0;bottom:0;width:5px;background:var(--ura-blue)}
.dashboard-kpi-card:nth-child(3) .dashboard-kpi-accent{background:var(--ura-yellow)}
.dashboard-kpi-money{background:var(--ura-blue);border-color:var(--ura-blue);color:#fff;box-shadow:0 10px 26px rgba(24,80,161,.2)}
.dashboard-kpi-money .dashboard-kpi-accent{background:var(--ura-yellow);width:6px}
.dashboard-kpi-money .dashboard-kpi-label,.dashboard-kpi-money small{color:#E2E9F0}
.dashboard-kpi-money .dashboard-kpi-value{color:#fff}
.dashboard-kpi-label{display:block;color:var(--muted);font-size:11px;letter-spacing:.08em;font-weight:600}
.dashboard-kpi-value{display:block;margin:18px 0 7px;font-size:34px;line-height:1;font-weight:600;letter-spacing:-.02em;color:var(--ura-blue)}
.dashboard-kpi-card small{color:#6E7781;font-size:12px}
.dashboard-kpi-money .dashboard-kpi-value{font-size:36px}
```

- [ ] **Step 4: Re-style Dashboard panels, bars, labels, and activity accents**

Use:

```css
.dashboard-panel{background:#fff;border:1px solid var(--border);border-radius:16px;box-shadow:0 4px 16px rgba(24,80,161,.06);overflow:hidden}
.dashboard-panel-head{display:flex;justify-content:space-between;gap:16px;align-items:flex-start;padding:20px 22px 15px;border-bottom:1px solid #E7EDF3}
.dashboard-panel-head h3{margin:4px 0 0;font-size:18px;font-weight:600;color:var(--text)}
.dashboard-panel-note{font-size:11px;color:var(--ura-blue);background:#F0F5FA;border:1px solid #D8E3EE;padding:6px 8px;border-radius:999px}
.chart-label{font-size:12px;fill:#3F4852;font-weight:500}
.chart-value{font-size:11px;fill:#64707D;font-weight:600}
.dashboard-bar-track{fill:#E8EEF4}
.dashboard-bar{fill:var(--ura-blue)}
.dashboard-bar-primary{fill:var(--ura-yellow)}
.activity-marker{width:10px;height:10px;border-radius:50%;margin-top:5px;background:var(--ura-yellow);box-shadow:0 0 0 4px var(--ura-yellow-soft)}
.activity-action{display:block;color:var(--ura-blue);font-weight:600;font-size:12px;margin-top:3px}
```

- [ ] **Step 5: Decouple pending status from brand yellow**

Change Dashboard semantic rules to:

```css
.donut-successful{stroke:var(--success)}
.donut-pending{stroke:var(--warning)}
.donut-reversed{stroke:var(--danger)}
.dot-successful{background:var(--success)}
.dot-pending{background:var(--warning)}
.dot-reversed{background:var(--danger)}
```

Keep `.badge-pending` amber-based as well; do not use `var(--ura-yellow)` for semantic pending status.

- [ ] **Step 6: Inspect `dashboard.js` for hard-coded colour values**

Run:

```bash
grep -nE '#[0-9A-Fa-f]{3,6}|rgb\(' app/static/js/dashboard.js || true
```

Expected: no chart colour constants requiring JavaScript edits because colours are supplied via CSS classes. If the command returns no lines, leave `dashboard.js` unchanged.

- [ ] **Step 7: Run Dashboard contract tests**

```bash
python -m pytest tests/test_ura_visual_contracts.py -v
```

Expected: all visual contract tests pass through Task 3.

- [ ] **Step 8: Commit Task 3**

```bash
git add app/static/css/app.css tests/test_ura_visual_contracts.py
git commit -m "style: apply URA brand roles to dashboard"
```

Do not add `dashboard.js` to this commit unless Step 6 proves a hard-coded colour must be changed.

---

### Task 4: Accessibility, focus, responsive polish, and dead-style cleanup

**Files:**
- Modify: `tests/test_ura_visual_contracts.py`
- Modify: `app/static/css/app.css`
- Inspect: `app/templates/index.html`

**Interfaces:**
- Consumes: all styling produced by Tasks 1–3.
- Produces: explicit focus-visible states, readable hover states, preserved responsive breakpoints, and removal of obsolete POC-footer styling.

- [ ] **Step 1: Add failing accessibility/cleanup tests**

Append:

```python
def test_keyboard_focus_is_visible_on_actions_and_navigation():
    css = compact(css_text())

    assert ".btn:focus-visible" in css
    assert ".nav-item:focus-visible" in css
    assert ".link-btn:focus-visible" in css
    assert "outline:" in css.split(".btn:focus-visible", 1)[1].split("}", 1)[0]


def test_obsolete_poc_footer_styles_are_removed():
    css = css_text()

    assert ".sidebar-footer" not in css


def test_legacy_palette_variables_are_absent():
    css = compact(css_text())

    assert "--navy:" not in css
    assert "--navy-2:" not in css
    assert "--yellow:" not in css
    assert "--yellow-hover:" not in css
```

- [ ] **Step 2: Run focused tests and verify RED**

```bash
python -m pytest tests/test_ura_visual_contracts.py -v
```

Expected before Task 4 implementation: failures for missing `:focus-visible` rules and dead `.sidebar-footer` responsive/style remnants.

- [ ] **Step 3: Add explicit keyboard focus styles**

Add:

```css
.btn:focus-visible,
.nav-item:focus-visible,
.link-btn:focus-visible,
.close-btn:focus-visible{
  outline:3px solid var(--ura-blue-2);
  outline-offset:2px;
}
.input:focus-visible,
.select:focus-visible{
  outline:0;
}
```

Keep the existing `.input:focus,.select:focus` blue border/ring so keyboard and mouse focus both remain visible.

- [ ] **Step 4: Remove obsolete footer/dead palette styling**

Delete any `.sidebar-footer` rule and the `.sidebar-footer div` fragment inside responsive media queries. Keep `.environment-dot` because Dashboard refresh status still uses it.

Search to confirm:

```bash
grep -nE 'sidebar-footer|--navy|--yellow:' app/static/css/app.css || true
```

Expected after cleanup: no matches for `sidebar-footer`, `--navy`, `--navy-2`, or legacy `--yellow:` token definitions.

- [ ] **Step 5: Preserve responsive behavior using the current breakpoints**

Retain the existing conceptual breakpoints at `1100px`, `900px`, and `620px`. Update only selectors/values required by the new visual system. The `900px` block should continue to collapse the sidebar to `78px`, and the `620px` block should continue to collapse KPI grids and drawer detail grids.

Use the `900px` rule without the removed footer selector:

```css
@media(max-width:900px){
  .app-shell{grid-template-columns:78px 1fr}
  .brand-text strong,.brand-kicker,.nav-item:not(.active){font-size:0}
  .nav-item span{font-size:16px}
  .nav-section{display:none}
  .kpi-grid{grid-template-columns:1fr 1fr}
  .content{padding:22px}
  .topbar{padding:0 22px}
  .dashboard-head{align-items:flex-start;flex-direction:column}
  .dashboard-refresh{align-self:flex-start}
}
```

Keep the `1100px` and `620px` layout logic functionally unchanged.

- [ ] **Step 6: Verify template has no external font/icon CDN or new logo dependency**

Run:

```bash
grep -nEi 'fonts\.googleapis|fontawesome|cdnjs|unpkg|jsdelivr|<img' app/templates/index.html || true
```

Expected: no newly introduced public CDN/font dependencies and no logo image added by this redesign.

- [ ] **Step 7: Run all visual contracts**

```bash
python -m pytest tests/test_ura_visual_contracts.py -v
```

Expected: PASS.

- [ ] **Step 8: Run the complete Python suite**

```bash
python -m pytest -v
```

Expected: zero failures. Record the actual test count rather than assuming one.

- [ ] **Step 9: Run syntax checks**

```bash
python -m compileall -q app
node --check app/static/js/app.js
node --check app/static/js/dashboard.js
node --check app/static/js/payments.js
node --check app/static/js/taxpayers.js
node --check app/static/js/stations.js
```

If Node is not installed on the RHEL host, record that and perform browser-console verification instead; do not add npm or Node as a project dependency merely for this check.

- [ ] **Step 10: Commit Task 4**

```bash
git add app/static/css/app.css tests/test_ura_visual_contracts.py
git commit -m "style: polish URA accessibility and responsive states"
```

---

## Host Visual Verification

After pulling the implementation on `datalake-test02`:

```bash
cd /home/jkasule/cdc-clickhouse-poc
source /home/jkasule/kjt/venv/bin/activate
git pull
python -m pytest -v
```

Start/restart Uvicorn using the existing environment and open the application in a desktop browser.

Verify each screen deliberately:

1. **Shell:** sidebar is solid URA blue `#1850A1`; active item is bright yellow `#FDF22C` with dark text; inactive nav remains readable.
2. **Typography:** browser computed style uses `Gotham-Book` when available, otherwise the system fallback; no font download request occurs.
3. **Top bar:** white background, URA blue eyebrow and avatar, restrained 600-weight hierarchy.
4. **Payments:** primary task action is yellow/dark; Mark Successful remains green; Reverse Payment remains red; hover states remain readable.
5. **Taxpayers/Stations:** white operational panels, blue links, pale blue-grey table headers/row hover, yellow create/save actions.
6. **Forms/Drawers:** white inputs, blue focus rings, grey-blue detail tiles, URA blue titles, semantic destructive controls unchanged.
7. **Dashboard:** Amount Collected card is URA blue with white text/yellow accent; regular KPI cards are white; station bars are URA blue with only the leader highlighted yellow.
8. **Status donut:** successful green, pending amber, reversed red; labels remain present so colour is not the only status cue.
9. **Keyboard:** Tab through nav, buttons, links, form fields, and drawer close controls; focus is always visible.
10. **Responsive:** inspect around 900px and 620px widths; no new horizontal overflow appears outside table wrappers.

## Regression Guardrails

The redesign must not change:

```text
/api/payments
/api/taxpayers
/api/stations
/api/dashboard/*
payment status transitions
Oracle writes
CDC behavior
ClickHouse queries
Dashboard polling
navigation destinations
form field names or submitted payloads
```

If any browser verification exposes a layout bug that requires markup changes, make the smallest possible class-hook change and add a contract test that would fail without that class. Do not broaden the redesign into a template or JavaScript refactor.
