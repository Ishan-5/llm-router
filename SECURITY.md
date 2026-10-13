# Security policy

## Supported versions

| Version | Supported |
|---|---|
| `main` — the deployed API, dashboard and CLI (`routewise` 0.2.x) | ✅ |
| Older commits and self-hosted forks | ⚠️ best-effort, please reproduce on `main` first |

## Reporting a vulnerability

Please report privately — **not** in a public issue.

- Open a [private security advisory](https://github.com/Ishan-5/llm-router/security/advisories/new)
  (repo **Security** tab → *Report a vulnerability*).

Please include what you can of:

- a description of the issue and its impact,
- steps to reproduce (endpoint, request, or a minimal script),
- the affected surface (API / dashboard / CLI / SDK) and version or commit,
- any suggested fix.

**Never** include real API keys, `.env` contents, or user data in a report.

## What to expect

This is a single-maintainer project with no formal SLA. Reports are acknowledged
on a **best-effort basis, typically within ~72 hours**, and you'll be kept updated
until the issue is resolved. Please give us a chance to fix it before public
disclosure; once a fix ships we're happy to credit you if you'd like.

## Scope

**In scope**

- API-key handling — user keys are used per-request and never persisted.
- Authentication, authorization and per-key data isolation.
- Prompt-injection detection and PII-sanitization bypasses.
- SSRF in webhook validation or any server-side fetch.
- Rate-limit or budget-cap bypass.

**Out of scope**

- Self-hosted deployments misconfigured by the operator.
- Vulnerabilities in third-party providers (OpenAI, Groq, OpenRouter, Gemini,
  DeepSeek, Mistral, Perplexity, xAI, Tavily, Ollama).
- Issues that require an already-compromised device or a leaked key.

## Safe harbour

We will not pursue legal action for good-faith security research that follows
this policy. Please act in good faith, avoid privacy violations and service
disruption, and only interact with accounts you own or have permission to test.
