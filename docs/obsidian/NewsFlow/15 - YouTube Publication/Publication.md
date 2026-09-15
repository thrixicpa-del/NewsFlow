# Publication

Publication V2 registry/snapshots/executions/receipts are canonical for the production UI. Existing OAuth, channel profiles, upload engine, title/description/tags/thumbnail/schedule/history and known `youtubeVideoId` must be retained. A retry after `youtubeVideoId` continues from the failed downstream stage and does not re-upload MP4.

## Preservation gate — 2026-09-11

Mocked Publication V2, publisher and OAuth-persistence regressions passed. A confirmed new-release cleanup preserves channels, OAuth tokens, analytics history, engagement policies and allocation presets; it clears only the explicitly designated production queue/artifact state. The renderer now sends the required confirmation phrase to the existing backend gate, so the visibly active action does not fail before the destructive confirmation reaches its canonical handler.

No upload, OAuth browser flow, YouTube API request or destructive cleanup was executed. Live external behavior is **NOT VERIFIED**.
