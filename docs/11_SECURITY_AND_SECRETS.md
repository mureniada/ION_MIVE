# Security and Secrets

## Required secret names

- `GEMINI_API_KEY`
- `OPENAI_API_KEY`
- vector-store URL/credentials when applicable

## Rules

1. Never commit `.env`.
2. Never commit frontend, Docker, or deployment secrets (`.env`, compose overrides, frontend env files).
3. Never print secret values.
4. Presence checks may print booleans only.
5. Validate that secrets contain valid header-safe characters before network calls.
6. Keep provider credentials out of logs and exception messages.
7. Use `.env` locally only through a documented loader.
8. Use platform secret management for cloud deployment.
9. Tests must use fake values and mocked network calls.
10. A missing secret must produce a clear configuration error.

## Import safety

Importing project modules must not:
- require secrets;
- open network connections;
- initialize external clients;
- validate cloud reachability.

External configuration and client creation occur at runtime when the relevant operation is invoked.
