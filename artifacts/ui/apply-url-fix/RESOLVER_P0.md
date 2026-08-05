# Apply URL Resolver — P0 shipped

**Status:** live against Fed Workday case

## What shipped

1. **Adapters** (`backend/app/modules/job_discovery/apply_resolver/`)
   - Workday CXS `POST /wday/cxs/{tenant}/{site}/jobs`
   - Greenhouse `GET boards-api.greenhouse.io/v1/boards/{board}/jobs`
   - Lever `GET api.lever.co/v0/postings/{company}`

2. **Match + light verify**
   - Title / req-id / location confidence
   - HTTP GET + keyword check; CAPTCHA/login → `unverified` (no bypass)

3. **Company → ATS cache**
   - `data/ats_company_map.json` (filled after first successful resolve)

4. **Wiring**
   - `resolve_listing_apply_url`: ① usable deep link → ② resolver → ③ board fallback
   - `start-apply` returns `apply_resolve` (verified / unverified / not_found)

## Fed case (live)

- Before: thin `…/FRS` or Indeed only
- After Manual apply `source_url`:
  `https://rb.wd5.myworkdayjobs.com/en-US/FRS/job/New-York-NY/Regulatory-Data-Analyst_R-0000032890-1`
- `apply_resolve.status`: `verified`
- Indeed kept as `board_url` fallback

## Jobright handoff (checked in DB)

Jobright already stores real Apply hrefs when the extension captures them, e.g.:

- Zipline → `boards.greenhouse.io/embed/job_app?…&utm_source=jobright`

Those usable deep links stay **tier ①** and skip the resolver.  
Next step when bridging: keep trusting `metadata.apply_url` when `is_usable_job_apply_url`, and only resolve when Jobright Apply is missing / thin / Jobright-hosted.

## Not yet (P1/P2)

- UI three-state badges (✅/⚠️/❌)
- Heavy browser verify
- iCIMS / SuccessFactors browser search
