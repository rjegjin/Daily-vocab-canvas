"""
중국어 성조 시각화 + HSK 1~2급 단어
매일 성조 물리 벡터 시각화 + 음성 발송
"""
import os
import json
from datetime import datetime
from dotenv import load_dotenv
from card_engine import generate_tts, send_audio_to_telegram, send_text_to_telegram, generate_tone_chart, send_to_telegram
from vocab_feedback import (
    load_supplement_seen,
    load_supplement_weak,
    merge_supplement_items,
    save_latest_supplement,
    send_supplement_feedback_buttons,
)

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
# HSK 1~2급 단어 풀 (성조별로 정렬)
# (단어, 병음, 뜻, 예문)
# -------------------------------------------------------------------
HSK_WORDS = [
    # 1성 (High Flat) ─
    ("学", "xué", "study", "我学中文", "I study Chinese"),
    ("天", "tiān", "day/sky", "今天天气好", "The weather is nice today"),
    ("妈", "mā", "mother", "我的妈妈", "My mother"),
    ("爸", "bà", "father", "我的爸爸", "My father"),
    ("茶", "chá", "tea", "喝茶", "Drink tea"),

    # 2성 (Rising) ↗
    ("来", "lái", "come", "你来了", "You came"),
    ("去", "qù", "go", "去学校", "Go to school"),
    ("人", "rén", "person", "好人", "Good person"),
    ("男", "nán", "male", "男孩", "Boy"),
    ("女", "nǚ", "female", "女孩", "Girl"),

    # 3성 (Low Dip) ∨
    ("你", "nǐ", "you", "你好", "Hello"),
    ("我", "wǒ", "I/me", "我是学生", "I am a student"),
    ("水", "shuǐ", "water", "喝水", "Drink water"),
    ("鼠", "shǔ", "mouse/rat", "老鼠", "Mouse"),
    ("手", "shǒu", "hand", "握手", "Shake hands"),

    # 4성 (Falling) ↘
    ("是", "shì", "is/am", "我是老师", "I am a teacher"),
    ("去", "qù", "go", "去哪儿", "Where to go"),
    ("书", "shū", "book", "看书", "Read a book"),
    ("写", "xiě", "write", "写字", "Write characters"),
    ("坐", "zuò", "sit", "坐下", "Sit down"),
]

MINIMAL_PAIR_SETS = [
    {
        "id": "tone_pair_ma",
        "base_syllable": "ma",
        "pairs": [
            {"tone": 1, "char": "妈", "pinyin": "mā", "meaning": "어머니"},
            {"tone": 2, "char": "麻", "pinyin": "má", "meaning": "삼, 마비"},
            {"tone": 3, "char": "马", "pinyin": "mǎ", "meaning": "말"},
            {"tone": 4, "char": "骂", "pinyin": "mà", "meaning": "욕하다"},
        ],
        "context_sentences": ["我妈妈很忙。", "请不要骂人。"],
    },
    {
        "id": "tone_pair_shi",
        "base_syllable": "shi",
        "pairs": [
            {"tone": 1, "char": "师", "pinyin": "shī", "meaning": "스승"},
            {"tone": 2, "char": "十", "pinyin": "shí", "meaning": "열"},
            {"tone": 3, "char": "史", "pinyin": "shǐ", "meaning": "역사"},
            {"tone": 4, "char": "是", "pinyin": "shì", "meaning": "~이다"},
        ],
        "context_sentences": ["老师教历史。", "这是十本书。"],
    },
    {
        "id": "tone_pair_mai",
        "base_syllable": "mai",
        "pairs": [
            {"tone": 2, "char": "埋", "pinyin": "mái", "meaning": "묻다"},
            {"tone": 3, "char": "买", "pinyin": "mǎi", "meaning": "사다"},
            {"tone": 4, "char": "卖", "pinyin": "mài", "meaning": "팔다"},
        ],
        "context_sentences": ["我想买水果。", "他卖咖啡。"],
    },
]

# (성조 이미지로 충분 - 텍스트 아트 제거)

# -------------------------------------------------------------------
# 메인
# -------------------------------------------------------------------
def get_tone_number(pinyin: str) -> int:
    """병음 문자열에서 성조 숫자 추출"""
    tone_map = {'ā': 1, 'á': 2, 'ǎ': 3, 'à': 4,
                'ē': 1, 'é': 2, 'ě': 3, 'è': 4,
                'ī': 1, 'í': 2, 'ǐ': 3, 'ì': 4,
                'ō': 1, 'ó': 2, 'ǒ': 3, 'ò': 4,
                'ū': 1, 'ú': 2, 'ǔ': 3, 'ù': 4,
                'ǖ': 1, 'ǘ': 2, 'ǚ': 3, 'ǜ': 4}
    for char in pinyin:
        if char in tone_map:
            return tone_map[char]
    return 1

def choose_minimal_pair():
    weak_ids = load_supplement_weak("zh_tones")
    if weak_ids:
        for item in MINIMAL_PAIR_SETS:
            if item["id"] in weak_ids:
                return item
    seen = set(load_supplement_seen("zh_tones"))
    for item in MINIMAL_PAIR_SETS:
        if item["id"] not in seen:
            return item
    return MINIMAL_PAIR_SETS[datetime.now().toordinal() % len(MINIMAL_PAIR_SETS)]

if __name__ == "__main__":
    print(f"=== 🇨🇳 Chinese Tone Visualization ({datetime.now().strftime('%Y-%m-%d %H:%M:%S')}) ===")

    # 오늘의 요일 기반 5개 단어 선택 (다양한 성조)
    day_of_week = datetime.now().weekday()  # 0=월, 6=일
    base_idx = (day_of_week * 5) % len(HSK_WORDS)
    selected_words = HSK_WORDS[base_idx:base_idx+5] if base_idx + 5 <= len(HSK_WORDS) else HSK_WORDS[base_idx:] + HSK_WORDS[:5-(len(HSK_WORDS)-base_idx)]
    minimal_pair = choose_minimal_pair()

    # 텍스트 생성 (간단히: 단어, 병음, 뜻, 예문만)
    text_content = f"""🎵 *HSK 1~2级 成调学习* ({datetime.now().strftime('%A')})

아래 이미지의 성조 곡선과 함께 들어보세요.
"""

    for char, pinyin, meaning, example, example_en in selected_words:
        text_content += f"""
*{char}* `{pinyin}` — {meaning}
"{example}" ({example_en})
"""

    text_content += f"""
━━━━━━━━━━━━━━━━━━
🎯 *최소대립쌍* `{minimal_pair['base_syllable']}`
"""
    for pair in minimal_pair["pairs"]:
        text_content += f"{pair['char']} `{pair['pinyin']}` — {pair['meaning']}\n"
    text_content += "\n맥락 예문:\n"
    for sentence in minimal_pair["context_sentences"]:
        text_content += f"- {sentence}\n"

    print(text_content)

    # 텔레그램으로 텍스트 전송
    send_text_to_telegram(text_content, TOKEN, CHAT_ID)
    tone_item = {
        "id": minimal_pair["id"],
        "title": f"{minimal_pair['base_syllable']} 최소대립쌍",
        "base_syllable": minimal_pair["base_syllable"],
        "category": "minimal_pair",
    }
    merge_supplement_items("zh_tones", [tone_item])
    save_latest_supplement("zh_tones", [tone_item])
    send_supplement_feedback_buttons("zh_tones")

    # 성조 곡선 이미지 생성 및 전송
    tone_chart_path = os.path.join(PROJECT_DIR, "tone_chart.png")
    if generate_tone_chart(tone_chart_path):
        send_to_telegram(tone_chart_path, TOKEN, CHAT_ID)
        if os.path.exists(tone_chart_path):
            os.remove(tone_chart_path)

    # 각 단어별 음성 생성 및 전송 (처음 3개만)
    for i, (char, pinyin, meaning, example, _) in enumerate(selected_words[:3]):
        try:
            audio_path = os.path.join(PROJECT_DIR, f"tone_{i}_{char}.mp3")

            # 병음 정규화 (성조 기호 제거 후 숫자로 표기 - TTS용)
            pinyin_for_tts = pinyin.replace('ā', 'a1').replace('á', 'a2').replace('ǎ', 'a3').replace('à', 'a4')
            pinyin_for_tts = pinyin_for_tts.replace('ē', 'e1').replace('é', 'e2').replace('ě', 'e3').replace('è', 'e4')
            pinyin_for_tts = pinyin_for_tts.replace('ī', 'i1').replace('í', 'i2').replace('ǐ', 'i3').replace('ì', 'i4')
            pinyin_for_tts = pinyin_for_tts.replace('ō', 'o1').replace('ó', 'o2').replace('ǒ', 'o3').replace('ò', 'o4')
            pinyin_for_tts = pinyin_for_tts.replace('ū', 'u1').replace('ú', 'u2').replace('ǔ', 'u3').replace('ù', 'u4')

            # 음성 생성 (원문 그대로)
            if generate_tts(example, 'zh-CN', audio_path):
                send_audio_to_telegram(audio_path, TOKEN, CHAT_ID, caption=f"🎵 {char} ({pinyin}) - {meaning}")
                if os.path.exists(audio_path):
                    os.remove(audio_path)
        except Exception as e:
            print(f"⚠️ {char} 음성 생성 실패: {e}")

    try:
        pair_script = "。 ".join(
            [f"{pair['char']}，{pair['pinyin']}" for pair in minimal_pair["pairs"]]
            + minimal_pair["context_sentences"]
        )
        audio_path = os.path.join(PROJECT_DIR, f"tone_pair_{minimal_pair['base_syllable']}.mp3")
        if generate_tts(pair_script, 'cmn-CN', audio_path):
            send_audio_to_telegram(audio_path, TOKEN, CHAT_ID, caption=f"🎧 최소대립쌍: {minimal_pair['base_syllable']}")
            if os.path.exists(audio_path):
                os.remove(audio_path)
    except Exception as e:
        print(f"⚠️ 최소대립쌍 음성 생성 실패: {e}")

    print("✅ 성조 시각화 발송 완료")
