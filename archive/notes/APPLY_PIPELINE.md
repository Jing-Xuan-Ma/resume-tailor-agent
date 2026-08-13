# Apply pipeline — paths & product boundaries

## Two entry paths

| Path | Entry | Purpose |
|------|--------|---------|
| **Batch (shopping cart)** | Intern-list select → `/shoppingcart` → Refine → Confirm PDF → **Start apply** | Multi-job: Jobright → Original Job Post → ATS → fill → pause |
| **Single job** | Tailor Confirm → `/apply?versionId=…` | One job fill-pause in Apply workspace |

Both share the same hard rule: **never auto-click Submit**. Final submit is user one-click only (Phase 6+).

## Apply status machine (per cart item)

```
idle → queued → navigating → on_ats → applying → registered → filled → ready_to_submit → submitted
                                                                    ↘ failed (any step)
```

| Phase | Status target | What it does |
|-------|---------------|--------------|
| **1** | `queued` | Queue eligible cart items; status APIs/UI |
| **2** | `navigating` → `on_ats` | Jobright job page → **Original Job Post** → company ATS URL (`ats_url` / `ats_type`) |
| **3** | `on_ats` → `applying` | ATS **Apply** → **Autofill with Resume** (confirmed cart PDF); never Submit |
| **4** | `applying` → `registered` | **Create Account / Sign In** with `ATS_DEFAULT_EMAIL` + `ATS_DEFAULT_PASSWORD` |
| **5** | `registered` → `filled` → `ready_to_submit` | Fill company ATS form (Profile + resume); **hard-stop before Submit**; persist reviewable snapshot |
| **6+** | `submitted` | One-click Submit display page (later) |

Phase 2 resolver order:

1. Scraped company `apply_url` / `source_url` (skip Jobright aggregators)
2. Company ATS resolver (Greenhouse/Workday/…)
3. If still missing and `CART_APPLY_LIVE_NAV` or `CART_APPLY_LIVE_NAV_FALLBACK`: Playwright Jobright Original Job Post (`commit`, then DCL best-effort)

Live nav timeouts become `jobright_page_timeout`; no official ATS → `no_official_ats_url` (never raw Playwright Call log).

APIs: `POST …/apply/start` (through Phase 5 by default; **runs in a worker thread** so Playwright Sync API is safe under FastAPI asyncio), `POST …/apply/process`, `GET …/apply/status`,  
`GET …/items/{item_id}/fill-review` (flip-through), `GET …/items/{item_id}/fill-screenshot`,  
`POST …/items/{item_id}/open-form` (**查看表单**: headed browser + restore `storage_state` → official filled submit page; never clicks Submit).

Shared helpers:
- Phase 3: `BrowserSession.apply_and_autofill_resume` / `ats_apply_entry`
- Phase 4: `BrowserSession.create_or_sign_in` / `ats_account` (email masked; password never stored)
- Phase 5: `BrowserSession.fill_form_pause` / `ats_form_fill` (snapshot JSON + screenshot)
- Sandbox: `artifacts/funnel/sprint-j/fixture_workday_entry.html`

## Credentials (ATS account create / sign-in)

Set in environment (never commit real secrets):

- `ATS_DEFAULT_EMAIL`
- `ATS_DEFAULT_PASSWORD` (must satisfy typical Workday rules: 8+ chars, upper, lower, digit, special)

See `.env.example`.

## Browser safety

- `ENABLE_BROWSER_FILL_PAUSE=true` — fill + screenshot, stop before Submit
- `ALLOW_LIVE_BROWSER_FILL=false` by default (sandbox); set `true` only for live ATS acceptance
- `CART_APPLY_LIVE_NAV=false` by default; scraped ATS URL first, Playwright Original Job Post as fallback
- `CART_APPLY_LIVE_ENTRY=false` by default; local `file://` / fixture pages always allowed for Phase 3
- `ENABLE_USER_CONFIRM_SUBMIT=true` — UI may record user confirm; does not mean agent clicks Submit alone

## Phase 2 acceptance (manual)

Sample Jobright: `https://jobright.ai/jobs/info/6a52cafd8a74e077472f6211?...`  
Expected ATS host pattern: `*.myworkdayjobs.com` (e.g. ASM Global Workday).

1. Refine + Confirm a cart item that has a scraped company apply URL **or** enable live nav.
2. Click **开始投递** → item moves `queued` → `navigating` → `on_ats`.
3. UI shows ATS link with `ats_type` (e.g. workday).
4. No Submit click; Phase 3 will handle Apply / Autofill.

## Phase 3 acceptance

1. Item must have **confirmed** `resume.pdf` (else `failed` / `confirm_resume_pdf_required`).
2. From `on_ats`: click **Apply** → **Autofill with Resume** → attach cart resume when file input appears.
3. Status → `applying` with `autofill_clicked` / `phase3_done`; `next_screen` often `create_account` (Phase 4).
4. Still **never** clicks final Submit.
5. Live company ATS: set `CART_APPLY_LIVE_ENTRY=true` (or `ALLOW_LIVE_BROWSER_FILL=true`). Sandbox: fixture URI works without the flag.
6. Single-job Apply workspace can call the same `BrowserSession.apply_and_autofill_resume`.

## Phase 4 acceptance

1. Configure `ATS_DEFAULT_EMAIL` + `ATS_DEFAULT_PASSWORD` (password must pass complexity rules).
2. From `applying` (`phase3_done`): Create Account; if email already exists → Sign In once.
3. Status → `registered` with `phase4_done`, `auth_mode`, `email_masked` only (no password in API/meta).
4. Failure reasons: `ats_credentials_not_configured`, `ats_password_policy_failed`, `validation_failed`, `captcha_required`, `sign_in_failed_after_email_exists`.
5. Still never clicks final Submit.
6. Fixture: `exists@example.com` forces email-exists → Sign In path.

## Phase 5 acceptance

1. From `registered`: fill company ATS form using Profile + confirmed cart `resume.pdf`.
2. Status → `ready_to_submit` with `phase5_done`, `filled_fields`, `fill_snapshot_path`, screenshot, **`form_url` + `storage_state_path`**.
3. **Submit is never clicked** (`submit_button=NOT_CLICKED` / `paused_before_submit`).
4. Cart expand → tab **已填内容（可翻阅）**: 拟填档案 ↔ 已写入字段 ↔ 截图 ↔ 暂停确认.
5. Cart row **查看表单** / pause-step CTA → `POST …/open-form` opens the **official** ATS URL and **re-fills** the form (DOM values are not in cookies), then keeps a headed browser on the Submit page. Submit is never clicked.
6. Live ATS requires `CART_APPLY_LIVE_ENTRY=true` (or `ALLOW_LIVE_BROWSER_FILL`); otherwise dry-run profile snapshot is still reviewable.
7. Single-job Apply can call `BrowserSession.fill_form_pause`.
