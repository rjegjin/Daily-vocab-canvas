#!/usr/bin/env python3
"""
Night Worker Task: Vocab Bot 주간 분석

실행 타이밍: 매주 일요일 23:00 KST
기능:
  1. learned_data_*.json 로드
  2. 취약 단어 자동 감지 (오래되고 seen_count=1인 단어)
  3. 카테고리별 분포 계산
  4. 부족한 카테고리 파악
  5. 주간 통계 리포트 생성 + 텔레그램 발송
  6. DEV_LOG.md에 기록

사용법:
  python vocab_analyze.py
  python vocab_analyze.py --dry-run  # 테스트 (알림 발송 안 함)
"""

import os
import json
import sys
from datetime import datetime, date, timedelta
from pathlib import Path
from collections import Counter

PROJECT_DIR = Path(__file__).parent

# 설정
WEAK_THRESHOLD_DAYS = 30  # 30일 이상 경과하고 본 횟수 1회면 weak 마킹

def load_learned_json(file_path: Path) -> list:
    """JSON 파일에서 단어 데이터 로드"""
    if not file_path.exists():
        return []
    with open(file_path, 'r', encoding='utf-8') as f:
        return json.load(f)


def save_learned_json(file_path: Path, data: list):
    """JSON 파일에 단어 데이터 저장"""
    with open(file_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def mark_weak_words(data: list) -> dict:
    """
    취약 단어를 감지하고 마킹

    기준:
      - date_added가 30일 이상 이전
      - seen_count == 1
      - weak가 False

    Returns:
        {
            "marked_count": int,  # 새로 weak 마킹된 단어
            "weak_words": [...]   # 전체 weak 단어 목록
        }
    """
    today = date.today()
    marked_count = 0
    weak_words = []

    for item in data:
        if item.get('weak'):
            # 이미 weak인 경우
            weak_words.append(item['word'])
        else:
            # weak이 아닌 경우: 조건 확인
            date_added = datetime.strptime(item['date_added'], "%Y-%m-%d").date()
            days_passed = (today - date_added).days

            if days_passed >= WEAK_THRESHOLD_DAYS and item.get('seen_count', 1) == 1:
                item['weak'] = True
                item['weak_date'] = today.isoformat()
                weak_words.append(item['word'])
                marked_count += 1

    return {
        'marked_count': marked_count,
        'weak_words': weak_words
    }


def analyze_category_distribution(data: list) -> dict:
    """
    카테고리별 단어 분포 분석

    Returns:
        {
            "total": int,
            "categories": {"emotion": 10, "nature": 8, ...},
            "weak_by_category": {"emotion": 2, ...}
        }
    """
    categories = Counter()
    weak_by_cat = Counter()

    for item in data:
        cat = item.get('category', 'unknown')
        categories[cat] += 1
        if item.get('weak'):
            weak_by_cat[cat] += 1

    return {
        'total': len(data),
        'categories': dict(categories),
        'weak_by_category': dict(weak_by_cat)
    }


def generate_report(lang_code: str, analysis: dict, weak_info: dict) -> str:
    """주간 분석 리포트 생성"""
    lang_names = {'es': '🇪🇸 스페인어', 'ja': '🇯🇵 일본어', 'zh': '🇨🇳 중국어'}
    lang_name = lang_names.get(lang_code, lang_code)

    report = f"""
📚 {lang_name} 주간 분석 리포트 ({date.today().isoformat()})

총 학습 단어: {analysis['total']}개
취약 단어: {len(weak_info['weak_words'])}개

📊 카테고리 분포:
"""
    for cat, count in sorted(analysis['categories'].items(), key=lambda x: -x[1])[:5]:
        weak_count = analysis['weak_by_category'].get(cat, 0)
        report += f"  {cat}: {count}개 (취약: {weak_count}개)\n"

    if weak_info['marked_count'] > 0:
        report += f"\n⚠️ 새로 취약 마킹된 단어 ({weak_info['marked_count']}개):\n"
        for word in weak_info['weak_words'][-5:]:  # 마지막 5개만 표시
            report += f"  • {word}\n"

    return report


def send_telegram_alert(message: str, dry_run: bool = False) -> bool:
    """텔레그램으로 알림 발송"""
    if dry_run:
        print(f"🧪 [DRY-RUN] 텔레그램 발송 예상 내용:\n{message}")
        return True

    try:
        # TelegramBridge 연동 시도
        telegram_script = "/home/rjegj/projects/System_Master/TelegramBridge/send_message.py"
        if os.path.exists(telegram_script):
            import subprocess
            result = subprocess.run(
                ["/home/rjegj/projects/unified_venv/bin/python", telegram_script],
                input=message,
                capture_output=True,
                text=True,
                timeout=10
            )
            return result.returncode == 0
        else:
            # Fallback: 로컬 저장
            alert_dir = PROJECT_DIR / "alerts"
            alert_dir.mkdir(exist_ok=True)
            alert_file = alert_dir / f"vocab_report_{date.today().isoformat()}.txt"
            alert_file.write_text(message, encoding='utf-8')
            print(f"✅ [Alert] {alert_file}에 저장됨")
            return True

    except Exception as e:
        print(f"⚠️ [Telegram] 알림 발송 실패: {e}")
        return False


def log_to_devlog(message: str):
    """DEV_LOG.md에 기록"""
    try:
        devlog_path = Path("/home/rjegj/projects/DEV_LOG.md")
        if devlog_path.exists():
            content = devlog_path.read_text(encoding='utf-8')
            timestamp = date.today().isoformat()
            entry = f"\n## [Night Worker] Vocab Bot 주간 분석 ({timestamp})\n{message}\n"
            devlog_path.write_text(content + entry, encoding='utf-8')
    except Exception as e:
        print(f"⚠️ [DevLog] 기록 실패: {e}")


def analyze_language(lang_code: str, dry_run: bool = False) -> dict:
    """
    특정 언어의 학습 데이터 분석

    Args:
        lang_code: 'es', 'ja', 'zh'
        dry_run: True면 파일에 저장하지 않음

    Returns:
        분석 결과 dict
    """
    json_files = {
        'es': 'learned_data_es.json',
        'ja': 'learned_data_ja.json',
        'zh': 'learned_data_zh.json'
    }

    json_file = PROJECT_DIR / json_files[lang_code]
    data = load_learned_json(json_file)

    if not data:
        return {'error': f'{json_files[lang_code]}를 찾을 수 없습니다'}

    print(f"\n📚 [{lang_code.upper()}] 분석 중...")

    # 1. 취약 단어 마킹
    weak_info = mark_weak_words(data)
    print(f"  • 새로 weak 마킹: {weak_info['marked_count']}개")

    # 2. 카테고리 분석
    analysis = analyze_category_distribution(data)
    print(f"  • 총 단어: {analysis['total']}개")
    print(f"  • 취약 단어: {len(weak_info['weak_words'])}개")

    # 3. 파일 저장 (dry-run이 아닌 경우)
    if not dry_run:
        save_learned_json(json_file, data)
        print(f"  ✅ {json_files[lang_code]} 업데이트됨")

    # 4. 리포트 생성 및 발송
    report = generate_report(lang_code, analysis, weak_info)
    send_telegram_alert(report, dry_run)

    return {
        'lang': lang_code,
        'total_words': analysis['total'],
        'weak_words': len(weak_info['weak_words']),
        'marked_count': weak_info['marked_count'],
        'report': report
    }


def main():
    dry_run = '--dry-run' in sys.argv

    if dry_run:
        print("🧪 [DRY-RUN 모드] 파일이 실제로 저장되지 않습니다.\n")

    print("=" * 60)
    print("📊 Vocab Bot 주간 분석")
    print("=" * 60)

    results = []
    for lang_code in ['es', 'ja', 'zh']:
        result = analyze_language(lang_code, dry_run)
        results.append(result)

    # DEV_LOG 기록
    devlog_msg = f"\n✅ 주간 분석 완료\n"
    for r in results:
        if 'error' not in r:
            devlog_msg += f"  [{r['lang'].upper()}] {r['total_words']}개 단어 (취약: {r['weak_words']}개, 새 weak: {r['marked_count']}개)\n"

    log_to_devlog(devlog_msg)

    print(f"\n✅ 분석 완료!")
    return 0


if __name__ == "__main__":
    sys.exit(main())
