# Operational Form Refinements Design

## Goal

Make three small usability refinements to the existing internal transaction application without changing the payment state model, database schema, or Oracle/CDC architecture.

## Scope

### 1. Payment status action hover fix

The existing `Mark Successful` action remains in the payment detail drawer exactly as it is functionally.

The success button must keep readable white text on hover. The hover state will use a darker green background and a matching darker green border instead of inheriting the generic white-button hover rule.

No status rules change:

- `PENDING -> SUCCESSFUL`
- `PENDING -> REVERSED`
- `SUCCESSFUL -> REVERSED`
- `REVERSED` is terminal

Reversing changes the existing Oracle payment row status to `REVERSED`. It does not delete the payment, create a negative payment, or alter the amount. CDC carries the status update downstream.

### 2. Taxpayer dropdown in Create Payment

Replace the free-text `Taxpayer TIN` field in the Create Payment drawer with a dropdown populated from the existing Oracle-backed taxpayer API.

Each option displays business-friendly text in this form:

```text
KJT Traders — TIN001
```

The submitted value remains the taxpayer ID/TIN, so the existing payment API contract and server-side validation remain unchanged.

Implementation should reuse existing source data rather than hard-code taxpayers. If the taxpayer list cannot be loaded, the form should not silently permit an arbitrary TIN; instead, show a clear error/toast and leave payment creation unavailable until the list can be loaded.

No custom searchable combobox is added in this change. A native `<select>` is sufficient for the current POC scale.

### 3. Remove POC environment footer

Remove the sidebar footer block that currently displays:

```text
POC Environment
Trusted internal access
```

The rest of the navigation shell remains unchanged.

## Related form patterns

The existing Taxpayer form already uses an Oracle-backed Station dropdown and remains unchanged.

Potential future dropdown candidates, not included in this change:

- Taxpayer Type, once an explicit allowed-value list is formally defined.
- Station Region suggestions, if region values are later governed as a controlled reference list.

## Files expected to change

- `app/static/css/app.css`
- `app/static/js/payments.js`
- `app/templates/index.html`
- tests only where needed to lock the revised behavior

## Commit separation

The implementation must be delivered as three separate commits in this order:

1. `fix: preserve successful action button on hover`
2. `feat: select taxpayer when creating payment`
3. `chore: remove POC environment footer`

## Non-goals

- No new payment statuses.
- No payment quick-action menu.
- No arbitrary editing of completed payments.
- No database schema changes.
- No changes to Debezium, Kafka, ClickHouse, or Power BI.
- No redesign of Taxpayer or Station forms.
