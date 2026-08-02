# Pull Request

## Summary

Describe what this PR changes and why.

## Scope

- [ ] Application shell / UI
- [ ] Payments
- [ ] Taxpayers
- [ ] Stations
- [ ] Dashboard / Reports
- [ ] Event Monitor
- [ ] Pipeline Health
- [ ] Simulator
- [ ] Deployment / systemd
- [ ] Documentation
- [ ] Other

## Architecture guardrails

These checks are required for this repository:

- [ ] Oracle remains the transactional source of truth.
- [ ] The application does **not** write directly to Kafka.
- [ ] The application does **not** write directly to ClickHouse.
- [ ] Operational screens (Payments, Taxpayers, Stations) read/write Oracle.
- [ ] Analytical/engineering screens read ClickHouse and/or infrastructure health APIs.
- [ ] Existing Debezium connectors, Kafka topics, ClickHouse tables/views, and Docker services were preserved unless this PR explicitly documents why a change was necessary.
- [ ] SCD2 / point-in-time station semantics remain correct.
- [ ] ClickHouse `ingested_at` is not being used as the authoritative source-event ordering field.

## Current source-schema guardrail

For the current application phase:

- [ ] No `TAXPAYER.STATUS` column was introduced.
- [ ] No `STATION.STATUS` column was introduced.
- [ ] No other TAXPAYER/STATION lifecycle schema change was made without explicit approval.
- [ ] Taxpayer/station deactivate/reactivate behavior was not assumed by the implementation.
- [ ] Payment validation uses fields that actually exist in the current Oracle schema.

## Business rules

If this PR touches payment behavior:

- [ ] Payment transitions are enforced server-side.
- [ ] `PENDING → SUCCESSFUL` is allowed.
- [ ] `PENDING → REVERSED` is allowed.
- [ ] `SUCCESSFUL → REVERSED` is allowed.
- [ ] `REVERSED` is terminal.
- [ ] Payment amount must be positive.
- [ ] Referenced taxpayer must exist.
- [ ] Referenced taxpayer station must exist where required.
- [ ] No taxpayer/station ACTIVE/INACTIVE assumption was added.
- [ ] `UPDATED_AT` is changed appropriately for source updates.

## Error handling / resilience

- [ ] Raw Oracle errors are not exposed to the browser.
- [ ] Stack traces, credentials, SQL, and connection strings are not returned to clients.
- [ ] Oracle write failures do not report false success.
- [ ] Oracle transactions rollback on failed writes.
- [ ] ClickHouse failure does not unnecessarily break Oracle source operations.
- [ ] Debezium/Kafka degradation does not unnecessarily break the source application.

## Security / repository hygiene

- [ ] No passwords, tokens, secrets, or API keys are committed.
- [ ] `.env` remains untracked.
- [ ] `.env.example` contains placeholders only.
- [ ] Oracle/Kafka/ClickHouse runtime data is not committed.
- [ ] Debezium connector files containing real credentials are not committed.
- [ ] Database queries use parameter/bind handling rather than unsafe string interpolation.
- [ ] No arbitrary SQL, shell-command, or Kafka-producer endpoint was introduced.

## UI / UX

If this PR touches the web application:

- [ ] UI follows the approved navy/yellow internal-system design.
- [ ] No organizational logo was added.
- [ ] No login/auth flow was added unless explicitly approved.
- [ ] Business pages avoid CDC/Kafka/Debezium jargon.
- [ ] Create/Edit actions use the consistent drawer pattern where appropriate.
- [ ] Dangerous actions use confirmation dialogs where applicable.
- [ ] Success/error feedback uses the shared toast/modal patterns.
- [ ] Navigation preserves the lightweight SPA-style behavior.
- [ ] Taxpayer/station status badges are not invented when the source model has no such field.

## Testing

List the tests/verification commands run:

```text
# commands here
```

- [ ] Relevant unit/business-rule tests pass.
- [ ] Relevant API tests pass.
- [ ] Existing behavior was smoke-tested.

For CDC-affecting changes, verify the path where applicable:

```text
FastAPI / Simulator
        ↓
      Oracle
        ↓
     Debezium
        ↓
       Kafka
        ↓
    ClickHouse
        ↓
   Power BI / APIs
```

- [ ] Source row verified in Oracle.
- [ ] CDC event verified downstream.
- [ ] ClickHouse current/serving state verified.
- [ ] Historical station-at-payment semantics remain valid where relevant.

## Screenshots

Add screenshots for visible UI changes.

## Documentation

- [ ] Documentation was updated if behavior, architecture, setup, or operations changed.
- [ ] `README.md` and `docs/` remain consistent with the implementation.

## Known limitations / follow-up

List anything deliberately left for a later PR.
