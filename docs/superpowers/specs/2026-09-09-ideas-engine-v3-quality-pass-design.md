# Ideas Engine V3 Quality Pass Design

## Goal

Apply the approved editorial-quality pass without changing the established
`RAW SIGNAL → EVENT → MACRO EVENT → DIRECTION → TOPIC → ANGLE → TITLE →
PRODUCTION ITEM` architecture.

## Decisions

- A narrow Event Bundle admits one item by default. A second is admitted only
  for independently supported information payload and a substantially distinct
  future script; three or more require separately evidenced subevents,
  reactions, consequences, actors or evidence bundles.
- `script_overlap` is a deterministic comparison of event, payload, actors,
  chronology, consequence, expected payoff and script requirements. It is a
  hard production-duplicate gate, with diagnostics persisted on rejection.
- Scoring uses content-strength signals, not successful validation as a bonus.
  A 90+ click score requires high creative amplification or emotional stakes.
- Factual, editorial and hypothetical script policies are separate. An
  hypothetical candidate only requires a grounded base event and a visible
  uncertainty marker; its imagined future is not treated as a factual claim.
- CIS relevance must explain a causal connection in reader-facing language;
  global topics without a specific CIS consequence are not scored highly.
- A deterministic second pass rewrites over-limit question titles into a
  non-question structure and rescoring happens before rejection. The model
  prompt also asks for stronger alternative concepts in the prescribed hook
  families.

## Scope

Only `scriptor/idea_engine.py`, `scriptor/bridge.py`, the existing Ideas UI
contracts and Ideas tests change. All other NewsFlow subsystems remain out of
scope. The final V3 review samples at least 40 live candidates from seven
directions and stops the task for external review.
