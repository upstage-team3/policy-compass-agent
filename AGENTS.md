# Policy Compass Agent Instructions

## Start Here

Before changing code, read these documents in order:

1. `docs/DEVELOPMENT_HANDOFF.md`
2. `docs/PROJECT_STATUS.md`
3. `docs/NEXT_ACTIONS.md`

Use the code and tests as the final source of truth. Update the handoff documents when implementation status changes.

## Current Architecture Rules

- Upstage Solar is the primary Router, Profile, Conversation, and Response path.
- Router output must pass `app/graph/contracts.py::RoutingDecision` validation.
- Keep the graph at eight meaningful orchestration nodes: `prepare_request`, `direct_response`,
  `retrieve`, `assess_evidence`, `rewrite_query`, `build_answer`, `verify_answer`, and `finalize`.
- Reset turn-only search, draft, and validation fields at every API request and Router entry. Only validated profile, recent history, explicit pending, and allowlisted `last_presented_candidates` may cross turns.
- Validate profile state with `app/graph/profile_contracts.py`; malformed/empty extraction is `UNCHANGED`, explicit user deletion is `CLEAR`, and valid allowlisted input is `SET`.
- Pending tasks use the explicit `KEEP`, `RESUME`, `CANCEL`, and `REPLACE` transitions. Resume only when the current utterance fills a recorded required slot.
- A valid LLM routing decision must not be overwritten by keyword rules.
- Keyword and regex rules belong in `app/graph/fallbacks.py` and are fallback-only.
- Exactly one of the three active external data Tools (`youth_policy`, `training`, `recruitment`) should run for a routed search.
- All Tool results cross the graph boundary as `SearchOutcome`; never put guide/failure records in candidate items.
- Apply deterministic no-score evidence gates before answer generation. Weighted eligibility scores are not part of the product contract.
- Compare 시·군·구 when both requested and candidate regions provide it; unresolved or mismatched structured regions must not produce cards.
- Keep recovery bounded: one additional retry for retryable source failure, at most one deterministic query rewrite, and at most one answer revision followed by re-verification.
- Send fixed/direct replies through `verify_answer` too. Only validation-passed `success/partial` search turns may create recommendation cards or replace the allowlisted candidate snapshot.
- Preserve a visible caveat when a `partial` outcome returns usable candidates.
- Startup/business-support requests are ordinary `out_of_scope` turns. They may use the LLM Router and conversation writer, must not invoke an external search Tool, and must not advertise Bizinfo or K-Startup as product integrations.
- The removed Bizinfo search pipeline, `/api/policies` endpoints, RAG-lite repository, `PolicyItem`, and weighted scoring must not be reintroduced without an explicit product decision.
- LLM responses must stay grounded in provided API candidates.
- Use Upstage Solar as the primary language path for routing, profile extraction, clarification, general/out-of-scope conversation, grounded search answers, source-status explanations, and candidate follow-ups. Keep deterministic templates only as bounded fallbacks for missing keys, network failures, and invalid LLM output.
- Do not add a global `MemorySaver`. `SupabaseChatMemoryRepository` is the single session boundary for profile, recent 8-message history, pending, and allowlisted candidate snapshots; its bounded local LRU mirror handles unconfigured/unavailable Supabase.
- Keep same-process `load → graph → save` inside `SessionLockPool`, require UUIDv4 session IDs, enforce the validated 60-second graph deadline (8-second LLM, 10-second source, 9-second repository HTTP), and preserve the in-process limits of 20 requests/minute per session and 120 requests/minute per IP.
- Multi-worker owner binding, database optimistic versioning, and server-side deletion/TTL remain separate follow-ups; do not imply the in-process controls solve them.
- Deployment must pin checkout and `APP_RELEASE_SHA` to the CI `workflow_run.head_sha`, deploy the immutable GHCR digest, and use `/api/ready`; `/api/live` is process liveness only.

## Safety

- Never commit `.env` or print API key values.
- Do not put credentials, authorization headers, or authenticated URLs in logs or docs.
- Do not invent policy, training, recruitment, amount, date, eligibility, or source-link data.
- Do not modify files in the external daily-retrospective folder unless explicitly requested.
- Preserve unrelated user changes in the worktree.

## Required Verification

```bash
uv run ruff check app tests
uv run ruff format app tests --check
uv run pytest tests -q
cd frontend && pnpm test && pnpm run build
```

The local full suite currently passes. Re-run the full Python suite, frontend suite, and frontend production build after changes. Unit tests must remain deterministic without external API keys or network access; do not rely on a hard-coded test count.
