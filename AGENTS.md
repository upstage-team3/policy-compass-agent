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
- Route by `action`: `RESPOND` goes to one Conversation node and `SEARCH` goes to the Tool path.
- A valid LLM routing decision must not be overwritten by keyword rules.
- Keyword and regex rules belong in `app/graph/fallbacks.py` and are fallback-only.
- Exactly one external data Tool should run for a routed request kind.
- LLM responses must stay grounded in provided API candidates.
- Keep deterministic templates for missing keys, network failures, and invalid LLM output.

## Safety

- Never commit `.env` or print API key values.
- Do not put credentials, authorization headers, or authenticated URLs in logs or docs.
- Do not invent policy, training, recruitment, business, amount, date, eligibility, or source-link data.
- Do not modify files in the external daily-retrospective folder unless explicitly requested.
- Preserve unrelated user changes in the worktree.

## Required Verification

```bash
uv run ruff check app tests
uv run ruff format app tests --check
uv run pytest tests -q
```

The current expected baseline is `64 passed`. Unit tests must remain deterministic without external API keys or network access.
