# URA Visual System Redesign

## Goal

Refine the existing internal transaction application so that it feels recognizably aligned with Uganda Revenue Authority visual identity while preserving the approved information architecture, business workflows, and dashboard structure.

The redesign is a visual-system change, not a functional rewrite.

## Design Direction

Use an **URA enterprise system** interpretation rather than copying the public website literally.

The application should combine:

- strong URA blue for structure and navigation,
- vivid URA yellow for active states and primary emphasis,
- pale blue-grey surfaces for institutional clarity,
- white operational cards and forms,
- restrained typography based on Gotham where available,
- existing semantic colours for operational status.

The result should feel like an internal URA operations platform rather than a generic SaaS dashboard or a public-facing marketing site.

## Palette

The supplied URA palette is the source palette for the redesign:

```text
#FDF22C  URA vivid yellow
#1850A1  URA primary blue
#E2E9F0  pale blue-grey
#5287C1  secondary blue
#FCF59A  soft yellow
#F0E964  muted yellow
#B1C6E0  pale blue
#BFB86A  muted olive
```

### Role mapping

```text
Primary brand blue       #1850A1
Secondary blue           #5287C1
Primary brand yellow     #FDF22C
Soft yellow surface      #FCF59A
Muted yellow hover       #F0E964
Main pale surface        #E2E9F0
Pale blue surface        #B1C6E0
Muted olive              #BFB86A
Primary text             #212529
Secondary text           #4B4C4D
Card/surface white       #FFFFFF
```

The existing near-black navy/gold treatment is replaced by the URA blue/yellow family.

## Brand Colour Versus Semantic Colour

Brand colours must not replace operational status colours.

Keep semantic colours separate:

```text
SUCCESSFUL  green
PENDING     amber/yellow status treatment
REVERSED    red
errors      red
warnings    amber
healthy     green
```

URA yellow is primarily an identity and emphasis colour. It must not be reused so broadly that it becomes impossible to distinguish a brand highlight from a warning state.

## Application Shell

### Sidebar

The sidebar becomes a solid `#1850A1` URA blue.

Normal navigation items use white or pale-blue text.

The active navigation item uses:

```text
background: #FDF22C
text:       #212529
```

Hover for inactive navigation uses a lighter/translucent blue rather than dark navy.

The application brand area remains simple and text-led. No logo is added unless a separate approved logo asset is supplied later.

### Workspace

The main workspace uses a very light neutral/pale-blue background derived from `#E2E9F0` rather than the current generic grey.

Cards, tables, forms, drawers, and the top bar remain primarily white for readability.

Borders and separators use softened blue-grey values rather than dark strokes.

## Typography

The preferred application stack is:

```css
font-family:
  "Gotham-Book",
  system-ui,
  -apple-system,
  "Segoe UI",
  Arial,
  Helvetica,
  sans-serif;
```

This reflects the typography observed across URA web properties while retaining robust fallbacks.

### Font distribution constraint

Do not add, package, download, or redistribute Gotham font files in the repository.

If `Gotham-Book` is already available on the user's machine or through an approved internal corporate asset, the browser may use it naturally. Otherwise the system font fallback is used.

### Weight and hierarchy

The interface should become slightly less heavy than the existing startup-style dashboard.

Recommended hierarchy:

```text
Page title        26–28px / 600
Section heading   18–20px / 600
KPI value         30–36px / 600
Body              14–16px / 400
Field label       13–14px / 500
Table heading     11–12px / 600 uppercase
Navigation        14px / 500
```

Avoid using very heavy `800+` weights for most ordinary labels and headings.

## Buttons and Actions

### Primary action

Primary task actions such as:

- New Payment
- New Taxpayer
- New Station
- Create Payment
- Save Changes

use URA yellow:

```text
background: #FDF22C
text:       #212529
```

Hover uses `#F0E964` or a closely related slightly-muted yellow.

### Secondary action

Secondary buttons remain white with URA blue border/text:

```text
background: white
border:     #1850A1
text:       #1850A1
```

### Semantic actions

Operational actions keep semantic colours:

- Mark Successful remains green.
- Reverse Payment remains red.

This preserves the meaning of operational state changes.

## Forms

Forms retain the existing drawer-based interaction pattern.

Refinements:

- labels use `#4B4C4D`,
- focus rings use `#5287C1`,
- selected controls may use very light `#E2E9F0`/`#B1C6E0` backgrounds,
- primary submit buttons use URA yellow,
- destructive actions remain red,
- inputs remain white for clarity.

The existing Oracle-backed reference dropdowns remain unchanged functionally.

## Tables

Tables keep the existing operational structure.

Visual treatment:

- white body,
- very pale blue-grey header,
- URA blue links,
- subtle pale-blue hover state,
- semantic badges retain green/amber/red,
- borders use pale blue-grey,
- no heavy blue fills across entire data rows.

Table density remains appropriate for operational monitoring rather than marketing presentation.

## Dashboard

The approved Dashboard information architecture remains unchanged.

### KPI cards

The four KPI cards stay large and prominent.

Recommended treatment:

- Total Taxpayers: white card with blue accent.
- Total Stations: white card with blue accent.
- Payments Today: white card with yellow accent.
- Amount Collected Today: strong `#1850A1` blue card with white type and yellow accent.

This replaces the current near-black navy amount card.

### Payments by Station

Use URA blue as the main bar colour.

Use URA yellow to highlight the leading/top station only.

Do not use yellow for every bar.

### Payment Status donut

Keep semantic status colours rather than brand palette colours:

- Successful = green
- Pending = amber/yellow
- Reversed = red

### Recent activity

Recent Payments and Recent Taxpayer Activity remain white panels with restrained pale-blue separators and URA blue action/link emphasis.

## Drawers and Detail Views

Drawers stay white.

Use URA blue for titles and links, and pale blue-grey for detail tiles.

Primary edit/save actions use the URA yellow primary button.

Status-changing actions remain semantic.

## Top Bar

The top bar remains white.

The small eyebrow/section label can use URA blue rather than generic grey.

User avatar can use `#1850A1` with white text.

No additional corporate messaging or environment label is added.

## Icons

URA web properties use Font Awesome, but this application must not gain a public-CDN dependency.

Preferred order:

1. keep the existing lightweight text/inline icon approach during this redesign;
2. later use approved locally hosted Font Awesome assets if they already exist internally;
3. otherwise use inline SVG icons.

Do not add Font Awesome from an external CDN as part of this change.

## Interaction States

All interactive elements need visible hover, focus, active, and disabled states.

Focus styles should use URA blue and remain keyboard-visible.

Yellow buttons must keep sufficient dark-text contrast.

Blue surfaces use white text.

Semantic red/green controls must keep readable foreground contrast on hover.

## Accessibility

The redesign must preserve or improve contrast and keyboard usability.

Important constraints:

- avoid white text directly on `#FDF22C`;
- use dark text on yellow;
- use white text on `#1850A1`;
- do not communicate payment status through colour alone;
- badges retain text labels;
- focus rings remain visible;
- charts retain labels/tooltips/accessible text.

## Responsive Behaviour

Existing responsive layout breakpoints remain conceptually unchanged.

On narrow screens:

- sidebar remains compact,
- active yellow navigation remains visible,
- cards collapse as they do now,
- forms/drawers remain usable,
- no new horizontal scrolling should be introduced outside existing table wrappers.

## Public URA Website Influence

The redesign borrows principles visible across URA public web properties rather than copying page layouts literally:

- strong blue/yellow institutional identity,
- task-first actions,
- Gotham-led typography where available,
- blue links,
- clear white content surfaces,
- direct service-oriented interaction.

The internal app keeps its own more compact operational information architecture because its users are working with transactions, master data, pipeline state, and analytics rather than browsing public services.

## Files Expected to Change

Primary visual implementation is expected to touch:

```text
app/static/css/app.css
app/templates/index.html        only if class hooks are needed
app/static/js/dashboard.js      only where chart colour logic needs adjustment
```

Other JavaScript files should change only when necessary to provide appropriate semantic classes. No API or business-rule changes are expected.

## Testing and Verification

Implementation must verify:

- URA colour variables exist and old navy/gold variables are no longer the visual source of truth;
- active navigation uses `#FDF22C` on `#1850A1` sidebar;
- Gotham-first font stack is present without bundled font files;
- primary buttons use yellow with dark text;
- semantic success/reverse controls retain green/red;
- Dashboard bar/donut semantics match this spec;
- no business API behaviour changes;
- existing unit/API tests remain green;
- browser inspection confirms readable hover/focus states and acceptable contrast.

## Non-Goals

This redesign does not include:

- adding a URA logo,
- packaging Gotham font files,
- changing payment/taxpayer/station functionality,
- changing the Dashboard data model,
- changing APIs,
- changing Oracle, Debezium, Kafka, ClickHouse, or Power BI,
- introducing a CSS framework,
- introducing React or npm,
- adding a public CDN dependency,
- redesigning the application navigation structure.
