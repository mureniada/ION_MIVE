# H1 measurement harness: capture-only IVE baseline pass

Prepared 2026-10-07 for David's "H1 OBSERVABILITY CLOSURE" request (17:00Z). **Not executed.** It waits for operator GO.

## What it does

The harness runs one sequential pass over the frozen 27-question set, inside the staging container, on deployment `2c91c45e`. It persists the full IVE output of each turn. The IVE request goes out exactly as the deployment builds it. Retrieval runs once per turn, inside the normal `Core.ask`.

| Item | Value |
|---|---|
| Provider calls planned | 27 IVE calls (`gemini-2.5-pro`, no thinking config, as deployed) |
| Composer calls planned | 0 |
| Retries / replacements | none |
| Estimated cost | about $0.86, at most about $1.18. Based on the 81 Phase A IVE calls (mean 1,133 input, 1,352 visible and 1,687 thinking tokens per call) and pricing verified 2026-10-06 |
| Estimated run time | about 11 to 12 minutes (Phase A IVE calls averaged 24.4 s; maximum 36.3 s) |

## How it stays observation-only

- **IVE request unchanged.** The harness does not touch the IVE prompt, schema, model, thinking budget, retrieval, Context Pack or settings. The Core is built from the deployed settings with the same calls the frozen E3 harness used: `Settings.load` and `build_core`.
- **No composer call.** Composition is skipped through the Core's own no-composer path. Only inside the harness process, `core._composer = None`. `Core.ask` then returns its deterministic base answer and never reaches `compose()`. The IVE call runs before that block (repo `orchestrator.py:540` vs `:618`). The deployed service and its configuration are not touched.
- **Fail-closed guard.** Any Gemini call whose backend label is not `ive`, and any IVE call beyond 27, is refused before it reaches the provider.
- **Raw capture.** A pass-through wrapper on `GeminiBackend.generate` keeps the exact text the IVE adapter parses: `GenerationResult.text`, which is `response.text`. In google-genai 2.28.0 that text is the visible text parts only; thought parts are excluded (`types.py:8698-8734`). The wrapper records the text verbatim with its sha256, chars and UTF-8 bytes. Request inputs are kept only as sha256 and sizes.
- **Normalized report.** `AskResult.ive_reports` is persisted as returned (repo `orchestrator.py:758`). It holds claims, concepts, relations, uncertainty and `raw_response`. Each turn records whether `raw_response` equals the captured text.
- **Per-call ledger.** The frozen E3 tap (`voe_e3_paired_replay.py`, sha256 `1134c4f6…65c7`, `e3-call-ledger-v2`) records usage, latency and sanitized errors per provider call. It records whether a thinking config was sent.

## Start checks

All of these run before any provider call, and every one must pass:

- Questions sha256 `b6a414cd…b833` and 27 questions.
- `RAILWAY_DEPLOYMENT_ID` is `2c91c45e-997c-4d8f-80e7-83be99e9b0af`.
- Model is `gemini-2.5-pro`. Profile is STANDARD_GEMINI, SINGLE, `["gemini"]`.
- v0.4 identity: profile 0.4, fingerprint `ba22801e…95b7`, composer system instruction `eba5b8c8…0e64`. The deployed composer budget is 512, both in settings and on the Core's composer.
- `Core.ask` source has the `if self._composer is not None` path and reads the composer only after the IVE call.
- The backend source sets no `http_options` or `retry_options`, and google-genai is 2.28.0. With no retry options, 2.28.0 never retries (`_api_client.py:562-573`), so 27 calls means 27 requests.
- The tap and capture are installed. Zero provider calls so far.

`H1_PREFLIGHT_ONLY=1` runs only these checks and exits.

## Stop rules

The run never retries a call and never replaces a turn. It stops at once on any of the following:

- **HTTP 402.** Stop, with no billing or credential change.
- **Guard condition.** A refused call, a non-IVE call, a composition attempt, more than one IVE call in a turn, or an IVE thinking config sent.
- **Capture mismatch.** A successful IVE call without captured text.
- **Consecutive failures.** 3 consecutive turns without a captured IVE output, whether from a provider error or a turn failure.
- **Hard cap.** 27 IVE calls.

## Output

All files are new. `H1_OUT_DIR` must not already exist.

- `h1cap_ledger.jsonl` contains:
  - one `H1_META` line, with identity, start checks, file hashes and versions;
  - one `H1_TURN` line per question, with the tap rows, the verbatim capture, the full `ive_reports`, retrieval and context sizes, and evidence ids;
  - one `H1_SUMMARY` line.
- stdout carries `H1_PROGRESS` per turn, then `H1_DONE`.

## Offline sizing (`h1_sizing.py`, stdlib only, no provider calls)

For each captured output, the analyzer measures:

- Total visible output in chars and UTF-8 bytes.
- Visible tokens from provider usage (`candidates_token_count`).
- For each of concepts, relations, claims, highlights, uncertainty and abstract:
  - item count;
  - serialized chars and bytes;
  - combined concepts+relations size and its share of the output.

Sizes come from exact spans in the captured text. Each top-level member owns the text from its key up to the next key. The member spans plus the envelope add up to the total exactly. The analyzer also reports value-only sizes and compact re-serialized sizes.

Two figures are **ESTIMATED**, labelled as such, and computed without a tokenizer:

- per-field tokens, by char share;
- latency, from an OLS slope of call latency on output tokens.

## Offline test evidence (cloud, 2026-10-07)

`tests/test_h1_capture.py` passed 29 of 29, with sockets blocked and a fake google-genai Client.

The tests use the real SDK types and the real repository code (`aa561f3`): `Core.ask`, ModelGateway, GeminiIVE, GeminiBackend and ive_common. They also use the frozen E3 tap, loaded by sha256. They cover:

- the zero-call preflight;
- a 27-turn pass with byte-exact capture (unicode, pretty-printed and fenced outputs), 0 composer calls, an unchanged IVE request, and `raw_response` equal to the capture;
- the stop rules: 402, three consecutive failures (a success resets the count), the guard refusing a non-IVE call before the provider, two IVE calls in one turn, the cap at 27, and a missing capture;
- the real `build_world` wiring;
- span arithmetic on tricky JSON;
- the analyzer end to end.

## Launch sequence (only after GO)

1. On the PC, verify the sha256 values in `SHA256SUMS.txt`.
2. Upload three files to a new container directory, `/tmp/h1cap/`, using chunked base64 over `railway ssh`, as for Phase A:
   - `voe_h1_ive_capture.py`;
   - the frozen `voe_e3_paired_replay.py` (`1134c4f6…`);
   - `questions.json`, saved as `e3q.json` (`b6a414cd…`).
3. Re-verify the hashes inside the container.
4. Run the preflight with `H1_PREFLIGHT_ONLY=1`. It must print `H1_PREFLIGHT` with `provider_calls: 0`. Anything else means STOP and report.
5. Launch one detached process with `nohup setsid`, using a lock directory and a `run.exit` marker. A hidden PC poller mirrors `out/` and the logs.
6. The run is never relaunched and never runs as a second instance.
7. After exit, verify the hashes and run `h1_sizing.py` on the mirrored ledger.

## Status labels

- **VERIFIED in repo code (`aa561f3`):**
  - the no-composer path;
  - IVE before composer;
  - `ive_reports` carries the full report;
  - the IVE backend label is `ive` with no thinking budget;
  - the backend sets no retry options.
- **VERIFIED in the google-genai 2.28.0 source:**
  - retries are off by default;
  - `.text` excludes thought parts.
- **VERIFIED in the staging container:** google-genai 2.28.0, recorded in the live-probe meta at 13:43Z. A start check re-verifies it at launch.
- **INFERRED, checked by the start checks at zero cost:** the deployed `e6880e7` code matches on those points. It is not on GitHub.
