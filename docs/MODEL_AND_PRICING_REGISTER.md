# Model and Pricing Register

Pricing captured **2026-07-13** from official provider pricing pages (OpenAI API pricing; Google Gemini Developer API pricing). Standard tier, text, short-context rates, USD per 1M tokens. **Model names and prices are configuration, not business logic** — they live in `.env` and an isolated, dated pricing table (`docs/08`). Confirm again at build time; unknown pricing returns `null`, never a fabricated estimate.

Status tags: **[GA]** generally available · **[Preview]** may change/deprecate.

## Proposed Pair A — Economical development (default)

Low cost, structured-JSON support, large context, reliable usage metadata. Used for all mocked/dev work and the first controlled live test.

| Role | Model | Input $/1M | Output $/1M | Status |
|------|-------|-----------:|------------:|--------|
| OpenAI IVE | `gpt-5.4-mini` | 0.75 | 4.50 | [GA] |
| Gemini IVE | `gemini-3.1-flash-lite` | 0.25 | 1.50 | [GA] |

Ultra-budget alternative (if quality is acceptable): OpenAI `gpt-5.4-nano` (0.20 / 1.25) + `gemini-3.1-flash-lite`.

## Proposed Pair B — Quality evaluation (opt-in, not default)

Stronger reasoning, higher cost. Not used until separately approved.

| Role | Model | Input $/1M | Output $/1M | Status |
|------|-------|-----------:|------------:|--------|
| OpenAI IVE | `gpt-5.5` | 5.00 | 30.00 | [GA] |
| Gemini IVE | `gemini-3.1-pro` (preview) | 2.00 | 12.00 | [Preview] |

Notes: `gemini-3.1-pro` is Preview — for a GA quality option use `gemini-2.5-pro`. Mid-cost middle ground exists (`gpt-5.6-terra` 2.50/15.00, `gemini-3.5-flash` 1.50/9.00) if Pair A underperforms and Pair B is too costly.

## First-live-question cost estimate (Question 1: "What is money?")

Assumptions (deliberately generous): `top_k=5`, ~6,000 input tokens per provider (5 evidence chunks + instructions + JSON schema), ~2,000 output tokens per provider. MIVE runs locally (no API cost). Two provider calls total (one Gemini, one OpenAI).

| Pair | OpenAI call | Gemini call | Total / question |
|------|------------:|------------:|-----------------:|
| A (economical) | ~$0.0135 | ~$0.0045 | **~$0.018** |
| B (quality) | ~$0.090 | ~$0.036 | **~$0.126** |

Worst-case padding (double the tokens): Pair A still **< $0.05/question**.

Budget implications against locked limits (USD 10 total / USD 1 live-without-approval):
- First live test (1 question, Pair A): **~$0.02** — safe.
- Full 20-question set on Pair A: **~$0.36–0.50** — within the $1 live ceiling, but still requires the pre-batch report per operator rule.
- Full 20-question set on Pair B: **~$2.5** — **exceeds** the $1 no-approval ceiling; requires explicit approval.

## Rules

1. No live call before the operator confirms both keys are configured **and** approves the economical pair + its estimated cost.
2. Model IDs come from `.env` (`OPENAI_MODEL`, `GEMINI_MODEL`); never hardcoded in logic.
3. Pricing table is isolated, dated, and versioned; usage metadata from the provider is preferred over local token estimates.
4. This register is re-verified whenever models or prices change.
