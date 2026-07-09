"""
일본어 음독 규칙 + 한/중/일 비교
한국어 한자음 → 일본어 음독 변환 규칙 시각화
"""
import os
import json
from datetime import datetime
from dotenv import load_dotenv
from card_engine import generate_tts, send_audio_to_telegram, send_text_to_telegram
from vocab_feedback import merge_supplement_items, save_latest_supplement, send_supplement_feedback_buttons

# -------------------------------------------------------------------
# 환경 변수
# -------------------------------------------------------------------
PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(PROJECT_DIR, '.env'))
load_dotenv(os.path.join(os.path.dirname(PROJECT_DIR), '.secrets', '.env'))

TOKEN   = os.getenv('VOCAB_BOT_TOKEN') or os.getenv('GEMINI_BOT_TOKEN')
CHAT_ID = os.getenv('VOCAB_CHAT_ID')   or os.getenv('GEMINI_CHAT_ID')

if not TOKEN or not CHAT_ID:
    print("❌ 환경 변수가 설정되지 않았습니다.")
    exit(1)

# -------------------------------------------------------------------
# 일반 단어 풀 (한자, 한국음, 일본음독, 중국음, 의미)
# -------------------------------------------------------------------
WORDS = [
    # 학교/교육
    ("学", "학", "がく", "xué", "study"),
    ("校", "교", "こう", "xiào", "school"),
    ("学校", "학교", "がっこう", "xuéxiào", "school"),
    ("先生", "선생", "せんせい", "xiānsheng", "teacher"),
    ("学生", "학생", "がくせい", "xuésheng", "student"),
    ("本", "본/권", "ほん", "běn", "book"),
    ("読む", "독/읽다", "よむ", "dú", "read"),
    ("書く", "서/쓰다", "かく", "xiě", "write"),

    # 자연/날씨
    ("水", "수", "みず", "shuǐ", "water"),
    ("火", "화", "ひ", "huǒ", "fire"),
    ("土", "토", "つち", "tǔ", "earth"),
    ("木", "목", "き", "mù", "tree"),
    ("金", "금", "きん", "jīn", "gold/money"),
    ("日", "일", "ひ", "rì", "sun/day"),
    ("月", "월", "つき", "yuè", "moon"),
    ("星", "성", "ほし", "xīng", "star"),
    ("山", "산", "やま", "shān", "mountain"),
    ("川", "천", "かわ", "chuān", "river"),
    ("海", "해", "うみ", "hǎi", "sea"),
    ("森", "삼", "もり", "sēn", "forest"),
    ("雲", "운", "くも", "yún", "cloud"),
    ("雨", "우", "あめ", "yǔ", "rain"),

    # 가족
    ("父", "부", "ちち", "fù", "father"),
    ("母", "모", "はは", "mǔ", "mother"),
    ("兄", "형", "あに", "xiōng", "older brother"),
    ("弟", "제", "おとうと", "dì", "younger brother"),
    ("妹", "매", "いもうと", "mèi", "younger sister"),
    ("姉", "자", "あね", "jiě", "older sister"),
    ("子", "자", "こ", "zǐ", "child"),

    # 일상 활동
    ("食べる", "식/먹다", "たべる", "chī", "eat"),
    ("飲む", "음/마시다", "のむ", "hē", "drink"),
    ("寝る", "면/자다", "ねる", "shuì", "sleep"),
    ("起きる", "기/일어나다", "おきる", "qǐ", "wake up"),
    ("走る", "주/달리다", "はしる", "zǒu", "run"),
    ("歩く", "보/걷다", "あるく", "bù", "walk"),
    ("働く", "동/일하다", "はたらく", "gōng", "work"),

    # 형용사
    ("大きい", "대/크다", "おおきい", "dà", "big"),
    ("小さい", "소/작다", "ちいさい", "xiǎo", "small"),
    ("長い", "장/길다", "ながい", "cháng", "long"),
    ("短い", "단/짧다", "みじかい", "duǎn", "short"),
    ("高い", "고/높다", "たかい", "gāo", "high"),
    ("低い", "저/낮다", "ひくい", "dī", "low"),
    ("速い", "속/빠르다", "はやい", "kuài", "fast"),
    ("遅い", "지/느리다", "おそい", "màn", "slow"),
    ("熱い", "열/뜨겁다", "あつい", "rè", "hot"),
    ("冷たい", "냉/차갑다", "つめたい", "lěng", "cold"),
]

# -------------------------------------------------------------------
# 음독 규칙 매핑
# -------------------------------------------------------------------
ONKUN_RULES = {
    "ㄱ": ["く", "き", "ご", "가"],
    "ㄴ": ["ん", "나"],
    "ㄹ": ["つ", "ち", "ろ", "라"],
    "ㅇ": ["う", "오"],
}

# -------------------------------------------------------------------
# 메인
# -------------------------------------------------------------------
if __name__ == "__main__":
    print(f"=== 🇯🇵 Japanese Onkun Rules ({datetime.now().strftime('%Y-%m-%d %H:%M:%S')}) ===")

    # 오늘의 요일 기반 5개 단어 선택
    day_of_week = datetime.now().weekday()  # 0=월, 6=일
    base_idx = (day_of_week * 5) % len(WORDS)
    selected_words = WORDS[base_idx:base_idx+5] if base_idx + 5 <= len(WORDS) else WORDS[base_idx:] + WORDS[:5-(len(WORDS)-base_idx)]
    rule_items = [
        {
            "id": f"onkun_{kanji}",
            "title": f"{kanji} ({jp_onkun})",
            "rule_name": "한국어 한자음과 일본어 읽기 비교",
            "category": "音読み/訓読み",
        }
        for kanji, kor_sound, jp_onkun, zh_pinyin, meaning in selected_words
    ]

    # 텍스트 생성
    text_content = f"""🎯 *日本語 音訓ルール* ({datetime.now().strftime('%A')})

한국어 한자음 → 일본어 음독 변환 과정을 보세요.
"""

    for kanji, kor_sound, jp_onkun, zh_pinyin, meaning in selected_words:
        # 간단한 설명
        text_content += f"""
*{kanji}* ({meaning})
한국: `{kor_sound}` 日本: `{jp_onkun}` 中文: `{zh_pinyin}`
"""

    print(text_content)

    # 텔레그램으로 텍스트 전송
    send_text_to_telegram(text_content, TOKEN, CHAT_ID)
    merge_supplement_items("ja_rules", rule_items)
    save_latest_supplement("ja_rules", rule_items)
    send_supplement_feedback_buttons("ja_rules")

    # 각 단어별 음성 생성 및 전송 (처음 3개만)
    for i, (kanji, kor_sound, jp_onkun, zh_pinyin, meaning) in enumerate(selected_words[:3]):
        try:
            audio_path = os.path.join(PROJECT_DIR, f"ja_rule_{i}_{kanji}.mp3")

            # 음성 생성 (일본어 발음)
            if generate_tts(kanji, 'ja-JP', audio_path):
                send_audio_to_telegram(audio_path, TOKEN, CHAT_ID, caption=f"🎵 {kanji} ({jp_onkun}) - {meaning}")
                if os.path.exists(audio_path):
                    os.remove(audio_path)
        except Exception as e:
            print(f"⚠️ {kanji} 음성 생성 실패: {e}")

    print("✅ 일본어 음독 규칙 발송 완료")
