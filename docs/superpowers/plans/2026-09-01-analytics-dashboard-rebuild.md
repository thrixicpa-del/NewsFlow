# Analytics Dashboard Rebuild Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver a modern, separate analytics dashboard with date and revenue filters plus an accurate summary grid for all selected channels.

**Architecture:** Move date parsing and aggregation from the React component into a pure Python dashboard module, then expose one filtered analytics payload through the bridge. Keep raw metric points untouched in Settings; client components only render the supplied totals, coverage and series.

**Tech Stack:** Python 3.12, dataclasses, unittest, React/TypeScript, existing Analytics API cache.

**Spec:** `docs/superpowers/specs/2026-09-01-youtube-posts-cards-end-screens-design.md`

## Global Constraints

- Support current month, previous month, 30 days, 90 days, and timezone-aware custom inclusive-start/exclusive-end periods.
- Revenue must be `Нет доступа` for no coverage and `Частичный доступ` for mixed coverage; never imply unavailable revenue is zero.
- Totals include only the selected channels and period; show channel count separately.
- Raw OAuth token data and browser-profile details never appear in analytics payloads.
- Keep OAuth connection/recovery controls available but outside the primary metrics flow.

---

### Task 1: Create pure filter and calculator functions

**Files:**
- Create: `scriptor/analytics_dashboard.py`
- Modify: `tests/test_youtube_publisher.py` or create `tests/test_analytics_dashboard.py`

**Interfaces:**
- Defines `resolve_period(kind: str, now: datetime, custom_start: datetime | None = None, custom_end: datetime | None = None) -> tuple[datetime, datetime]`.
- Defines `build_dashboard(points: Sequence[AnalyticsMetricPoint], channels: Sequence[Mapping[str, object]], channel_ids: Sequence[str], revenue_filter: str, start_at: datetime, end_at: datetime) -> dict`.

- [ ] **Step 1: Write failing date/revenue coverage tests**

```python
def test_previous_month_is_calendar_month_not_last_thirty_days():
    start, end = resolve_period("previous-month", datetime(2026, 9, 18, tzinfo=UTC))
    assert (start.isoformat(), end.isoformat()) == ("2026-08-01T00:00:00+00:00", "2026-09-01T00:00:00+00:00")

def test_dashboard_marks_partial_revenue_without_hiding_nonfinancial_totals():
    dashboard = build_dashboard(points, channels, ["a", "b"], "all", start, end)
    assert dashboard["totals"]["views"] == 320
    assert dashboard["revenue"]["state"] == "partial"
    assert dashboard["totals"]["revenue"] == 12.5
```

- [ ] **Step 2: Run to verify failure**

Run: `py -3 -m unittest tests.test_analytics_dashboard -v`

Expected: FAIL because the module does not exist.

- [ ] **Step 3: Implement validation and aggregation**

Normalize channel IDs, reject unknown period names and naïve custom times, filter `monetized`, `without-revenue`, and `all` based on actual financial coverage. Return `filters`, `totals` (`channelCount`, `views`, `subscribers`, `publications`, `watchHours`, `revenue`), chronological `series`, and explicit revenue coverage labels.

- [ ] **Step 4: Run pure calculator tests**

Run: `py -3 -m unittest tests.test_analytics_dashboard tests.test_youtube_publisher -v`

Expected: PASS.

### Task 2: Add one bridge query for filtered analytics

**Files:**
- Modify: `scriptor/bridge.py: snapshot and command dispatcher`
- Modify: `studio-ui-remotion-verify/src/desktop.d.ts`
- Test: `tests/test_analytics_dashboard.py`

**Interfaces:**
- Adds `get-analytics-dashboard(payload: dict) -> dict` with `channelIds`, `period`, `revenueFilter`, `customStart`, `customEnd`.
- Return shape is `{analyticsDashboard: {filters, totals, revenue, series, channels, updatedAt}}`.

- [ ] **Step 1: Write failing bridge command test**

```python
def test_bridge_dashboard_filters_selected_monetized_channels_for_current_month():
    result = bridge.get_analytics_dashboard({"channelIds": ["money"], "period": "current-month", "revenueFilter": "with-revenue"})
    assert result["analyticsDashboard"]["totals"]["channelCount"] == 1
    assert result["analyticsDashboard"]["revenue"]["state"] == "available"
```

- [ ] **Step 2: Run to verify failure**

Run: `py -3 -m unittest tests.test_analytics_dashboard.AnalyticsBridgeTests -v`

Expected: FAIL because the command is absent.

- [ ] **Step 3: Convert persisted points to factual metric objects and return safe payload**

Use `youtube_analytics_metric_points` and channel `monetary_access` only. Keep missing data explicit. Do not mutate cache when querying filters; use `refresh-analytics` only for external refresh.

- [ ] **Step 4: Run bridge and old analytics tests**

Run: `py -3 -m unittest tests.test_analytics_dashboard tests.test_youtube_publisher -v`

Expected: PASS.

### Task 3: Extract the modern Analytics workspace

**Files:**
- Create: `studio-ui-remotion-verify/src/ui/analytics/AnalyticsWorkspace.tsx`
- Modify: `studio-ui-remotion-verify/src/ui/App.tsx: AnalyticsDashboard route wrapper`
- Modify: `studio-ui-remotion-verify/src/ui/analytics.css`
- Modify: `studio-ui-remotion-verify/src/desktop.d.ts`

**Interfaces:**
- `AnalyticsWorkspace({data, command})` owns local filter state and calls `get-analytics-dashboard`.
- `AnalyticsSummaryGrid({totals, revenue})` renders count, views, subscribers, publications, watch hours and revenue.

- [ ] **Step 1: Add a failing UI scenario**

```tsx
render(<AnalyticsWorkspace data={snapshot} command={command} />)
await user.selectOptions(screen.getByLabelText("Период"), "previous-month")
expect(command).toHaveBeenCalledWith("get-analytics-dashboard", expect.objectContaining({period: "previous-month"}))
expect(screen.getByText("Частичный доступ")).toBeVisible()
```

- [ ] **Step 2: Run to verify failure**

Run: `npm test -- --runInBand` from `studio-ui-remotion-verify`, or add the same behavior to `tests/manual-ui-checks.md` if no frontend runner is configured.

Expected: FAIL or missing behavior.

- [ ] **Step 3: Implement filters and calculator grid**

Render multiselect channel chips, period presets, custom start/end inputs and revenue availability filter above the grid. Keep `Обновить данные` as an explicit green action. Use a full-width dashboard layout: summary grid, line chart, then compact channel/video tables. Put OAuth setup and channel management in a collapsed `Каналы и доступ` panel.

- [ ] **Step 4: Apply modern accessible styling**

Replace dense table-first styling with responsive cards and clear spacing. Use semantic blue/green/amber/red tokens, visible focus states, text status labels, and a two-column tablet/one-column mobile grid.

- [ ] **Step 5: Verify dashboard behavior**

Run: `py -3 -m unittest tests.test_analytics_dashboard tests.test_youtube_publisher -v`

Expected: PASS. Run frontend checks/build and visually verify each period preset, a custom period, full/no/partial revenue coverage, and all-channel totals.
