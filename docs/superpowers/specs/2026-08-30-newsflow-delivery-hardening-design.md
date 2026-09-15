# NewsFlow Delivery Hardening Design

## Purpose

Make the current NewsFlow desktop application reliable as a visible end-to-end workflow: generating realistic news covers, preparing publishable YouTube packages, connecting a channel, scheduling uploads, and showing the operator exactly what has happened.

## Scope

This design covers the existing NewsFlow application only. It preserves local project data, OAuth tokens, Chrome profiles, channel allocation presets, and analytics history. It does not publish a video publicly without a separate explicit operator confirmation.

Automated imitation of human viewers through random comments, likes, or viewing is intentionally excluded. The application may assist with genuine publishing, channel analytics, and opening Creator Studio, but must not impersonate normal audience engagement.

## User-visible channel flow

1. The operator imports one shared Google OAuth Desktop Client JSON.
2. The operator presses **Add channel**, sees an inline form, and creates a visible row.
3. The operator presses **OAuth** for that row and completes the Google consent flow in the selected channel account.
4. NewsFlow fetches and stores the actual YouTube channel ID, name, avatar, subscriber count, and token in the row's persistent Chrome profile.
5. **Open Studio** opens `studio.youtube.com/channel/<channelId>` using exactly that profile. Before OAuth it opens Studio sign-in.
6. A free-text operator tag is stored with the row and never changes the connected YouTube identity.

## Publication flow

Ready result folders provide MP4, duration, thumbnail, scenario title, SEO title, SEO description, SEO phrases, and tags to the publication queue. A scenario title longer than 100 characters is blocked from upload and must be rewritten through a visible action before it becomes ready.

Tags are normalized at queue creation and immediately before upload: blank and duplicate tags are removed, then whole tags are retained in order until their comma-separated YouTube string is no longer than 500 characters. No tag is cut in the middle.

Each upload remains a private draft unless a schedule is set. The queue preserves channel assignment, schedule, selected thumbnail, SEO data, and upload result. A paired Community post is prepared with SEO description, a call to action, and the video URL, with hashtag tokens removed. Because the public YouTube API does not publish Community posts, NewsFlow must present copy/open-Studio/mark-published controls rather than claim the post was sent automatically.

Suggested mid-roll positions at 39-second intervals are a Studio checklist only; NewsFlow does not claim to set advertising markers through an unsupported public API.

## Cover and FastGen contract

Every saved cover prompt begins with the real-photo/news contract. The scene must be tied to the supplied topic; people, conflict, missiles, explosions, emergency services, flags, press, or leaders are included only when the topic supports them. The prompt rejects illustration, CGI, 3D, paintings, generic speculative scenes, invented war rooms, and text baked into the source image.

The local compositor reserves a background zone only underneath the local headline/subheadline, keeps the scene visible outside it, fits a selected portrait without covering the middle of the frame, and sends normalized reference images below the FastGen size limit. One requested prompt produces one expected variant; partial provider results are retried only for missing variants. Current and new-prompt regeneration retain the route and chosen model.

## Interface integrity

Only active navigation routes may contain actionable controls. Retired components with disabled controls are removed. Remaining disabled controls must explain the missing prerequisite and become enabled only when it is satisfied. System prompt dialogs in publication are replaced by visible forms.

## Validation

Automated tests cover channel creation, OAuth metadata persistence, Studio URL/profile selection, 100-character titles, 500-character tag normalization, post preparation, scheduling and allocation. The TypeScript client passes `pnpm typecheck`.

The Python test environment must include the declared image dependencies and NumPy before running the complete suite. The final portable application is checked for core startup, UI typecheck, and a non-public end-to-end test path; actual YouTube upload uses only a private test draft and requires a connected channel.
