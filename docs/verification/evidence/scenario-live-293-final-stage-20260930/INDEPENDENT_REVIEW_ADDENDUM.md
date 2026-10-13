# Independent-review addendum — A3 transmission and disclosure correction

This addendum records the independent reading review of
`scenario-live-293-a3-20260930-140000` at evidence commit
`d4bc0fd217a539200868ce53a33fbdabec87e97a`.  It does not modify the historical
scenario, Story Map, model-visible responses, or runtime behavior.  No
provider call was made for this addendum.

## Scope and limits

The review read the user-facing scenario, Planner and Writer post-adapter
requests, visible Planner/Writer responses, persisted map, ledgers, manifest,
and editorial audit.  It did not programmatically compare every JSON byte or
ZIP member, run the full application suite, or make paid calls.  Claims below
are therefore limited to the inspected evidence.

## Confirmed observations

1. The Planner post-adapter request supplies the exact title and the
   `12000` / `11500` / `12500` contract.  Its NewsFlow instructions require
   event-led material, allow DRAMATIZED content for this test, and give that
   allowance precedence over the manual template’s generic no-invention rule.
2. The weak material appears in the visible Planner response, not only after
   persistence.  In particular, A3/A4/P3 describes a delayed diplomatic
   outlook and an open question rather than a concrete terminal event.
3. The Writer requests visibly carry all 20 planned canonical event steps:
   P1 receives A1/A2 (10), P2 receives A3 (5), and P3 receives A4 (5).  The
   reading review found no sign that these event-step strings were truncated.
   This confirms transmission of weak material, not the quality of that
   material.
4. P3’s current purpose is itself analytic: it asks for a conclusion about
   peace being delayed and an open next-step question while its current target
   is approximately 3,998 characters.  That task originates in the Planner
   map despite the general event-first instructions.
5. The transport metadata/ledgers identify the Planner and all three Writers
   as `gpt-5.4-mini-2026-03-17` through `/v1/responses`.  The result is an
   observed failure of this model-plus-prompt configuration on this run; it is
   not evidence that the model fails for every configuration.
6. **Correction:** P1’s Writer instructions require one DRAMATIZED disclosure
   after the opening hook.  `response-02-visible.txt` begins directly with the
   attack narrative and contains no disclosure; `scenario.txt` contains none
   either.  The earlier `EDITORIAL_AUDIT.md` assertion that every opening
   disclosed the reconstruction was false and is corrected there.  The
   historical A3 text remains unchanged.
7. The response metadata reports `completed` with `incomplete_details=null`.
   P1/P2/P3 have 3,156 / 4,434 / 2,902 visible-response characters and
   777 / 1,038 / 707 output tokens respectively, with `max_output_tokens=5120`.
   These values do not indicate output-token truncation.
8. A2’s 12,226-character result demonstrates that this configuration can land
   in the requested aggregate range on one run.  It did not pass editorial
   acceptance, so it does not establish reliable quality.

## Result

The inspected A3 evidence shows that the title, event-first contract, and all
currently planned Writer material reached the model.  The Planner’s own
visible response nevertheless supplied an analytic P3 task, and P1 separately
missed its mandatory disclosure instruction.  This is an evidence correction
and diagnostic finding only: it creates no new runtime quality blocker,
Writer regeneration, model switch, or paid-call authorization.
