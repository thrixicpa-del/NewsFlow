# Public OAuth site for NewsFlow

## Purpose

Provide the public, HTTPS-hosted information pages Google requires before
publishing and verifying the NewsFlow OAuth application. The site explains the
desktop product and discloses its YouTube OAuth data handling without claiming
features the product does not provide.

## Scope

The deliverable is a standalone static site ready for Cloudflare Pages Direct
Upload. It contains no analytics, cookies, third-party trackers, sign-up forms,
or server-side code.

Routes:

- `/` — concise Russian landing page explaining that NewsFlow is a desktop
  workspace for preparing, scheduling, publishing and measuring YouTube
  content only after the operator connects a channel through Google OAuth.
- `/privacy/` — Russian privacy policy covering local OAuth token storage,
  access scopes, use, retention, user controls, deletion and contact.
- `/terms/` — Russian terms of use that state the operator is responsible for
  channel access, YouTube policy compliance and published materials.
- `/404.html` — small navigable missing-page state.

## Content and compliance

- Contact address: `mariaplusize22@gmail.com`.
- The policy explicitly names YouTube Data API and YouTube Analytics API.
- It says NewsFlow accesses the minimum data authorised by the operator: channel
  identity and public statistics; upload/scheduling metadata and files; and
  analytics. Financial analytics is requested only when the operator explicitly
  enables it.
- OAuth tokens are stored locally on the operator's computer in NewsFlow's
  application data; the static website does not collect or receive them.
- The privacy policy says users can revoke access in their Google Account and
  remove a channel in NewsFlow. It avoids unsupported claims such as encryption
  at rest or automatic browser publishing of community posts.

## Visual direction

The visual system echoes the NewsFlow desktop UI rather than a generic SaaS
landing page: deep navy panels, electric blue for actions, restrained cyan
rules and warm white text. The distinctive element is a vertical "signal path"
on the home page: channel → NewsFlow → scheduled YouTube publication. It is an
explanatory diagram, not decorative animation.

- Display: `Manrope`; body: `Inter`; system fallbacks remain usable offline.
- Responsive single-column reading layout on small screens.
- Visible focus states, semantic landmarks, meaningful page titles and no
  interaction required to read policy text.
- Reduced-motion users receive no animated path.

## Deployment and domain

The static output will be uploaded with Cloudflare Pages Direct Upload. The
operator will then connect `tinkbro.ru` as the custom domain and verify domain
ownership in Google Search Console. Google Auth Platform fields will use:

- Home page: `https://tinkbro.ru/`
- Privacy policy: `https://tinkbro.ru/privacy/`
- Terms of service: `https://tinkbro.ru/terms/`
- Authorized domain: `tinkbro.ru`

## Verification

Before delivery, a local static-server smoke check will request all four routes
and confirm status 200 for the three policy pages and 404 for the missing-page
route. HTML will be checked for page titles, navigation links and required
privacy-policy disclosures. The user will perform the external Cloudflare
upload, custom-domain connection and Google Search Console verification because
they require the user's Cloudflare and domain-DNS accounts.
