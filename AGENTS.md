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

- `$context-load`: 새 세션 시작 또는 맥락 파악 필요 시
- `$dead-end-log`: 뭔가 실패했을 때 즉시 기록
- `$grill-me`: 설계/계획 검토 시
- `$tdd`: 기능 구현 시
- `$zoom-out`: 방향이 흔들릴 때

## mh_bot 동기화

- 운영 서버는 `mh_bot@100.103.20.9`이다.
- 운영 프로젝트 경로는 `/home/mh_bot/projects/Daily_Vocab_Card_Bot`이다.
- 로컬 변경은 Git hook, cron, GitHub Actions, systemd로 자동 동기화되지 않는다.
- AI 또는 로컬 작업으로 운영에 반영해야 하는 파일이 바뀌면, 작업 종료 전 변경 파일을 명시적으로 `rsync`로 동기화한다.
- 전체 working tree를 무조건 동기화하지 않는다. 로그, 캐시, 생성 이미지, lock 파일, learned data가 섞여 있으므로 검토한 source/docs/config 파일만 보낸다.
- 기본 동기화 예시:

```bash
rsync -av path/to/file.py path/to/doc.md mh_bot@100.103.20.9:/home/mh_bot/projects/Daily_Vocab_Card_Bot/
```

- 현재 운영 서비스는 `vocab-manager-bot.service`이고 `manager_bot.py`를 실행한다.
- runtime Python 파일이나 service entrypoint를 운영에 반영한 경우 필요한 서비스만 재시작한다.

```bash
ssh mh_bot@100.103.20.9 'systemctl --user restart vocab-manager-bot.service'
```

- 언어별 bot service를 추가한 뒤에는 전체 manager가 아니라 영향을 받은 언어별 service만 재시작한다.

## 검증 출력 최소화

- 로컬과 원격을 동시에 검증하면 출력이 대화 컨텍스트로 들어와 토큰 비용이 늘어난다.
- 그래도 운영 서버와 로컬이 같은지 확인하는 검증은 사고 방지 가치가 있으므로 유지하되, 기본 출력은 최소화한다.
- 파일 전체 내용 비교 대신 `sha256sum`으로 일치 여부를 확인한다.
- 원격 검증은 동기화 스크립트 또는 짧은 명령에서 `py_compile && systemctl is-active` 정도로 끝낸다.
- 상세 로그, 긴 diff, 광범위한 검색은 실패 원인을 파악해야 할 때만 연다.
