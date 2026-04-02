#!/usr/bin/env python3
"""
Vocab Bot 학습 데이터 마이그레이션: TXT → JSON

기능:
  1. learned_words.txt → learned_data_es.json (중복 제거)
  2. learned_ja.txt → learned_data_ja.json
  3. learned_zh.txt → learned_data_zh.json
  4. Gemini로 각 단어의 카테고리 자동 분류
  5. 기존 .txt 파일은 .bak으로 보존

사용법:
  python migrate_learned_to_json.py          # 실제 실행
  python migrate_learned_to_json.py --dry-run  # 테스트 (실제 저장 안 함)
"""

import os
import json
import sys
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv
from google import genai

# 환경 변수 로드
PROJECT_DIR = Path(__file__).parent
load_dotenv(PROJECT_DIR / '.env')
load_dotenv(PROJECT_DIR.parent / '.secrets' / '.env')

API_KEY = os.getenv('GEMINI_API_KEY')
if not API_KEY:
    print("❌ GEMINI_API_KEY 환경 변수가 설정되지 않았습니다.")
    sys.exit(1)

client = genai.Client(api_key=API_KEY)

# 마이그레이션 설정
MIGRATIONS = {
    'es': {
        'txt_file': 'learned_words.txt',
        'json_file': 'learned_data_es.json',
        'lang_name': '스페인어',
        'categories': ['emotion', 'nature', 'object', 'action', 'food', 'travel', 'abstract', 'time', 'body', 'family']
    },
    'ja': {
        'txt_file': 'learned_ja.txt',
        'json_file': 'learned_data_ja.json',
        'lang_name': '일본어',
        'categories': ['감정', '자연', '물체', '행동', '음식', '여행', '추상', '시간', '신체', '가족']
    },
    'zh': {
        'txt_file': 'learned_zh.txt',
        'json_file': 'learned_data_zh.json',
        'lang_name': '중국어',
        'categories': ['emotion', 'nature', 'object', 'action', 'food', 'travel', 'abstract', 'time', 'body', 'family']
    }
}


def load_txt_file(file_path: Path) -> list:
    """TXT 파일에서 단어 목록 로드"""
    if not file_path.exists():
        return []
    with open(file_path, 'r', encoding='utf-8') as f:
        words = [line.strip() for line in f if line.strip()]
    return words


def classify_words_with_gemini(words: list, lang_code: str) -> dict:
    """
    Gemini를 사용해 단어들을 카테고리별로 분류

    Returns:
        {
            'word1': 'emotion',
            'word2': 'nature',
            ...
        }
    """
    if not words:
        return {}

    config = MIGRATIONS[lang_code]
    categories = config['categories']

    prompt = f"""
    Classify each of the following {config['lang_name']} words into one of these categories:
    {', '.join(categories)}

    Words to classify:
    {', '.join(words)}

    Output as a JSON object where keys are words and values are categories.
    Example: {{"word1": "emotion", "word2": "nature"}}

    IMPORTANT: Every word MUST be assigned to exactly one category. No missing words.
    """

    try:
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=prompt
        )

        text = response.text.strip()
        # JSON 코드블록 제거
        if text.startswith('```json'):
            text = text[7:]
        if text.startswith('```'):
            text = text[3:]
        if text.endswith('```'):
            text = text[:-3]

        classification = json.loads(text.strip())
        print(f"✅ {len(classification)}개 단어 분류 완료")
        return classification

    except Exception as e:
        print(f"⚠️ Gemini 분류 실패: {e}")
        # Fallback: 모든 단어를 첫 번째 카테고리로 분류
        return {word: categories[0] for word in words}


def build_json_data(words: list, classifications: dict) -> list:
    """
    TXT 단어 목록을 JSON 데이터로 변환

    Returns:
        [
            {
                "word": "Feliz",
                "date_added": "2026-04-02",
                "category": "emotion",
                "seen_count": 1,
                "weak": False,
                "weak_date": None
            },
            ...
        ]
    """
    today = datetime.now().strftime("%Y-%m-%d")
    data = []

    for word in words:
        category = classifications.get(word, 'abstract')
        data.append({
            "word": word,
            "date_added": today,
            "category": category,
            "seen_count": 1,
            "weak": False,
            "weak_date": None
        })

    return data


def migrate_language(lang_code: str, dry_run: bool = False) -> bool:
    """
    특정 언어의 learned_*.txt를 JSON으로 마이그레이션

    Args:
        lang_code: 'es', 'ja', 'zh'
        dry_run: True면 파일에 저장하지 않음

    Returns:
        성공 여부
    """
    config = MIGRATIONS[lang_code]
    txt_file = PROJECT_DIR / config['txt_file']
    json_file = PROJECT_DIR / config['json_file']
    bak_file = txt_file.with_suffix('.txt.bak')

    print(f"\n{'='*60}")
    print(f"🔄 [{config['lang_name']}] 마이그레이션 시작")
    print(f"{'='*60}")

    # 1. TXT 파일 로드
    print(f"📖 {config['txt_file']} 로드 중...")
    words = load_txt_file(txt_file)

    if not words:
        print(f"⚠️ {config['txt_file']}에 단어가 없습니다. 스킵")
        return False

    print(f"✅ {len(words)}개 단어 로드됨")

    # 2. 중복 제거
    unique_words = list(dict.fromkeys(words))  # 순서 유지하면서 중복 제거
    if len(unique_words) < len(words):
        print(f"🧹 중복 제거: {len(words)} → {len(unique_words)}개 ({len(words) - len(unique_words)}개 제거)")

    # 3. Gemini로 카테고리 분류
    print(f"🧠 Gemini로 카테고리 분류 중...")
    classifications = classify_words_with_gemini(unique_words, lang_code)

    # 4. JSON 데이터 생성
    print(f"📝 JSON 데이터 생성 중...")
    json_data = build_json_data(unique_words, classifications)

    # 5. Dry-run 또는 저장
    if dry_run:
        print(f"🧪 [DRY-RUN] 변경사항 없음 (실제 저장 안 함)")
        print(f"  예상 파일: {json_file}")
        print(f"  예상 데이터: {len(json_data)}개 항목")
        return True

    # 6. 기존 TXT 파일 백업
    if txt_file.exists() and not bak_file.exists():
        import shutil
        shutil.copy2(txt_file, bak_file)
        print(f"💾 백업 완료: {bak_file}")

    # 7. JSON 파일 저장
    with open(json_file, 'w', encoding='utf-8') as f:
        json.dump(json_data, f, ensure_ascii=False, indent=2)

    print(f"✅ {json_file} 저장 완료")

    # 8. 요약
    categories_count = {}
    for item in json_data:
        cat = item['category']
        categories_count[cat] = categories_count.get(cat, 0) + 1

    print(f"\n📊 카테고리 분포:")
    for cat, count in sorted(categories_count.items(), key=lambda x: -x[1]):
        print(f"  {cat}: {count}개")

    return True


def main():
    dry_run = '--dry-run' in sys.argv

    if dry_run:
        print("🧪 [DRY-RUN 모드] 파일이 실제로 저장되지 않습니다.")

    results = {}
    for lang_code in ['es', 'ja', 'zh']:
        results[lang_code] = migrate_language(lang_code, dry_run)

    print(f"\n{'='*60}")
    print("📋 마이그레이션 결과 요약")
    print(f"{'='*60}")
    for lang_code, success in results.items():
        status = "✅ 성공" if success else "⏭️ 스킵"
        lang_name = MIGRATIONS[lang_code]['lang_name']
        print(f"  {lang_name}: {status}")

    if all(results.values()):
        print(f"\n✅ 모든 언어 마이그레이션 완료!")
        return 0
    else:
        print(f"\n⚠️ 일부 언어에서 오류 발생")
        return 1


if __name__ == "__main__":
    sys.exit(main())
