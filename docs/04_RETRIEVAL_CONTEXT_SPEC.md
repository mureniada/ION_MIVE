# Retrieval and Context Pack Specification

## Retrieval responsibility

Retrieval stores and returns evidence. It does not interpret the evidence.

## Minimum retrieved evidence fields

Each retrieved item must expose:

- `document_id`
- `source_id`
- `title`
- `content`
- `score`
- optional `page`
- optional `chunk_id`
- optional metadata

## Retrieval requirements

- deterministic validation of question and `top_k`;
- configurable embedding model;
- versioned collection/index identity;
- explicit similarity score;
- no secrets loaded merely by importing the retrieval module;
- configuration validation at runtime before actual external calls;
- useful error messages;
- no hidden fallback corpus;
- no silent empty-success state.

## Canonical Context Pack

Both Gemini and OpenAI receive the same Context Pack.

Required fields:

- `context_pack_id`
- `question`
- `documents`
- `metadata`

Each document contains:

- `document_id`
- `title`
- `content`
- `source`
- optional `page`
- optional `chunk_id`

## Context Pack invariants

1. No reasoning is performed while constructing it.
2. Provider-specific prompt content is not stored inside it.
3. Its document identifiers remain stable through IVE and MIVE.
4. Context size must be measurable.
5. Truncation, if required, must be explicit and recorded.
