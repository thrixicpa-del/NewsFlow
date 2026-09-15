# NewsFlow OAuth Site Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a Russian static public website for `tinkbro.ru` that supports NewsFlow's Google OAuth production verification.

**Architecture:** A dependency-free static directory is the deployable unit for Cloudflare Pages Direct Upload. Each public route has its own HTML document and shares one CSS file; a standard-library test reads rendered files and verifies route, navigation, accessibility and required policy disclosures without requiring a browser or cloud credentials.

**Tech Stack:** HTML5, CSS3, Python standard-library `unittest`, Cloudflare Pages Direct Upload.

**Spec:** `docs/superpowers/specs/2026-08-31-newsflow-oauth-site-design.md`

## Global Constraints

- Create only static files: no trackers, cookies, forms, server-side code or external fonts.
- All visible text is Russian except Google and YouTube product names.
- Use the contact address `mariaplusize22@gmail.com`.
- Do not claim encryption, automatic community-post publishing, or capabilities absent from NewsFlow.
- Keep the three Google Auth URLs exactly: `/`, `/privacy/`, `/terms/`.
- Make the site responsive, keyboard navigable, with visible focus and reduced-motion support.
- The workspace is not a Git repository; record verification commands instead of commits.

---

### Task 1: Static-site structure and shared visual system

**Files:**
- Create: `oauth-site/assets/site.css`
- Create: `oauth-site/index.html`
- Test: `tests/test_oauth_site.py`

**Interfaces:**
- Produces a document at `oauth-site/index.html` that imports `/assets/site.css` and links `/privacy/` and `/terms/`.
- Produces a shared stylesheet consumed by every page through `<link rel="stylesheet" href="/assets/site.css">`.

- [ ] **Step 1: Write the failing structural test**

```python
def test_home_page_has_newsflow_identity_and_policy_navigation(self):
    page = read_site("index.html")
    self.assertIn("<title>NewsFlow", page)
    self.assertIn('href="/privacy/"', page)
    self.assertIn('href="/terms/"', page)
    self.assertIn('href="/assets/site.css"', page)
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `python -m unittest tests.test_oauth_site.OAuthSiteTests.test_home_page_has_newsflow_identity_and_policy_navigation -v`

Expected: FAIL because `oauth-site/index.html` does not exist.

- [ ] **Step 3: Create the minimal home page and stylesheet**

Create a semantic `<header>`, `<main>` and `<footer>`. The home page must state that NewsFlow is a local desktop workspace for preparing, scheduling, uploading and measuring YouTube publications after the operator grants OAuth access. Add the signal-path diagram as plain text with three steps: `Канал → NewsFlow → Публикация`. Include `lang="ru"`, a viewport tag, a meaningful title and links to policy and terms.

Create CSS custom properties for navy, blue, cyan, warm white and muted text. Implement `:focus-visible`, a `max-width` reading column, responsive layout below `640px`, and `@media (prefers-reduced-motion: reduce)` that disables transitions.

- [ ] **Step 4: Run the structural test to verify it passes**

Run: `python -m unittest tests.test_oauth_site.OAuthSiteTests.test_home_page_has_newsflow_identity_and_policy_navigation -v`

Expected: PASS.

- [ ] **Step 5: Record the checkpoint**

Run: `Get-ChildItem oauth-site -Recurse -File`

Expected: `index.html` and `assets/site.css` are present. Do not commit because this workspace has no Git repository.

### Task 2: Privacy policy and terms

**Files:**
- Create: `oauth-site/privacy/index.html`
- Create: `oauth-site/terms/index.html`
- Modify: `tests/test_oauth_site.py`

**Interfaces:**
- Produces privacy and terms documents at the exact paths linked from the home page.
- Every document uses the shared stylesheet and has a link back to `/`.

- [ ] **Step 1: Extend tests with the required data-handling disclosure**

```python
def test_privacy_page_explains_google_data_and_user_controls(self):
    page = read_site("privacy/index.html")
    for required in (
        "YouTube Data API", "YouTube Analytics API",
        "локально на компьютере", "Google Аккаунте",
        "mariaplusize22@gmail.com", 'href="/"',
    ):
        self.assertIn(required, page)

def test_terms_page_links_back_and_names_channel_responsibility(self):
    page = read_site("terms/index.html")
    self.assertIn("ответственность", page.casefold())
    self.assertIn("YouTube", page)
    self.assertIn('href="/"', page)
```

- [ ] **Step 2: Run the two new tests to verify they fail**

Run: `python -m unittest tests.test_oauth_site.OAuthSiteTests.test_privacy_page_explains_google_data_and_user_controls tests.test_oauth_site.OAuthSiteTests.test_terms_page_links_back_and_names_channel_responsibility -v`

Expected: FAIL because the two route documents do not exist.

- [ ] **Step 3: Create the policy documents**

Write the privacy policy with sections: data accessed, purpose, local storage, user controls, retention/deletion and contact. State that OAuth tokens and publication metadata are stored by NewsFlow locally on the operator's computer; the website itself does not collect OAuth tokens. State that users can revoke Google OAuth access in their Google Account and remove a channel in NewsFlow.

Write terms covering operator responsibility for channel permissions, content legality, YouTube policies and third-party rights. Do not promise uninterrupted service or make legal claims not supported by the product.

- [ ] **Step 4: Run policy tests to verify they pass**

Run: `python -m unittest tests.test_oauth_site.OAuthSiteTests.test_privacy_page_explains_google_data_and_user_controls tests.test_oauth_site.OAuthSiteTests.test_terms_page_links_back_and_names_channel_responsibility -v`

Expected: PASS.

- [ ] **Step 5: Record the checkpoint**

Run: `Get-ChildItem oauth-site\privacy,oauth-site\terms -Recurse -File`

Expected: one `index.html` in each route directory.

### Task 3: Missing-page state and deploy instructions

**Files:**
- Create: `oauth-site/404.html`
- Create: `oauth-site/README.md`
- Modify: `tests/test_oauth_site.py`

**Interfaces:**
- `404.html` is a navigable document with the shared stylesheet and a root link.
- `README.md` gives a human-safe Cloudflare Pages Direct Upload and custom-domain procedure without credentials.

- [ ] **Step 1: Add the failing 404 and route test**

```python
def test_all_public_documents_have_titles_styles_and_root_navigation(self):
    for relative in ("index.html", "privacy/index.html", "terms/index.html", "404.html"):
        page = read_site(relative)
        self.assertIn("<title>", page)
        self.assertIn('href="/assets/site.css"', page)
    self.assertIn('href="/"', read_site("404.html"))
```

- [ ] **Step 2: Run it to verify it fails**

Run: `python -m unittest tests.test_oauth_site.OAuthSiteTests.test_all_public_documents_have_titles_styles_and_root_navigation -v`

Expected: FAIL because `oauth-site/404.html` does not exist.

- [ ] **Step 3: Create the missing-page and deployment guide**

Create a 404 page that explains the page was not found and includes a visible return-to-home action.

Write `oauth-site/README.md` with these exact deployment steps: create a Cloudflare Pages project with Direct Upload, upload the *contents* of `oauth-site` as the project root, add `tinkbro.ru` and `www.tinkbro.ru` as custom domains, use the DNS records shown by Cloudflare, and only then enter the three live HTTPS URLs in Google Auth Platform Branding. Include a final step to verify domain ownership in Google Search Console and submit OAuth verification.

- [ ] **Step 4: Run the test to verify it passes**

Run: `python -m unittest tests.test_oauth_site.OAuthSiteTests.test_all_public_documents_have_titles_styles_and_root_navigation -v`

Expected: PASS.

- [ ] **Step 5: Record the checkpoint**

Run: `Test-Path oauth-site/README.md; Test-Path oauth-site/404.html`

Expected: both values are `True`.

### Task 4: Local smoke verification

**Files:**
- Modify: `tests/test_oauth_site.py`

**Interfaces:**
- Verifies static deployment contents before the user uploads them to Cloudflare.

- [ ] **Step 1: Add a failing expected-route test**

```python
def test_deploy_root_has_exact_google_auth_routes(self):
    expected = {
        "index.html", "privacy/index.html", "terms/index.html", "404.html", "assets/site.css",
    }
    actual = {path.relative_to(SITE_ROOT).as_posix() for path in SITE_ROOT.rglob("*") if path.is_file()}
    self.assertTrue(expected.issubset(actual))
```

- [ ] **Step 2: Run the complete site test file before final cleanup**

Run: `python -m unittest tests.test_oauth_site -v`

Expected: PASS after Tasks 1–3; if any expected file is missing, correct only that file before proceeding.

- [ ] **Step 3: Run a local HTTP smoke check**

Run:

```powershell
$site = (Resolve-Path oauth-site).Path
$job = Start-Job { param($root) Set-Location $root; python -m http.server 4173 } -ArgumentList $site
Start-Sleep -Seconds 1
try {
  @('/', '/privacy/', '/terms/').ForEach({ (Invoke-WebRequest "http://127.0.0.1:4173$_" -UseBasicParsing).StatusCode })
} finally { Stop-Job $job; Remove-Job $job }
```

Expected: three `200` responses.

- [ ] **Step 4: Verify deployment instructions and report the handoff**

Run: `Get-Content oauth-site/README.md`

Expected: instructions mention Direct Upload, custom domains, DNS, Google Search Console and all three final URLs.

- [ ] **Step 5: Record the final checkpoint**

Run: `python -m unittest tests.test_oauth_site -v`

Expected: all static-site tests pass. Do not publish or modify DNS; that requires the user's Cloudflare account.
