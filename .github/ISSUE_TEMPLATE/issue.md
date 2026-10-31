---
name: Issue
about: A bug, feature or review follow-up
title: ""
labels: []
assignees: []
---

## Problem

<!-- What's wrong or missing, and who it affects. For a bug: steps to
reproduce, what happens, and what should happen. -->

## Context

<!-- Current behavior with file references (`app/services/trip.py`,
`src/lib/data/mutations.ts`), related issues/PRs (#12,
Tom-Camp/bckpacking_ui#22), and the review finding it came from, if any. -->

## Brief

Branch: `ba-<n>-<slug>`, from `develop`

Change:
-

Tests:
-

Acceptance:
-

## Cross-repo impact

<!-- API: does OpenAPI change (new route, schema or field)? Does the nested
`GET /trips` shape change? Do any status codes change that the sync engine
relies on (404/409/422 drop an edit; 401 and 5xx keep it queued)?
UI: which API change must land first? Offline-capable or online-only?
Write "None" if neither applies. -->

## Open decisions

<!-- DECISION NEEDED: the question, then the options with the recommended
one first. Delete this section if there are none. -->
