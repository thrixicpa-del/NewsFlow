# Provider Failure Runbook

## Scope

This covers OpenAI/ChatGPT, FastGen/image, WProject/voice, YouTube/Google, and
other configured provider faults. It does not authorize changing credentials,
reissuing OAuth, or rerunning a job against production by default.

## Triage

1. Correlate the user action with the local redacted action trace from
   [[Observability]]. Preserve command, opaque action ID, durable job ID,
   provider class, status, and elapsed time; never copy secrets or responses
   into tickets/logs.
2. Classify the outcome: invalid request, authentication/authorization,
   quota/rate limit, transient network/timeout, provider partial result,
   artifact validation failure, or downstream publication failure.
3. Verify the current UI contract and worker path. A provider error must not
   cause fallback to a legacy provider, stale queue row, or unrelated retry.

## Safe response

- Retry only when the current job's durable identity and idempotency contract
  permit it; record attempts and preserve a valid existing artifact.
- For authentication faults, report the provider and non-secret remediation
  boundary. Do not expose or overwrite a token/key.
- For invalid media or output failures, validate the staged artifact and leave
  the prior good result untouched.
- For quota/rate limits, surface a retryable status without busy-looping or
  generating duplicate jobs.
- Exercise diagnosis with the provider-free controlled failure matrix before a
  live retry when possible.

## Verification

`tests/failure-matrix.json` maps simulated provider, retry, FFmpeg, restart,
and partial-result scenarios to isolated regressions. A real-provider check is
strictly opt-in (`NEWSFLOW_ENABLE_REAL_PROVIDERS=1`) and belongs only to an
authorized release/manual validation context.
