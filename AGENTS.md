# Agent Rules

## 언어

- 한국어로 대화한다.
- 코드, 파일명, 기술 용어는 영어를 유지한다.

## 코드 스타일

- 변경 전 대상 파일을 먼저 읽는다.
- 한 번에 하나의 문제만 다룬다.
- 추측하지 말고 확인 먼저 한다.

## 토큰 절약

- 긴 파일 전체를 컨텍스트에 올리지 않는다.
- 필요한 섹션만 읽는다.
- 요약은 원본보다 훨씬 짧게 유지한다.
- 로컬/원격 검증 시 긴 출력은 피한다.
- 기본 검증은 `py_compile`, 핵심 파일 `sha256sum`, `systemctl is-active` 또는 `systemctl show --property=ActiveState,SubState,ExecMainPID`처럼 짧은 출력 위주로 한다.
- `git diff`, `rg`, `systemctl status`, journal 출력은 문제가 있거나 사용자가 요청할 때만 범위를 좁혀 실행한다.

## 세션 시작 시

- 프로젝트에 `Context.md`가 있으면 반드시 읽는다.
- 프로젝트에 `DEAD_END.md`가 있으면 읽고 해당 접근법을 피한다.

## Skill 사용

- `/ponytail`: 가장 간단한 솔루션 추구 (과도한 엔지니어링 방지)
- `/code-review`: 코드 리뷰
- `/simplify`: 코드 간소화 및 중복 제거
- `/verify`: 구현 후 동작 검증
- `/run`: 앱 실행 및 동작 확인

## 운영 서버 배포 (mhbot@100.103.20.9)

- 운영 서버: `mhbot@100.103.20.9`
- 운영 프로젝트 경로: `/home/mh_bot/projects/Daily_Vocab_Card_Bot`
- 로컬 변경은 Git hook, cron, GitHub Actions, systemd로 자동 동기화되지 않음.
- 코드 변경 시 git push 후, 원격 서버에서 git pull 하거나 명시적 rsync 동기화

**부트스트랩 변경** (2026-07-06):
- 모든 봇이 `bot_common` (mh-common의 shared 헬퍼) 사용
- `load_secrets()`: `~/.secrets/.env` 로드
- `require_env()`: 필수 환경 변수 검증
- 환경 변수 누락 시 启动 중단으로 사고 방지

**동기화 시 주의**:
- 전체 working tree 무조건 동기화 금지 (로그, 캐시, 이미지, lock, learned data 혼합)
- 검토된 source/docs/config 파일만 선택 동기화

```bash
rsync -av manager_bot.py spanish.py japanese.py chinese.py mhbot@100.103.20.9:/home/mh_bot/projects/Daily_Vocab_Card_Bot/
rsync -av GEMINI.md README.md PROJECT_STATUS.md mhbot@100.103.20.9:/home/mh_bot/projects/Daily_Vocab_Card_Bot/
```

**서비스 재시작**:
- 현재 운영 서비스: `vocab-manager-bot.service` (manager_bot.py 실행)

```bash
ssh mhbot@100.103.20.9 'systemctl --user restart vocab-manager-bot.service'
```

## 검증 출력 최소화

- 로컬과 원격을 동시에 검증하면 출력이 대화 컨텍스트로 들어와 토큰 비용이 늘어난다.
- 그래도 운영 서버와 로컬이 같은지 확인하는 검증은 사고 방지 가치가 있으므로 유지하되, 기본 출력은 최소화한다.
- 파일 전체 내용 비교 대신 `sha256sum`으로 일치 여부를 확인한다.
- 원격 검증은 동기화 스크립트 또는 짧은 명령에서 `py_compile && systemctl is-active` 정도로 끝낸다.
- 상세 로그, 긴 diff, 광범위한 검색은 실패 원인을 파악해야 할 때만 연다.
