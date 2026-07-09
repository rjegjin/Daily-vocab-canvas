# Dead Ends

- Checked on 2026-06-17.

## Avoided / Failed Approaches

- Do not assume Gemini / Imagen is currently the only or default provider. Older docs say that, but `FLUENCY_STATUS.md` records a 2026-06-09 switch to lower-cost OpenAI text/image providers.
- Do not retry the old Gemini-only path without checking billing/API key state. Prior failure was `429 RESOURCE_EXHAUSTED` with prepayment credits depleted; the workaround was switching default vocab card generation to OpenAI.
- Do not treat `repomix-output.md` as authoritative source. It is a generated repo dump and may not match current files.
- Do not rely on `README.md`, `GEMINI.md`, or `DEV_LOG.md.bak` as fully current operational docs without cross-checking `FLUENCY_STATUS.md` and source code.
- Do not assume local edits automatically reach `mh_bot@100.103.20.9`. The production host has the repo and a running `vocab-manager-bot.service`, but no repo-local deploy hook, crontab, or GitHub Actions deployment step was found.
- Do not use verbose local+remote verification by default. Long `git diff`, broad `rg`, full `systemctl status`, and journal outputs should be reserved for failures or explicit requests.
