# ION E1 — Durable Closure Binding

**Date:** 2026-09-03
**Type:** Control artifact. Binds E1 closure to durable Git object identities.
**Authority:** E1.8 final durable closure binding authorization.

---

## 1. Gate state

```
E1.1  = CLOSED / APPROVED
E1.2  = CLOSED / APPROVED
E1.3  = EXECUTED
E1.4  = EXECUTED
E1.5  = VERIFIED
E1.6  = PASS
E1.6A = PASS
E1.7  = PASS
```

## 2. Commit binding

```
QUALIFIED PRE-E1 BASELINE       = 4d5a5000da92cc52cf22115b659d5a2138c6512e
E1 IMPLEMENTATION COMMIT        = 1a731e7deb81bcdfd64518c02c65484fd8ed9adc
E1 IMPLEMENTATION COMMIT PARENT = 4d5a5000da92cc52cf22115b659d5a2138c6512e
COMMITTED E1 FILE COUNT         = 11
```

The implementation commit carries a `Co-Authored-By` trailer, ratified under
E1.8 as non-substantive commit provenance. No amend was performed.

## 3. Verification state

```
TARGETED TESTS             = 116 PASS / 0 FAIL
BOUNDED REGRESSION         = 211 PASS / 3 QUALIFIED NON-E1 FAILURES
NEW E1 SEMANTIC REGRESSION = NOT SUPPORTED
NEW E1 WIRING REGRESSION   = NOT SUPPORTED
```

The three qualified failures are in `backend/tests/test_core_ask_mocked.py`,
caused by the tracked `runtime_evidence_bridge` rejecting that module's
in-memory fixtures for missing provenance. Proven non-attributable to E1: no
E1-modified module appears in that test module's import closure. Deliberately
not repaired. They remain an open item requiring their own operator decision.

## 4. Contract status

```
TASK23 HISTORICAL CONTRACT            = PRESERVED
E1 ADDENDUM                           = AUTHORITATIVE POST-TASK23 AMENDMENT
TASK23 CONTRACT-AMENDMENT REQUIREMENT = SATISFIED
```

## 5. Pre-existing overlay

```
PRE-EXISTING OVERLAY = 4 FILES / NON-E1 / UNCHANGED / NOT COMMITTED
```

```
backend/app/modules/admission/receipts.py
backend/app/modules/retrieval/source_provenance_manifest.py
backend/t4/contract/STATUS.md
schemas/ion_evidence_record_v0.1.schema.json
```

Never modified, never staged, never committed, never attributed to E1.

---

## 6. Portable artifact identity

### 6.1 Why worktree hashes are not durable identities

This repository converts line endings on checkout. A file's bytes **in the
working tree** are therefore not necessarily its bytes **in the Git object
store**, and a SHA256 taken from disk is an execution-environment observation,
not a portable identity.

```
WORKTREE SHA256  !=  PORTABLE COMMITTED-CONTENT IDENTITY
    (when line-ending conversion is enabled)
```

This is recorded as an observed fact, not a prediction. At the time of this
binding, on this host, the divergence was measured directly:

- all **9 E1 code/test files** are CRLF in the working tree and LF in the Git
  object store — their worktree SHA256 values **do not** equal their
  committed-content SHA256 values;
- both **E1 Markdown artifacts** were authored LF and stored LF — their
  worktree SHA256 values **did** equal their committed-content SHA256 values
  when measured. That equality is incidental to this checkout, not a
  guarantee: a future checkout may materialize them as CRLF, after which the
  worktree hash would no longer match.

**The committed-content identities in §6.2 and §6.3 are the durable ones.** Any
integrity check should read Git object content (`git cat-file blob <oid>`), not
the checked-out file.

### 6.2 E1 durable artifacts — committed-content identity

Bound to commit `1a731e7deb81bcdfd64518c02c65484fd8ed9adc`.

**`docs/ION_E1_ADAPTIVE_DIALOGUE_RUNTIME_INTEGRATION_ADDENDUM_v1.md`**
```
GIT BLOB OID              = e2503e1b45c3e7951478ab6d0c1274d3dd2d0cbf
COMMITTED-CONTENT SHA256  = 16B34CED861089E155C3FDB8BFBB0EF05D22E1F4900D4D04F3E5C87A3083F94A
COMMITTED BYTES           = 9377
```

**`docs/ION_E1_MINIMAL_ADAPTIVE_DIALOGUE_RUNTIME_CLOSURE_2026-09-03.md`**
```
GIT BLOB OID              = f269d535376dd9de7b547ab3bc1aa24c8abbbcc1
COMMITTED-CONTENT SHA256  = 2464750D2ECE06A0001BD1D9E5E3093C6769C98712377EAB458567B1D6182236
COMMITTED BYTES           = 10706
```

### 6.3 E1 code and test files — committed-content identity

Bound to commit `1a731e7deb81bcdfd64518c02c65484fd8ed9adc`.

```
BLOB OID                                  COMMITTED-CONTENT SHA256                                          PATH
cb6ad9c1f62b14b48c358281b37bb877eaeb2157  ED255C94CD2ECA445D03D4DA763D12B07B3F9102605C61D90E08D94E267CCDF5  backend/app/modules/adaptive_dialogue/__init__.py
9cc13e93f60fa33654ed9b910d17b7aed37be9cc  19D3FC3156A0D88052829F5E5072AF1DACFE6B6D89FB3EB394F3565B703A678D  backend/app/modules/adaptive_dialogue/engine.py
ac7644d0dc26b70d2048ed00248efa5882f6a930  C00967EFC9824C2AF8D19B24F5C988E5960B2D7C03B1EC74E3D1927CCDA1AE7D  backend/app/modules/adaptive_dialogue/models.py
744aca58e9aa128fc2938181bc69348217f6498a  10D5D32F926F988CDF16C9F38B65AEE569985B66884A9E3A3063333287D57776  backend/app/modules/session/__init__.py
bfb12278fc319c4e55ee176200be6cfa8bd1add4  FAB87761EC3B7A7B9B76CD249ED91C7A7F6A4696BF3CA4A800E4D9B221A1E904  backend/app/modules/session/controller.py
281aeac76029f34fd0df4115b5f793c035859c04  F0842740CDC6274053736D9DEE002BE869BB6072AEB00BDFDDF2940C685E7A09  backend/tests/test_adaptive_dialogue_engine_v0_1.py
f8bf4e43f7adef50c77661e432be7b0ab752af50  6C7D433EABB479776C40007ADA89A4C9AA0D67C27FAF5C713970BF66F71B85D8  backend/tests/test_adaptive_dialogue_models_v0_1.py
4f5c57bc61a989db39cfd549936312fa0f4e67d7  4DC3557294BD0D286840734C87A9AE951857832361D73808AD7332812BDA3503  backend/tests/test_session_controller_v0_1.py
089f43e90650760b2c2b207c74a446e57521daea  B3479CA0B328D2B6420C86B17EE65840CAABE03C84E4FEEE7509DC2BF69FAECD  backend/tests/test_session_models_v0_1.py
```

### 6.4 Superseded non-portable hashes

The following worktree SHA256 values were recorded during E1.6 / E1.6A / E1.7
execution. They are retained as **historical execution-environment hashes**
only.

```
NON-PORTABLE — WORKTREE BYTES ON THE E1 EXECUTION HOST — DO NOT USE FOR INTEGRITY VERIFICATION
```

```
E0F7F363644F9F3C5F8C70BCABC9F2312F1995D55B53CF8BE6E6B30241C77396  backend/app/modules/adaptive_dialogue/__init__.py
A85CBEF7B7CF161EB65E39DDBFB3404D232B247B968DC44CB770582686DCD563  backend/app/modules/adaptive_dialogue/engine.py
D4DB65EF7A0688AD0A73082413F783A3C9B45784555B517ACD2B856D184C0AA5  backend/app/modules/adaptive_dialogue/models.py
5167C637E66CD2FC00B4FD8309BD86033E4C21E396A8B94109D914065797FF5D  backend/app/modules/session/__init__.py
56B188CD36CAF54A68110F6782963F76D2533CBC307D5406EDB87381ED890CCD  backend/app/modules/session/controller.py
5901CC10021F18DC64E0451F37EE7CDB7503BA1DC9B6DF24F8D2D2082B3E5CCD  backend/tests/test_adaptive_dialogue_engine_v0_1.py
197C947CACD05AB48E40D3ECC1B92B6B810E63172ACB858809B0EE45082B90A6  backend/tests/test_adaptive_dialogue_models_v0_1.py
5910662BECB0AB3ADDD4F3221CC92241FA3F022B64D8AF09131C35CF35BA492B  backend/tests/test_session_controller_v0_1.py
A8ED3B9C200D800ED252B34DAB8FA0A130050721B4781BEE78EB03098BBA4C13  backend/tests/test_session_models_v0_1.py
```

The four pre-existing overlay hashes recorded in the closure receipt §11.4 are
worktree hashes of **untracked** files. They have no Git object identity by
definition, remain valid as observations of those files on this host, and are
unaffected by this correction.

---

## 7. Final state

```
PUSH = NONE
E2   = BLOCKED / NOT STARTED
```

HEAD is detached. No branch was created, and no repository movement occurred
beyond the normal HEAD advancement caused by the two authorized commits.

Nothing in this artifact constitutes a push, tag, release, deployment, or
authorization to begin E2.
