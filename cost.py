"""
비용 대시보드 + 예산 설정 CLI

사용법:
  python cost.py                    이번 달 현황 조회
  python cost.py --budget 40        월 예산 변경 ($40)
  python cost.py --disable ja       일본어 비활성화
  python cost.py --enable ja        일본어 활성화
  python cost.py --disable tts      TTS 비활성화
  python cost.py --enable tts       TTS 활성화
  python cost.py --history          최근 30일 일별 내역
"""
import sys
import os
import json
from datetime import date, timedelta
from pathlib import Path

PROJECT_DIR = Path(__file__).parent
COST_LOG    = PROJECT_DIR / 'cost_log.json'
BUDGET_FILE = PROJECT_DIR / 'budget.json'

LANG_LABEL = {'es': '🇪🇸 ES', 'ja': '🇯🇵 JA', 'zh': '🇨🇳 ZH'}
# TTS 단가: Standard $4/1M chars, 1M/월 무료
TTS_FREE_CHARS  = 1_000_000
TTS_PRICE_PER_M = 4.0

# -------------------------------------------------------------------
def _load_log() -> dict:
    if not COST_LOG.exists():
        return {}
    with open(COST_LOG, 'r') as f:
        return json.load(f)

def _load_budget() -> dict:
    defaults = {'monthly_limit_usd': 50.0, 'tts_enabled': True,
                'lang_enabled': {'es': True, 'ja': True, 'zh': True}}
    if not BUDGET_FILE.exists():
        return defaults
    with open(BUDGET_FILE, 'r') as f:
        data = json.load(f)
    for k, v in defaults.items():
        data.setdefault(k, v)
    data['lang_enabled'] = {**defaults['lang_enabled'], **data.get('lang_enabled', {})}
    return data

def _save_budget(cfg: dict):
    with open(BUDGET_FILE, 'w') as f:
        json.dump(cfg, f, indent=2)
    print(f"✅ budget.json 저장 완료")

def _bar(used: float, limit: float, width: int = 24) -> str:
    ratio = min(used / limit, 1.0) if limit > 0 else 0
    filled = round(ratio * width)
    color = '█' if ratio < 0.7 else ('▓' if ratio < 0.9 else '░')
    return color * filled + '░' * (width - filled)

def _month_stats(prefix: str, log: dict) -> dict:
    """주어진 YYYY-MM 접두사에 해당하는 통계 반환"""
    gemini_total = 0.0
    tts_chars    = 0
    per_lang     = {'es': 0.0, 'ja': 0.0, 'zh': 0.0}
    days_with_data = 0

    for day_key, day_data in log.items():
        if not day_key.startswith(prefix) or not isinstance(day_data, dict):
            continue
        days_with_data += 1
        gemini_total += day_data.get('_daily_total_usd', 0.0)
        tts_chars    += day_data.get('tts', {}).get('chars', 0)
        for lang in per_lang:
            if lang in day_data and isinstance(day_data[lang], dict):
                per_lang[lang] += day_data[lang].get('cost_usd', 0.0)

    # TTS 비용: 월 누적 기준으로 무료 티어 적용
    billable_chars = max(0, tts_chars - TTS_FREE_CHARS)
    tts_cost = billable_chars / 1_000_000 * TTS_PRICE_PER_M

    return {
        'gemini': gemini_total,
        'tts_chars': tts_chars,
        'tts_cost': tts_cost,
        'total': gemini_total + tts_cost,
        'per_lang': per_lang,
        'days': days_with_data,
    }

# -------------------------------------------------------------------
def cmd_dashboard():
    log    = _load_log()
    budget = _load_budget()
    today  = date.today()
    prefix = today.strftime('%Y-%m')
    stats  = _month_stats(prefix, log)

    limit     = budget['monthly_limit_usd']
    used      = stats['total']
    days_done = today.day
    projected = (used / days_done * 30) if days_done > 0 else 0

    print(f"\n{'='*46}")
    print(f"  📊 Daily Vocab Bot — 비용 대시보드")
    print(f"  기준: {today.year}년 {today.month}월 ({days_done}일 경과)")
    print(f"{'='*46}")

    # 예산 현황
    bar = _bar(used, limit)
    pct = (used / limit * 100) if limit > 0 else 0
    print(f"\n💰 월 예산:  ${limit:.2f}")
    print(f"   사용:     ${used:.4f}  ({pct:.1f}%)")
    print(f"   [{bar}]")
    print(f"   월말 예상: ${projected:.2f}", end="")
    if projected > limit:
        print(f"  ⚠️  예산 초과 예상!")
    else:
        print(f"  ✅")

    # Gemini 상세
    print(f"\n🤖 Gemini 이미지 생성: ${stats['gemini']:.4f}")
    for lang, cost in stats['per_lang'].items():
        enabled = budget['lang_enabled'].get(lang, True)
        status = '✅' if enabled else '🔴 비활성'
        daily_avg = cost / days_done if days_done > 0 else 0
        print(f"   {LANG_LABEL[lang]}  ${cost:.4f}  (~${daily_avg:.3f}/일)  {status}")

    # TTS 상세
    tts_status = '✅' if budget['tts_enabled'] else '🔴 비활성'
    print(f"\n🔊 TTS (Google Cloud): {tts_status}")
    if stats['tts_chars'] > 0:
        free_left = max(0, TTS_FREE_CHARS - stats['tts_chars'])
        print(f"   이번 달 {stats['tts_chars']:,}자  |  무료 잔여: {free_left:,}자")
        print(f"   TTS 비용: ${stats['tts_cost']:.6f}")
    else:
        print(f"   이번 달 TTS 사용 없음 (또는 미추적)")

    # 조절 명령어
    print(f"\n{'─'*46}")
    print(f"  조절 명령어:")
    print(f"  python cost.py --budget <금액>     예산 변경")
    print(f"  python cost.py --disable es|ja|zh  언어 비활성화")
    print(f"  python cost.py --enable  es|ja|zh  언어 활성화")
    print(f"  python cost.py --disable tts        TTS 끄기")
    print(f"  python cost.py --history            일별 내역")
    print(f"{'='*46}\n")

def cmd_history():
    log   = _load_log()
    today = date.today()
    print(f"\n{'─'*52}")
    print(f"  📅 최근 30일 일별 내역")
    print(f"{'─'*52}")
    for i in range(29, -1, -1):
        d = (today - timedelta(days=i)).isoformat()
        if d not in log or not isinstance(log[d], dict):
            continue
        day_data = log[d]
        total = day_data.get('_daily_total_usd', 0.0)
        langs = ' '.join(
            f"{LANG_LABEL[l]}:${v['cost_usd']:.2f}"
            for l, v in day_data.items()
            if l in LANG_LABEL and isinstance(v, dict) and 'cost_usd' in v
        )
        tts_chars = day_data.get('tts', {}).get('chars', 0)
        tts_str = f"  TTS:{tts_chars:,}자" if tts_chars else ""
        print(f"  {d}  ${total:.4f}  {langs}{tts_str}")
    print(f"{'─'*52}\n")

# -------------------------------------------------------------------
def main():
    args = sys.argv[1:]

    if not args:
        cmd_dashboard()
        return

    if '--history' in args:
        cmd_history()
        return

    if '--budget' in args:
        idx = args.index('--budget')
        try:
            val = float(args[idx + 1])
        except (IndexError, ValueError):
            print("❌ 사용법: python cost.py --budget <금액>")
            return
        cfg = _load_budget()
        cfg['monthly_limit_usd'] = val
        _save_budget(cfg)
        print(f"💰 월 예산 → ${val:.2f}")
        return

    if '--disable' in args:
        idx = args.index('--disable')
        try:
            target = args[idx + 1].lower()
        except IndexError:
            print("❌ 사용법: python cost.py --disable es|ja|zh|tts")
            return
        cfg = _load_budget()
        if target == 'tts':
            cfg['tts_enabled'] = False
            print("🔴 TTS 비활성화")
        elif target in ('es', 'ja', 'zh'):
            cfg['lang_enabled'][target] = False
            print(f"🔴 {LANG_LABEL[target]} 비활성화")
        else:
            print(f"❌ 알 수 없는 대상: {target}")
            return
        _save_budget(cfg)
        return

    if '--enable' in args:
        idx = args.index('--enable')
        try:
            target = args[idx + 1].lower()
        except IndexError:
            print("❌ 사용법: python cost.py --enable es|ja|zh|tts")
            return
        cfg = _load_budget()
        if target == 'tts':
            cfg['tts_enabled'] = True
            print("✅ TTS 활성화")
        elif target in ('es', 'ja', 'zh'):
            cfg['lang_enabled'][target] = True
            print(f"✅ {LANG_LABEL[target]} 활성화")
        else:
            print(f"❌ 알 수 없는 대상: {target}")
            return
        _save_budget(cfg)
        return

    print("❌ 알 수 없는 옵션. python cost.py --help 참고")

if __name__ == "__main__":
    main()
