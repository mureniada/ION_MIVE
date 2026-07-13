# IVE Specification

## Definition

IVE means Intelligence Validation Engine.

An IVE is one complete, independent model interpretation of one canonical Context Pack.

## Independence

- Gemini IVE cannot read OpenAI IVE output.
- OpenAI IVE cannot read Gemini IVE output.
- Neither IVE performs cross-model comparison.
- Provider failures remain attributable to the provider path.

## Input

- user question;
- canonical Context Pack.

## Required output

- `engine_id`
- `provider`
- `model`
- `question`
- `abstract`
- `highlights`
- `claims`
- `concepts`
- `relations`
- `evidence_mapping`
- `uncertainty`
- `confidence`
- optional `raw_response`

## Claim contract

Each claim contains:

- `claim_id`
- `statement`
- `evidence_document_ids`
- `confidence`

## Concept contract

Each concept contains:

- `name`
- `description`

## Relation contract

Each relation contains:

- `source`
- `relation`
- `target`
- `evidence_document_ids`

## Normalization boundary

Provider-native output may vary.

Each provider adapter must normalize native output into the canonical IVE schema.

Provider-specific field names must not leak into MIVE.

## Validation

An IVE report is invalid when:
- required fields are absent;
- claims are not structurally valid;
- evidence IDs use unsupported types;
- confidence is outside 0–1;
- output is not valid JSON when JSON is required;
- the report cannot be normalized without guessing.

No fabricated repair of missing semantic content is allowed.
