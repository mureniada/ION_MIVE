# Voice of Emergence — Technical Release Closure

**Date:** 2026-09-05
**Type:** Technical release closure record (read-only verification + this
document only). Not a commit, push, merge, or public-announcement decision.
**Produced by:** L6-C1 through L6-C4 (staging identity reconfirmation,
hosting/security topology analysis, fork-scoped service creation and
configuration, private-only hosted acceptance).

---

## A. Release classification

**VOICE OF EMERGENCE TECHNICAL RELEASE STATE = READY FOR CONTROLLED HANDOFF.**

This means: the public URL below may be given to the intended external
owner or a small controlled audience, opened directly, linked from
ION.fund, linked or attached from leaf, or later replaced/embedded by
another frontend.

This does **not** mean: mass public announcement, internet-scale load
readiness, formal multi-tenant isolation, or formal rate-limit hardening.
See section G.

---

## B. Exact implementation / deployment identities

### Voice of Emergence surface

| Field | Value |
|---|---|
| Service | `voice-of-emergence` |
| Service ID | `2e7a66f2-8fee-4c9d-ac6d-1b817af7d0a9` |
| Surface Git commit | `aaef3be6b2a2098ae411c5d60a47b170597824e9` |
| Commit subject | "Voice of Emergence Streamlit release surface" |
| Railway deployment | `218c25c3-c92b-4876-8717-dcbb1f9a1c92` |
| Public domain ID | `c0e0a922-349d-4a37-b216-90465c7b963d` |
| Public URL | `https://voice-of-emergence-voe-staging-rc.up.railway.app` |
| Target port | `8501` |
| Auto-deploy | `false` |
| Deployment triggers | `0` |

### Backend

| Field | Value |
|---|---|
| Service | `ION_MIVE` |
| Service ID | `33fa65be-5b8e-4e0c-8277-ba43e05d7032` |
| Environment | `voe-staging-rc` |
| Environment ID | `1a2c9bbe-acc6-4e05-9a27-81141af19268` |
| Backend commit | `710b1745af42e924cc3694b71c5d46b6dd06f7f4` |
| Backend deployment | `acd37acd-1b43-41db-9a05-87f8a735475f` |
| Backend listen port | `8000` |
| Public ServiceDomain count | `0` |
| Public CustomDomain count | `0` |
| Private network | present |
| Auto-deploy | `false` |

### Production (untouched throughout)

| Field | Value |
|---|---|
| Deployment | `0bec7d76-1a24-467e-bcfa-e82dd9a2916d` |
| Commit | `dacf954b2be52a51699faaeee964acdbf162c27d` |
| Status | `SUCCESS` |
| Public domain | `ionmive-production.up.railway.app` (unchanged) |

**Final live read-only reconfirmation (2026-09-05, this task):** VOE
deployment `218c25c3-...` SUCCESS, 1 running instance, public root HTTP
200. ION_MIVE staging deployment `acd37acd-...` SUCCESS, 1 running
instance, 0 public domains, private network present. Former public
backend hostname (`ionmive-voe-staging-rc.up.railway.app`) returns HTTP
404 rather than serving ION_MIVE — a single bounded check, not polled.
Production deployment, commit, and domain unchanged.

---

## C. Final topology

**PUBLIC:** `https://voice-of-emergence-voe-staging-rc.up.railway.app`
provides the Voice of Emergence Streamlit application only.

**PRIVATE:** `voice-of-emergence` → Railway private network → `ION_MIVE`
on port `8000`. ION_MIVE has no public ingress in `voe-staging-rc`.

Existing production ION_MIVE is a separate environment and was untouched
by this release.

No CORS is required: the browser only ever talks to the Streamlit server;
the backend call is made server-side from `pilot_client.py`, not from
browser JavaScript.

No public backend authentication is required under this topology, because
the backend has no public network path to authenticate against. This does
**not** mean the public Streamlit surface itself has formal abuse
protection — see section G.

---

## D. Proof chain

| Stage | Result |
|---|---|
| E4 governed backend | PASS |
| Real Gemini backend execution | PASS |
| 10-book governed corpus candidate | PASS |
| Cloud candidate materialization | PASS |
| Read-only candidate runtime scope | PASS |
| Real staging governed E2E | PASS |
| Streamlit implementation | VERIFIED |
| Streamlit release commit | `aaef3be6b2a2098ae411c5d60a47b170597824e9` |
| Local real Streamlit → staging acceptance | PASS |
| Hosted Streamlit deployment | PASS |
| Hosted public domain | PASS |
| Hosted real Streamlit turn with public backend still present | PASS |
| Public ION_MIVE domain removal | PASS |
| Final private-only hosted Streamlit turn | PASS |

**FINAL PRIVATE-ONLY PRODUCT PATH = PROVEN.** The last hosted turn ran
with zero public ION_MIVE ServiceDomains in existence and the former
public URL already returning 404 — there was no public backend route
available for the hosted Streamlit server to have used instead.

---

## E. Public handoff URL

```
https://voice-of-emergence-voe-staging-rc.up.railway.app
```

---

## F. Product-mode / claim boundary

**Voice of Emergence release execution mode = SINGLE (standard Gemini
execution).**

This release does **not** claim MIVE consensus, cross-model agreement, or
dual-model verification. The interface truthfully discloses this to the
user on every answer: *"This response was produced by a single configured
model execution (gemini). No second, independent model interpretation was
run for this turn, so no cross-model agreement, disagreement, or consensus
claim applies."*

Evidence projection is public and bounded to: source/title, reference,
excerpt, and linked claim. Verified during hosted acceptance to not
expose: raw TurnRecord structure, governance internals, Qdrant internals,
provider credentials, operational metrics, backend hostnames, or private
network details.

---

## G. Open operational limitations

1. No formal application-level rate limiting currently exists for the
   public Streamlit surface.
2. Initial distribution should therefore remain controlled/limited.
3. The backend session controller is in-memory (no persistent or
   cross-replica session store).
4. The backend is intentionally kept at one replica / one worker for this
   release state.
5. The environment is named `voe-staging-rc`; this is Railway-internal
   operational metadata, not user-visible, and does not affect function.
6. The Railway service manifest may retain an inert `branch: "main"` label
   while the actually-deployed commit is exactly `aaef3be6...`; this is
   harmless because auto-deploy is `false` and no DeploymentTrigger exists
   for this service.
7. A custom domain is not required for function and is not part of this
   release proof.

None of these block the controlled handoff classified in section A.

---

## H. Kill switch / rollback

**Immediate public-surface OFF object:** VOE ServiceDomain ID
`c0e0a922-349d-4a37-b216-90465c7b963d`.

**Emergency controlled OFF action:** delete that one ServiceDomain
(`serviceDomainDelete`). Effect: removes public Voice of Emergence
ingress; leaves the VOE container running; leaves private ION_MIVE
running and reachable to it; does not touch production.

**Alternative, stronger OFF:** stop the VOE service instance/deployment,
under separate authorization.

**Constraint:** ION_MIVE's staging public domain must not be recreated as
a rollback method — that would reopen the exact public backend ingress
this release closed.

No action in this section was executed as part of this closure task.

---

## I. External handoff brief (plain-English, for the intended owner)

> Voice of Emergence is available at the URL above. It is currently
> delivered as a standalone Streamlit application. You're welcome to link
> to it from ION.fund or leaf now — the URL is stable and ready for a
> small, controlled audience. Later, the interface itself can be embedded
> or reimplemented elsewhere without changing the governed backend
> underneath it. This release intentionally runs in single-model mode
> (not a multi-model comparison). Every answer comes with supporting
> evidence you can expand in the interface. The backend that does the
> actual reasoning and retrieval is not publicly exposed — only the
> Voice of Emergence interface itself is.

(No Railway IDs, private hostnames, ports, Git hashes, Qdrant details,
credentials, or operator diagnostics are included above, by design.)

---

## J. What is explicitly NOT claimed

- Not a multi-model / MIVE-consensus product in this release.
- Not internet-scale load tested.
- Not formally rate-limit hardened.
- Not multi-tenant isolated beyond per-session backend state.
- Not a mass-public-announcement-ready release — controlled distribution
  only.
- Does not certify `docs/CANONICAL_SYSTEM_MAP.md` as current (see K).
- Does not authorize external handoff by itself — that remains a separate
  operator action.

---

## K. Next post-release reconciliation work

`docs/CANONICAL_SYSTEM_MAP.md` is now materially stale with respect to:
E4, `voe-staging-rc`, the Voice of Emergence service, the private-only
backend topology, the exact VOE deployment, and the public VOE URL.

**CANONICAL SYSTEM MAP UPDATE = NEXT POST-CLOSURE RECONCILIATION TASK.**
This is not a blocker to the controlled handoff already proven above.

Recommended order after this artifact is reviewed:

1. Review this closure artifact.
2. Commit/bind this closure artifact under separate authorization.
3. Provide the controlled handoff URL to the intended owner.
4. Establish provider spend alerts / controlled-distribution posture
   (operational, no code change).
5. Reconcile `docs/CANONICAL_SYSTEM_MAP.md`.
6. Optionally add a custom domain or stronger rate limiting later.

Backend/frontend development should not reopen without a newly observed
defect.
