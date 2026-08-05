# Resume Agent ↔ Jobright Bridge Extension

Chrome/Edge extension: read the current Jobright job page (no copy-paste), then open Resume Agent **Tailor** in a full window. **No Side Panel** — Tailor / Apply / Outreach live in the main Resume Agent UI.

## Install (Load unpacked)

1. Start backend (`:8000`) and frontend (`:3000`).
2. Chrome → `chrome://extensions` → Developer mode → **Load unpacked**.
3. Select this folder: `extensions/jobright-bridge`.
4. Open a Jobright job detail **or** local mock:  
   `http://localhost:3000/fixtures/jobright-mock.html`
5. Click the green **Open Tailor** FAB (or the extension toolbar icon) — imports JD and opens Tailor in a **1440×900** window.

After code updates: click **Reload** on the extension card (required when `manifest.json` changes). Close any old Side Panel tab if Chrome still shows one from a previous version.

Default token: `dev-extension-token` (matches backend `EXTENSION_BRIDGE_TOKEN`).

## Safety

- Apply stays `paused_before_submit` in the main app.
- Outreach is draft / user-send only.
