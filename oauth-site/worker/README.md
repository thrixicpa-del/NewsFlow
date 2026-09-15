# NewsFlow YouTube OAuth Worker

This Worker is the HTTPS callback for NewsFlow channel access. It retains an encrypted token payload in D1 for at most ten minutes and deletes the payload after the desktop consumes it. It never stores a refresh token permanently.

## Configure

1. In the current Google Cloud project create an OAuth client of type **Web application**.
2. Add only this authorized redirect URI: `https://a.tinkbro.online/oauth/youtube/callback`.
3. Create a D1 database and put its `database_id` into `wrangler.jsonc`.
4. Run the migration and set secrets interactively:

```powershell
pnpm wrangler d1 migrations apply OAUTH_SESSIONS --remote
pnpm wrangler secret put GOOGLE_WEB_CLIENT_ID
pnpm wrangler secret put GOOGLE_WEB_CLIENT_SECRET
pnpm wrangler secret put SESSION_ENCRYPTION_KEY
pnpm wrangler deploy
```

Generate `SESSION_ENCRYPTION_KEY` as 32 random bytes encoded with base64url. Do not add a `.dev.vars` file, a downloaded Google JSON file, or any secret value to this directory.

The Worker must be attached to `a.tinkbro.online`. Its static asset binding serves the existing home page, privacy policy and terms pages; only `/oauth/youtube/*` is handled dynamically.
