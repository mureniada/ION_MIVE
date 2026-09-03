# ION E4 — Durable Closure Binding

**Date:** 2026-09-04
**Project-control phase:** E4 — Integrated Governed ION Pilot
**E4 status:** IMPLEMENTED / VERIFIED / COMMITTED

## 1. Commit identity

| Field | Value |
|---|---|
| Implementation commit | `027b796998af1d1232ef2341789a40ec616035e1` |
| Implementation parent | `a58c35a2b9d113f77877b2a86929443068bd2884` |
| Implementation commit subject | `E4: add integrated governed pilot` |
| Implementation file count | 5 |

## 2. Exact committed file set (five files)

```
backend/app/container.py
backend/app/main.py
backend/tests/test_e4_pilot_transport_v0_1.py
docs/ION_E4_INTEGRATED_GOVERNED_PILOT_CONTRACT_v1.md
docs/ION_E4_INTEGRATED_GOVERNED_PILOT_CLOSURE_2026-09-03.md
```

## 3. Committed blob identities

The committed Git blob identities are the authoritative durable identity.

```
backend/app/container.py
  blob OID = 11c252e5b92572aef82a78118b7fe28f3d128689
  bytes    = 5391
  sha256   = c16ea5f766d0caf4f5a8ed257c2162e60d5dba3ae7611255af5331e3bded9de6

backend/app/main.py
  blob OID = 5cc631216b37b4dda32a8cb1920c130b9a5daa69
  bytes    = 7575
  sha256   = 7c7187a2497e8e0e7fa1180aef4313cd13f035b0642db0ebf5403a8125e2c049

backend/tests/test_e4_pilot_transport_v0_1.py
  blob OID = 92a80013855fc5bd48285daab227057f640f72e2
  bytes    = 8793
  sha256   = 3ccd44c19b93d43a6f821a2184f3ed12b7ecb544653c3c8184678ed6ec4485b1

docs/ION_E4_INTEGRATED_GOVERNED_PILOT_CONTRACT_v1.md
  blob OID = 5f1e866d64a8ae91f9e0235495a9b3840ba95ed5
  bytes    = 11961
  sha256   = c0f73b35afd4e4039815461e26f887daeb6a3cad73dedf5ec3d2a63feeeeca81

docs/ION_E4_INTEGRATED_GOVERNED_PILOT_CLOSURE_2026-09-03.md
  blob OID = d499b77eba3d8116ec57f0f7a25e8705a55490a5
  bytes    = 20651
  sha256   = 0b1760629df32ae446e81e845ea5f0e4652399a68c7850640d7d23499c3e7ea4
```

## 4. Line-ending qualification

Two files were measured in the worktree before commit and produce a different
committed blob identity. Both measurements are correct; they measure different
objects.

```
backend/app/container.py
  worktree identity before commit = 5524 bytes
                                    69ee002a520f2b6eac3aac32c70e30277ac76d5a5f556cf496b38dfed02b42cf
  committed durable identity      = 5391 bytes
                                    c16ea5f766d0caf4f5a8ed257c2162e60d5dba3ae7611255af5331e3bded9de6

backend/app/main.py
  worktree identity before commit = 7777 bytes
                                    10dbb25c99c7c3791a433b7b843efdb4126a97c8e64c55b780bfe561945ff81e
  committed durable identity      = 7575 bytes
                                    7c7187a2497e8e0e7fa1180aef4313cd13f035b0642db0ebf5403a8125e2c049
```

Reason observed:

```
core.autocrlf = true
worktree CRLF normalized to LF in the committed blobs
```

Classification:

```
WORKTREE IDENTITY != DURABLE COMMITTED BLOB IDENTITY
```

No amend was performed. The E4E worktree measurements are **not** incorrect —
they remain correct measurements of the pre-commit worktree state.

## 5. Pilot transport

```
PILOT TRANSPORT = DEDICATED SESSION TRANSPORT
```

Routes:

```
POST /pilot/sessions
POST /pilot/sessions/{session_id}/turn
POST /pilot/sessions/{session_id}/close
```

Legacy transport:

```
POST /ask        = UNCHANGED
POST /ask/stream = UNCHANGED
```

Composition:

```
ONE PROCESS
  -> ONE SHARED CORE
      -> ONE SessionController
          -> MANY IN-MEMORY SESSIONS
```

```
PERSISTENT SESSION STORE = NONE
CONVERSATION MEMORY      = NONE
DialogueState FRAMEWORK  = NONE
```

## 6. Integrated path

```
USER / PILOT TRANSPORT
        |
        v
SessionController
        |
        v
Session admission
        |
        v
ActiveTurnReservation
        |
        v
AdaptiveDialogueEngine
        |
        v
CLARIFY | PROCEED

PROCEED
        |
        v
Core.ask
        |
        v
RetrievalPort
        |
        v
QdrantRetrieval
        |
        v
ACTIVE LOGICAL ALIAS
        |
        v
Core Adapter / governance
        |
        v
GovernedEvidenceSet
        |
        v
ModelContextAssembly
        |
        v
ModelGateway
        |
        v
STANDARD_GEMINI / SINGLE
        |
        v
renderer
        |
        v
TurnRecord
        |
        v
SessionTurnEntry
```

## 7. CLARIFY semantics

Preserved:

```
CLARIFY != AskResult
CLARIFY != failure
CLARIFY != TurnRecord
```

CLARIFY causes:

```
Core.ask            = 0
retrieval           = 0
governance          = 0
model execution     = 0
TurnRecord          = 0
SessionTurnEntry    = 0
ordinal             = UNCHANGED
reservation         = RELEASED
Session             = ACTIVE
```

No new dialogue semantics were introduced by E4.

## 8. Synthetic content — E4 content boundary

**E4 content is synthetic test/verification content only.**

```
E4 CONTENT = SYNTHETIC CLOSED-API PILOT PACK

pack_id                    = e4_synthetic_pilot_pack
pack_version               = 1.0.0
pack canonical fingerprint = 30c0a862e02524fb349ca5f198e2d6e1c84604aeb5076d46fbe72561148dac7e
source SHA256              = aff7fb1f9098ef89795e4b6467bc351c301433ad7b16617d9aad3b42395a05ca
```

```
CONTENT PACK #1 = NOT ENTERED
The Works       = NOT ENTERED / NOT SELECTED UNDER E4
```

## 9. E2 / E3 lifecycle proof

```
EXPECTED DERIVED INDEX             = e406986fbfbb4ccc21dbd9a47c3cebd745728b64d3c2d0b730ad9765a4915cc8
CANDIDATE MATERIALIZATION RECEIPT  = 44737caa003c842fe7db73c78dc65ec6b89a75ab8dbbd39007ab87bacfd86d08
MEASURED STATE                     = 09e26557e35c216f0ce549c26c2efe07fd02d482660cd03b4b03de9543ff0c33
VERIFICATION RECEIPT               = cbd8b55454442a190a709bce5f4e6f9421388d3913c847bc587301562b52944f

VERIFICATION STATUS = PASS
VERIFICATION SCOPE  = STRUCTURAL_V0_1

ACTIVATION RECEIPT          = a83c629dc5e5bfe52b8b35c46d8bf0b40ddfd9be282944a587fd5deec8d91845
ACTIVE LOGICAL ALIAS        = e4_pilot_active
ACTIVE PHYSICAL COLLECTION  = e4_pilot_candidate
ACTIVATION METHOD           = ALIAS_BOOTSTRAP_CREATE
PREVIOUS ACTIVE COLLECTION  = NONE
```

## 10. Disposable Qdrant proof

```
container     = e4d-disposable-qdrant
image tag     = qdrant/qdrant:latest
image digest  = sha256:75eab8c4ba42096724fdcfde8b4de0b5713d529dde32f285a1f86fdcb2c9e50c

Qdrant semantic server version = 1.18.2
server commit                  = 44ad62f8cd69642be5afa6441612525e24a0d063
version basis                  = INDEPENDENTLY MEASURED VIA GET /

persistent mounts               = NONE
PROJECT/LIVE QDRANT MUTATION    = NONE
DISPOSABLE QDRANT CLEANUP       = PASS
```

## 11. Provider qualification

```
EXECUTION PROFILE = STANDARD_GEMINI / 0.1 / SINGLE
DECLARED PROVIDER = gemini
DECLARED MODEL    = gemini-2.5-pro

AUTOMATED E4D EXTERNAL NETWORK PROVIDER = NONE
PROVIDER NETWORK SUBSTITUTE             = tests.fakes.FakeBackend
Substitution scope                      = GeminiBackend network/provider boundary only

LIVE GEMINI SMOKE = NOT EXECUTED / CREDENTIALS UNAVAILABLE

PROVIDER-REPORTED IMMUTABLE MODEL REVISION = UNBOUND
```

Not claimed by this closure:

```
real Gemini execution PASS       = NOT CLAIMED
Google executed gemini-2.5-pro   = NOT CLAIMED
provider model revision verified = NOT CLAIMED
```

## 12. Final corrected PROCEED identity

Authoritative bound E4 PROCEED turn identity:

```
e1c9fd83c0334b51abae1e64ae9f335f = FINAL CORRECTED E4D RUN / BOUND
7177d75707b44b5ba3861673954a75f4 = SUPERSEDED FIRST-RUN EVIDENCE / NOT BOUND
```

This classification is directional and must not be reversed.

## 13. PROCEED / CLARIFY / SESSION CLOSE proof

```
PROCEED = PASS

dialogue evaluations       = 1
decision                   = PROCEED / NO_RULE_TRIGGERED
Core.ask calls             = 1
retrieval calls            = 1
retrieval alias            = e4_pilot_active
governed candidates        = 5
GovernedEvidenceSet admitted = 5
rejected                   = 0
unknown                    = 0
ModelContext evidence count = 5
model executions           = 1
TurnRecord count           = 1
TurnRecord closure         = COMPLETED
SessionTurnEntry count     = 1
ordinal                    = 1
next ordinal               = 1 -> 2
RESPONSE-EVIDENCE SUBSET   = PASS
```

```
CLARIFY = PASS

reason_code             = QUESTION_HAS_NO_ANSWERABLE_CONTENT
Core.ask delta          = 0
retrieval delta         = 0
governance delta        = 0
model execution delta   = 0
TurnRecord              = 0
SessionTurnEntry        = 0
ordinal                 = UNCHANGED
Session                 = ACTIVE
```

```
SESSION CLOSE = PASS
```

No fabricated additional turn.

## 14. Active turn reservation qualification

E4D did **not** directly freeze and observe the `ActiveTurnReservation` object
mid-flight.

Observed integrated evidence includes:

```
reserved ordinal behavior
reservation release behavior
single ordinal commitment on PROCEED
no ordinal commitment on CLARIFY
```

Reservation-before-dialogue semantics remain independently closed by the
existing SessionController / E1 contract and tests.

```
CLASSIFICATION = NON-BLOCKING OBSERVABILITY QUALIFICATION
```

No direct mid-flight reservation snapshot is claimed.

## 15. Response-evidence qualification

```
CURRENT render_single AUTHORIZED-BASIS PATH = ACCEPTED FOR E4
Task17 ResponseEvidenceProjection           = PRESERVED / UNWIRED / REUSABLE

E4-R01 = renderer inline duplicate-candidate-id behavior differs from the
         Task17 fail-closed projector behavior

CLASSIFICATION = NON-BLOCKING FOR BOUNDED E4 SYNTHETIC PILOT

Synthetic document ids            = UNIQUE
Observed response-evidence subset = PASS
```

```
renderer change            = NONE
projector change           = NONE
semantic-equivalence claim = NONE
```

## 16. Test / regression record

```
E4C TARGETED TRANSPORT TESTS = 7 PASS / 0 FAIL
E4C T01-T18                  = EXECUTED / PASS

CURRENT PREPARED-ENVIRONMENT REGRESSION = 1393 PASS / 34 FAIL / 1 SKIP
POST-E4D                                = 1393 PASS / 34 FAIL / 1 SKIP
FAILURE SET DIFF                        = IDENTICAL

NEW E4C REGRESSION = NOT SUPPORTED
NEW E4D REGRESSION = NOT SUPPORTED
```

Historical E3 baseline remains, and must not be collapsed with the
prepared-environment state:

```
HISTORICAL E3 BASELINE = 1381 PASS / 33 FAIL / 7 SKIP
```

## 17. Q1 / Q2 / Q3 / Q4 — preserved, unrepaired

```
Q1 = PRE-EXISTING OVERLAY-DEPENDENT COLLECTION BLOCKER / UNREPAIRED
Q2 = PRE-EXISTING HISTORICAL BYTE-IDENTITY / CRLF QUALIFICATION / UNREPAIRED
Q3 = ION_REPO_ROOT ENVIRONMENT REQUIREMENT
Q4 = PRE-EXISTING TRANSPORT/API GOVERNANCE-FIXTURE FAILURE
     PREVIOUSLY SKIP-MASKED
     PROVEN PRESENT ON PRE-E4C HEAD
     NON-E4C / UNREPAIRED
```

Current measured protected-suite failure mechanism, where established:

```
CANONICAL_REJECTED / MISSING_PROVENANCE
```

These current failures must not be misclassified as CRLF without proof.

## 18. External E4D evidence identities

```
C:/Temp/e4d/lifecycle_evidence.json
  bytes  = 7578
  sha256 = 27626f8a1d374fae4c569c2628c329f1b0d869fb650c93c06efd3f23d101ae9d

C:/Temp/e4d/pilot_evidence.json
  bytes  = 5483
  sha256 = 2918e7452d836cddfac780736b492c536e43293d0cdd921391f76360e9bb5e77
```

Classification:

```
EXTERNAL SUPPORTING E4D EVIDENCE
```

These are **not** repository artifacts, **not** canonical Product objects, and
**not** durable Git blobs. They may remain external after E4G and were not
copied into the repository.

## 19. Core / session / dialogue identity precision

```
APP_VERSION     = 0.1.0
PRICING_AS_OF   = RUNTIME / PRODUCT METADATA ONLY
                  NOT pilot compatibility identity
```

Exact observed truth:

```
DEDICATED CODE-EXPORTED CORE CONTRACT-VERSION CONSTANT = NONE

Session runtime          = documented v0.1 / durable closed ancestry
Adaptive Dialogue runtime = documented v0.1 / durable E1 ancestry
```

No runtime version constants were invented.

## 20. No pilot framework

```
IntegratedPilotBinding production object = NONE
Pilot canonical fingerprint              = NONE
General Pilot framework                  = NONE
Pilot persistence                        = NONE
```

E4 durable identity is bound through:

```
repository implementation commit
  + committed blob identities
  + existing subsystem identities
  + E2/E3 lifecycle receipts
  + E4D runtime evidence
  + this durable closure artifact
```

## 21. Content Pack #1 boundary

```
CONTENT PACK #1 = NOT ENTERED

FIRST REAL DOMAIN CONTENT PACK = NEXT SEPARATE PRODUCT/CONTENT STAGE
                                 AFTER POST-E4 CONTROL RECONCILIATION
```

E4 does not select The Works. E4 does not authorize Content Pack #1 creation.

## 22. Ancestry chain bound by this closure

```
a58c35a2b9d113f77877b2a86929443068bd2884   (E3 durable closure / pre-E4 parent)
        -> 027b796998af1d1232ef2341789a40ec616035e1   (E4 implementation commit)
                -> <this closure commit>              (E4 durable closure binding)
```

Prior durable anchors (recorded here; ancestry is verified independently in the
E4G execution report):

```
e92fa8bc96bf29c659f72c824a88859bd21985d7
bbb226ccf10729a8cbdbb2d2456824f67fa100a7
a640dfa810b00044e472980bb8602ded0b2a0c6c
7cf6ba52557dd92c3f4c96a7edbdfbe9ade4d169
```

## 23. Execution-context qualification

Recorded as exact observed truth, not as a claim of conformance to the E4G
header's stated location:

```
E4G EXECUTION WORKTREE = .claude/worktrees/e4g-closure-binding-934661
E4G EXECUTION BRANCH   = claude/e4g-closure-binding-934661
```

The E4G header named worktree `e4c-bounded-integration-785cc0` / branch
`claude/e4c-bounded-integration-785cc0` as the execution destination. At E4G
execution time no such branch existed in the repository, and
`claude/e4g-closure-binding-934661` was the only branch pointing at the E4
implementation commit `027b796998af1d1232ef2341789a40ec616035e1`.

All E4G pre-binding Git identity gates — HEAD, HEAD parent, the
`e3-derived-index-lifecycle-20260903` durable predecessor target, clean tracked
worktree, no staged changes, no untracked non-ignored files, and the absence of
a pre-existing `e4-integrated-governed-pilot-20260904` ref — were verified and
passed exactly as specified.

```
REPOSITORY MOVEMENT = NONE
```

No reset, clean, checkout, switch, rebase, merge, cherry-pick, or stash was
performed.

## 24. Disposition

```
PROJECT-CONTROL:E4              = CLOSED / DURABLE / LOCALLY REFERENCED
INTEGRATED GOVERNED ION PILOT   = CLOSED / VERIFIED / DURABLE

SESSION / DIALOGUE / GOVERNED EXECUTION / CONTENT LIFECYCLE CONVERGENCE
                                = PROVEN

LIVE EXTERNAL GEMINI PROVIDER PROOF = NOT CLOSED / CREDENTIALS UNAVAILABLE
CONTENT PACK #1                     = NOT ENTERED
PUSH                                = NONE
```

No live provider proof is claimed. No push was performed.
