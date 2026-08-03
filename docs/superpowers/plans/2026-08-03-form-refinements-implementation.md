# Operational Form Refinements Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver three small UI refinements: preserve the successful-action button on hover, select taxpayers from live Oracle-backed data when creating a payment, and remove the POC environment footer.

**Architecture:** Keep all business behavior unchanged. The hover fix is CSS-only; the payment form will reuse the existing `GET /api/taxpayers` endpoint and submit the selected `taxpayer_id` through the existing payment API; the footer removal is template-only. No schema, payment-state, CDC, Kafka, ClickHouse, or Power BI changes are permitted.

**Tech Stack:** FastAPI/Jinja shell, vanilla JavaScript, CSS, pytest, Python 3.9.

## Global Constraints

- Preserve payment transitions exactly: `PENDING -> SUCCESSFUL`, `PENDING -> REVERSED`, `SUCCESSFUL -> REVERSED`, and `REVERSED` terminal.
- Reversal remains a status update on the existing Oracle payment row; do not delete the payment, create a negative payment, or change its amount.
- Payment creation continues to submit `taxpayer_id` to the existing `/api/payments` contract.
- Taxpayer options must come from the existing Oracle-backed taxpayer API; do not hard-code TINs.
- If taxpayer options cannot be loaded, do not fall back to arbitrary free-text TIN entry.
- Use a native `<select>`; do not add a custom combobox or new frontend dependency.
- Remove only the sidebar block containing `POC Environment` and `Trusted internal access`; keep the rest of the shell unchanged.
- Deliver the three product changes as three separate commits in this exact order:
  1. `fix: preserve successful action button on hover`
  2. `feat: select taxpayer when creating payment`
  3. `chore: remove POC environment footer`

---

### Task 1: Preserve the successful-action button on hover

**Files:**
- Create/Modify test: `tests/test_frontend_contracts.py`
- Modify: `app/static/css/app.css`

**Interfaces:**
- Consumes: existing `.btn-success` class used by `Mark Successful` in `app/static/js/payments.js`.
- Produces: an explicit `.btn-success:hover` rule with white text and a darker green background/border.

- [ ] **Step 1: Write a failing frontend contract test**

Create `tests/test_frontend_contracts.py` with:

```python
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_success_button_has_readable_hover_state():
    css = (ROOT / "app/static/css/app.css").read_text()

    assert ".btn-success:hover" in css
    hover_rule = css.split(".btn-success:hover", 1)[1].split("}", 1)[0]
    assert "color:#fff" in hover_rule.replace(" ", "")
    assert "background:" in hover_rule
    assert "border-color:" in hover_rule
```

- [ ] **Step 2: Run the focused test and verify failure**

Run:

```bash
python -m pytest tests/test_frontend_contracts.py::test_success_button_has_readable_hover_state -v
```

Expected before implementation: FAIL because `.btn-success:hover` does not exist.

- [ ] **Step 3: Add the explicit hover rule**

In `app/static/css/app.css`, immediately after the existing `.btn-success` declaration, add:

```css
.btn-success:hover{color:#fff;background:#166534;border-color:#166534}
```

This must override the generic `.btn:hover{background:#f8fafc}` behavior.

- [ ] **Step 4: Run the focused test**

```bash
python -m pytest tests/test_frontend_contracts.py::test_success_button_has_readable_hover_state -v
```

Expected: PASS.

- [ ] **Step 5: Commit only Task 1**

```bash
git add app/static/css/app.css tests/test_frontend_contracts.py
git commit -m "fix: preserve successful action button on hover"
```

---

### Task 2: Populate Create Payment with live taxpayer options

**Files:**
- Modify test: `tests/test_frontend_contracts.py`
- Modify: `app/static/js/payments.js`

**Interfaces:**
- Consumes: existing `api()` helper and `GET /api/taxpayers` response shape `{items: [...], total, summary}`.
- Each taxpayer item provides at minimum `taxpayer_id` and `taxpayer_name`.
- Produces: `PaymentsPage.loadTaxpayers()` and `PaymentsPage.taxpayerOptions()`; Create Payment uses `<select name="taxpayer_id">`.

- [ ] **Step 1: Extend frontend contract tests**

Append to `tests/test_frontend_contracts.py`:

```python
def test_create_payment_uses_taxpayer_dropdown_from_api():
    js = (ROOT / "app/static/js/payments.js").read_text()

    assert 'api("/api/taxpayers?limit=200")' in js
    assert 'name="taxpayer_id"' in js
    assert '<select class="select" name="taxpayer_id"' in js
    assert 'KJT Traders' not in js
    assert 'TIN001' not in js


def test_payment_form_does_not_fallback_to_free_text_taxpayer_tin():
    js = (ROOT / "app/static/js/payments.js").read_text()

    assert '<input class="input" name="taxpayer_id"' not in js
```

- [ ] **Step 2: Run focused tests and verify failure**

```bash
python -m pytest \
  tests/test_frontend_contracts.py::test_create_payment_uses_taxpayer_dropdown_from_api \
  tests/test_frontend_contracts.py::test_payment_form_does_not_fallback_to_free_text_taxpayer_tin \
  -v
```

Expected before implementation: FAIL because Create Payment still uses a free-text input and does not load taxpayer options.

- [ ] **Step 3: Add taxpayer state and option helpers**

Change the `PaymentsPage` constructor to initialize taxpayer state:

```javascript
constructor(shell) {
  this.shell = shell;
  this.taxpayers = [];
}
```

Add an HTML escaping helper near the existing formatting helpers:

```javascript
const escapeHtml = (value) => String(value ?? "")
  .replaceAll("&", "&amp;")
  .replaceAll("<", "&lt;")
  .replaceAll(">", "&gt;")
  .replaceAll('"', "&quot;")
  .replaceAll("'", "&#039;");
```

Add these methods to `PaymentsPage`:

```javascript
async loadTaxpayers() {
  const data = await api("/api/taxpayers?limit=200");
  this.taxpayers = data.items || [];
}

taxpayerOptions() {
  return this.taxpayers.map(taxpayer => `
    <option value="${escapeHtml(taxpayer.taxpayer_id)}">
      ${escapeHtml(taxpayer.taxpayer_name)} — ${escapeHtml(taxpayer.taxpayer_id)}
    </option>`).join("");
}
```

- [ ] **Step 4: Make Create Payment load reference data before opening**

Change `openCreate()` to `async openCreate()` and load taxpayers first:

```javascript
async openCreate() {
  try {
    await this.loadTaxpayers();
  } catch (error) {
    this.taxpayers = [];
    this.shell.toast(`Taxpayers could not be loaded: ${error.message}`, true);
    return;
  }

  if (!this.taxpayers.length) {
    this.shell.toast("No taxpayers are available for payment creation.", true);
    return;
  }

  // existing drawer rendering continues here
}
```

The existing click binding remains valid because an async function can be called from the click handler without changing the handler shape.

- [ ] **Step 5: Replace the free-text taxpayer field**

Replace:

```html
<div class="field"><label>Taxpayer TIN</label><input class="input" name="taxpayer_id" maxlength="20" required placeholder="TIN001"></div>
```

with:

```html
<div class="field"><label>Taxpayer</label><select class="select" name="taxpayer_id" required><option value="">Select taxpayer</option>${this.taxpayerOptions()}</select></div>
```

Do not change the POST payload or `/api/payments` backend contract.

- [ ] **Step 6: Run the frontend contract tests**

```bash
python -m pytest tests/test_frontend_contracts.py -v
```

Expected: all frontend contract tests pass.

- [ ] **Step 7: Commit only Task 2**

```bash
git add app/static/js/payments.js tests/test_frontend_contracts.py
git commit -m "feat: select taxpayer when creating payment"
```

---

### Task 3: Remove the POC environment footer

**Files:**
- Modify test: `tests/test_app_shell.py`
- Modify: `app/templates/index.html`

**Interfaces:**
- Consumes: existing Jinja application shell.
- Produces: unchanged navigation except for removal of the sidebar footer block containing the two POC labels.

- [ ] **Step 1: Add failing shell assertions**

In `tests/test_app_shell.py`, extend `test_root_renders_the_internal_application_shell()` with:

```python
assert "POC Environment" not in response.text
assert "Trusted internal access" not in response.text
```

- [ ] **Step 2: Run the focused test and verify failure**

```bash
python -m pytest tests/test_app_shell.py::test_root_renders_the_internal_application_shell -v
```

Expected before implementation: FAIL because both strings are still in `index.html`.

- [ ] **Step 3: Remove only the sidebar footer markup**

Delete this block from `app/templates/index.html`:

```html
<div class="sidebar-footer">
  <span class="environment-dot"></span>
  <div><strong>POC Environment</strong><small>Trusted internal access</small></div>
</div>
```

Do not alter the navigation items, top bar, user chip, drawer, or toast region.

- [ ] **Step 4: Run the focused test**

```bash
python -m pytest tests/test_app_shell.py::test_root_renders_the_internal_application_shell -v
```

Expected: PASS.

- [ ] **Step 5: Run the complete suite**

```bash
python -m pytest -v
```

Expected: all existing and new tests pass; record the actual count rather than assuming one.

- [ ] **Step 6: Commit only Task 3**

```bash
git add app/templates/index.html tests/test_app_shell.py
git commit -m "chore: remove POC environment footer"
```

---

## Host Verification

After pulling the three commits on `datalake-test02`:

```bash
cd /home/jkasule/cdc-clickhouse-poc
source /home/jkasule/kjt/venv/bin/activate
git pull
python -m pytest -v
```

Restart Uvicorn if it is not running with `--reload`, then verify in the browser:

1. Open a PENDING payment and hover `Mark Successful`; white text remains readable on dark green.
2. Open `+ New Payment`; Taxpayer is a dropdown populated with live entries such as `KJT Traders — TIN001`.
3. Select a taxpayer and create a test payment; existing server-side taxpayer/station validation still governs the transaction.
4. Confirm the sidebar no longer shows `POC Environment` or `Trusted internal access`.
5. Reverse behavior remains unchanged: it only changes status to `REVERSED`, and reversed payments remain terminal.
