"""
월간 성취 리포트
- 당월(또는 --prev 로 전월) 신규 단어 수, 누적, 취약, 카테고리 분포
- 텍스트 바 차트 포함
- Telegram 전송

스케줄: 매월 1일 00:30 (manager_bot이 --prev 없이 호출 → 전월 데이터)
수동:   python monthly_report.py          (이번 달)
        python monthly_report.py --prev   (지난 달)
"""
import os
import sys
import json
from collections import Counter
from datetime import date, timedelta
from pathlib import Path
from dotenv import load_dotenv

PROJECT_DIR = Path(__file__).parent
load_dotenv(PROJECT_DIR / '.env')
load_dotenv(PROJECT_DIR.parent / '.secrets' / '.env')

TOKEN   = os.getenv('VOCAB_BOT_TOKEN') or os.getenv('GEMINI_BOT_TOKEN')
CHAT_ID = os.getenv('VOCAB_CHAT_ID')   or os.getenv('GEMINI_CHAT_ID')

LANG_LABELS = {
    'es': '🇪🇸 스페인어',
    'ja': '🇯🇵 일본어',
    'zh': '🇨🇳 중국어',
}
JSON_FILES = {
    'es': 'learned_data_es.json',
    'ja': 'learned_data_ja.json',
    'zh': 'learned_data_zh.json',
}

# -------------------------------------------------------------------
# 헬퍼
# -------------------------------------------------------------------
def _bar(count: int, max_count: int, width: int = 20) -> str:
    if max_count == 0:
        return '░' * width
    filled = round(count / max_count * width)
    return '█' * filled + '░' * (width - filled)


def _month_label(year: int, month: int) -> str:
    return f"{year}년 {month}월"


def _prev_month(year: int, month: int):
    first = date(year, month, 1)
    last_prev = first - timedelta(days=1)
    return last_prev.year, last_prev.month


def _load(lang: str) -> list:
    path = PROJECT_DIR / JSON_FILES[lang]
    if not path.exists():
        return []
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)


def _monthly_cost(year: int, month: int) -> float:
    cost_path = PROJECT_DIR / 'cost_log.json'
    if not cost_path.exists():
        return 0.0
    with open(cost_path, 'r', encoding='utf-8') as f:
        log = json.load(f)
    prefix = f"{year:04d}-{month:02d}"
    total = 0.0
    for day_key, day_data in log.items():
        if day_key.startswith(prefix) and isinstance(day_data, dict):
            total += day_data.get('_daily_total_usd', 0.0)
    return round(total, 4)


def _speaking_metrics(year: int, month: int) -> dict:
    """
    Calculate speaking session metrics for a given month from SPEAKING_SESSIONS_FILE.
    Returns: dict with keys:
      - sessions_count: int (total sessions this month)
      - target_hit_rate: float (0-100, based on target_hit field)
      - avg_turn_length: float (average of avg_turn_words)
      - speaking_error_resolved: float (0-100, weak=False ratio for speaking_error items)
    """
    prefix = f"{year:04d}-{month:02d}"

    result = {
        "sessions_count": 0,
        "target_hit_rate": 0.0,
        "avg_turn_length": 0.0,
        "speaking_error_resolved": 0.0,
    }

    # Count sessions and calculate metrics from SPEAKING_SESSIONS_FILE
    sessions_path = PROJECT_DIR / "speaking_sessions.json"
    if sessions_path.exists():
        try:
            with open(sessions_path, "r", encoding="utf-8") as f:
                sessions = json.load(f)
            if not isinstance(sessions, list):
                sessions = []

            this_month_sessions = [
                s
                for s in sessions
                if isinstance(s, dict) and s.get("date", "").startswith(prefix)
            ]
            result["sessions_count"] = len(this_month_sessions)

            # Calculate target hit rate and avg turn length
            target_hits = []
            avg_words = []
            for session in this_month_sessions:
                # Target hit: only for roleplay sessions with analysis
                if session.get("target_hit") is True:
                    target_hits.append(1.0)
                elif session.get("target_hit") is False:
                    target_hits.append(0.0)

                # Average turn length
                avg_turn = session.get("avg_turn_words", 0.0)
                if avg_turn > 0:
                    avg_words.append(avg_turn)

            if target_hits:
                result["target_hit_rate"] = round(sum(target_hits) / len(target_hits) * 100, 1)
            if avg_words:
                result["avg_turn_length"] = round(sum(avg_words) / len(avg_words), 1)

        except Exception as e:
            print(f"⚠️ 말하기 메트릭 계산 실패: {e}")

    # Calculate speaking error resolution rate
    learned_path = PROJECT_DIR / "learned_data_en_phrase.json"
    if learned_path.exists():
        try:
            with open(learned_path, "r", encoding="utf-8") as f:
                learned = json.load(f)
            if not isinstance(learned, list):
                learned = []

            speaking_errors = [
                item
                for item in learned
                if isinstance(item, dict) and item.get("category") == "speaking_error"
            ]
            if speaking_errors:
                resolved = sum(
                    1 for item in speaking_errors if not item.get("weak", False)
                )
                result["speaking_error_resolved"] = round(
                    resolved / len(speaking_errors) * 100, 1
                )

        except Exception as e:
            print(f"⚠️ 말하기 오류 해소율 계산 실패: {e}")

    return result


# -------------------------------------------------------------------
# 리포트 생성
# -------------------------------------------------------------------
def build_report(year: int, month: int) -> str:
    prefix = f"{year:04d}-{month:02d}"
    label  = _month_label(year, month)

    lang_stats = {}
    for lang in ('es', 'ja', 'zh'):
        data = _load(lang)
        new_words  = [d for d in data if d.get('date_added', '').startswith(prefix)]
        total      = len(data)
        weak       = sum(1 for d in data if d.get('weak'))
        cats       = Counter(d.get('category', 'unknown') for d in new_words)
        lang_stats[lang] = {
            'new':   len(new_words),
            'total': total,
            'weak':  weak,
            'cats':  cats,
        }

    total_new = sum(s['new'] for s in lang_stats.values())
    max_new   = max((s['new'] for s in lang_stats.values()), default=1) or 1

    cost = _monthly_cost(year, month)

    lines = [
        f"📅 *{label} 월간 성취 리포트*",
        "",
        f"📝 이번 달 신규 단어: *{total_new}개*",
        "",
        "──────────────────────",
    ]

    for lang, s in lang_stats.items():
        bar = _bar(s['new'], max_new)
        lines.append(f"{LANG_LABELS[lang]}")
        lines.append(f"  이번 달 +{s['new']}개  {bar}")
        lines.append(f"  누적 {s['total']}개 · 취약 {s['weak']}개")
        if s['cats']:
            top_cats = s['cats'].most_common(3)
            cat_str = '  '.join(f"{c}({n})" for c, n in top_cats)
            lines.append(f"  카테고리: {cat_str}")
        lines.append("")

    lines.append("──────────────────────")

    # 말하기 세션 지표
    speaking = _speaking_metrics(year, month)
    if speaking["sessions_count"] > 0:
        lines.append(f"🎤 *말하기 세션*")
        lines.append(f"  세션: {speaking['sessions_count']}회")
        if speaking["target_hit_rate"] > 0:
            lines.append(f"  타깃 적중률: {speaking['target_hit_rate']}%")
        if speaking["avg_turn_length"] > 0:
            lines.append(f"  평균 턴 길이: {speaking['avg_turn_length']}단어")
        if speaking["speaking_error_resolved"] > 0:
            lines.append(f"  오류 해소율: {speaking['speaking_error_resolved']}%")
        lines.append("")

    lines.append("──────────────────────")

    # 전체 누적 합계
    grand_total = sum(s['total'] for s in lang_stats.values())
    lines.append(f"📚 전체 누적: *{grand_total}개*")
    if cost > 0:
        lines.append(f"💰 이달 API 비용: *${cost:.4f}*")

    return '\n'.join(lines)


# -------------------------------------------------------------------
# Telegram 전송
# -------------------------------------------------------------------
def _send(text: str):
    import requests
    import warnings

    class IPAdapter(requests.adapters.HTTPAdapter):
        def send(self, request, **kwargs):
            request.url = request.url.replace("api.telegram.org", "149.154.167.220")
            request.headers["Host"] = "api.telegram.org"
            return super().send(request, **kwargs)

    session = requests.Session()
    session.mount("https://", IPAdapter())
    session.verify = False

    proxy = os.getenv('TELEGRAM_PROXY_URL')
    if proxy:
        session.proxies = {'http': proxy, 'https': proxy}

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        result = session.post(
            f"https://api.telegram.org/bot{TOKEN}/sendMessage",
            data={'chat_id': CHAT_ID, 'text': text, 'parse_mode': 'Markdown'}
        ).json()

    if result.get("ok"):
        print("✅ 월간 리포트 전송 완료")
    else:
        print(f"❌ 전송 실패: {result}")


# -------------------------------------------------------------------
# 메인
# -------------------------------------------------------------------
def main():
    today = date.today()
    if '--prev' in sys.argv:
        year, month = _prev_month(today.year, today.month)
    else:
        year, month = today.year, today.month

    print(f"📅 {_month_label(year, month)} 리포트 생성 중...")
    report = build_report(year, month)
    print(report)

    if not TOKEN or not CHAT_ID:
        print("⚠️ TOKEN/CHAT_ID 없음 — 전송 건너뜀")
        return

    _send(report)


if __name__ == "__main__":
    main()
