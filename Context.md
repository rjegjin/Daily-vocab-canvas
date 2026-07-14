# Project Context

## 2026-07-14 Image Quality Guard

- OpenAI image 기본값을 `gpt-image-1-mini` medium으로 올리고 9-in-1 sheet를 3-in-1 sheet 3장으로 분리했다.
- icon cache key에 visual/provider/model/quality/version을 포함해 잘못된 구형 cache의 무기한 재사용을 막았다.
- 아이콘 9개가 완전하지 않으면 카드 합성과 Telegram 발송을 중단한다.
- 정상 카드는 Telegram document로 보내 PNG 원본을 보존한다 (`VOCAB_TELEGRAM_SEND_MODE=photo`로 override 가능).
- 운영의 기존 `.env` low 설정은 `systemd/vocab-image-quality.conf` service drop-in으로 안전하게 override한다.
- OpenAI billing hard limit은 별도 운영 이슈로 남아 있으며, 이번 변경은 API 호출 없이 mock test로 검증했다.

- Checked on 2026-06-17.
- No staged Git changes were present at the time of creation.
- The working tree already had modified, deleted, and untracked files.

## Current Shape

- The bot sends foreign-language learning content to Telegram.
- ES / JA / ZH keep image-based 3x3 vocab card flows.
- JA / ZH also have weak feedback, TTS, dialogue, and supplemental drills.
- EN is a text-first fluency system: vocab, phrase, dialogue with TTS, writing prompt, and writing feedback.
- `manager_bot.py` is the operations hub for manual runs, callbacks, writing feedback, and scheduled jobs.
- `card_engine.py`, `cost.py`, `budget.json`, and `cost_log.json` handle provider cost logging, TTS accounting, monthly budget limits, and language enable flags.

## Scheduling

- 05:00 KST: ES / JA / ZH vocab image cards.
- 05:10 KST: ES patterns, JA rules, ZH tones.
- 06:00 KST: English fluency.
- 06:20 KST: JA / ZH dialogue.

## Provider Notes

- Older docs describe Gemini / Imagen as the primary path.
- `FLUENCY_STATUS.md` says the default vocab card provider was switched on 2026-06-09 to lower-cost OpenAI text/image models.
- Gemini / Imagen fallback may still exist, but requires valid Google/Gemini billing credits.

## Main Reference Docs

- `FLUENCY_STATUS.md`: best current implementation/status summary.
- `PROJECT_STATUS.md`: broader progress summary and next-work notes.
- `ENGLISH_FLUENCY_SYSTEM.md`: English fluency module details.
- `JA_ZH_FLUENCY_ROADMAP.md`: Japanese/Chinese fluency roadmap and completed milestones.
- `GEMINI.md`, `DEV_LOG.md.bak`, and `README.md`: useful historical context but not fully current.
- `repomix-output.md`: generated analysis dump; verify against source files before trusting it.

## Known Follow-Ups

- `README.md` is stale and still presents the older Gemini/Imagen-centered project shape.
- `requirements.txt` may be incomplete for manager bot, English modules, scheduler, and Google TTS usage.
- Decide whether English automation should stay in the long-running manager scheduler or get dedicated GitHub Actions workflows.

## Remote Sync Rule

- Production host is `mh_bot@100.103.20.9`.
- Production project path is `/home/mh_bot/projects/Daily_Vocab_Card_Bot`.
- Local changes are not automatically synced to the production host by Git, hook, cron, or systemd.
- After AI-assisted or local file changes that should run on production, sync the changed files explicitly with `rsync`.
- Prefer syncing only reviewed source/docs/config files instead of the whole working tree, because logs, caches, generated images, learned data, and local locks are mixed into the repo directory.
- Current production service is `vocab-manager-bot.service`, running `manager_bot.py`.
- If runtime Python files or service entrypoints change, restart the affected user service after sync:
  - `ssh mh_bot@100.103.20.9 'systemctl --user restart vocab-manager-bot.service'`
- If language-specific bot services are introduced later, create separate user services and restart only the affected language bot.

## Verification Cost Rule

- Local and remote verification consumes more AI tokens when command output is long.
- Keep default verification terse: local `py_compile`, remote `py_compile`, key-file `sha256sum`, and `systemctl is-active` or short `systemctl show` properties.
- Avoid full `git diff`, broad `rg`, full `systemctl status`, and journal output unless investigating a failure.
- Prefer comparing checksums over reading full file contents from both local and remote.
