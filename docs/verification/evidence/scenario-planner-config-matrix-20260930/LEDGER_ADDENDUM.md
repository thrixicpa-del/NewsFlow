# Immutable evidence addendum: M2 attempt count

The original M2 capture contains one exported POST payload, one HTTP attempt, a `TimeoutError`, and no response/map. Its original logical ledger is `0` only because that harness appended the logical record after `client.generate()` returned. The correct audit count is **one logical generation attempt and one HTTP attempt**.

The current harness writes a pending logical record before transport and marks it `ERROR` on exception. That correction was tested offline; M2 was not resent. This addendum does not alter M2's original request, exception, response absence, or outcome.
