# Dead Ends

- Checked on 2026-06-17.

## Avoided / Failed Approaches

- 2026-07-14: secret-presence 확인용으로 shell 안에 복잡한 `awk` quoting을 중첩하자 zsh parse error가 발생했다. 다음에는 key 값을 읽지 않는 단순한 `test`/단일 `awk` 조건으로 존재 여부만 확인한다.
- 2026-07-14: `Daily_Vocab_Card_Bot`를 cwd로 지정한 뒤 `rg Daily_Vocab_Card_Bot/...` 경로를 다시 붙여 IO error가 발생했다. 다음에는 command의 `workdir`와 상대 경로 기준을 먼저 맞춘다.
- 2026-07-14: `rsync systemd/ remote:project/`가 디렉터리 내부 파일을 remote project root에 펼쳤다. 다음에는 remote의 `project/systemd/`를 명시해 하위 구조를 보존한다.

- Do not assume Gemini / Imagen is currently the only or default provider. Older docs say that, but `FLUENCY_STATUS.md` records a 2026-06-09 switch to lower-cost OpenAI text/image providers.
- Do not retry the old Gemini-only path without checking billing/API key state. Prior failure was `429 RESOURCE_EXHAUSTED` with prepayment credits depleted; the workaround was switching default vocab card generation to OpenAI.
- Do not treat `repomix-output.md` as authoritative source. It is a generated repo dump and may not match current files.
- Do not rely on `README.md`, `GEMINI.md`, or `DEV_LOG.md.bak` as fully current operational docs without cross-checking `FLUENCY_STATUS.md` and source code.
- Do not assume local edits automatically reach `mh_bot@100.103.20.9`. The production host has the repo and a running `vocab-manager-bot.service`, but no repo-local deploy hook, crontab, or GitHub Actions deployment step was found.
- Do not use verbose local+remote verification by default. Long `git diff`, broad `rg`, full `systemctl status`, and journal outputs should be reserved for failures or explicit requests.
