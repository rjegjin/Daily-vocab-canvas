"""
스페인어 반사 신경 패턴 + 화학 용어
매일 화학반응 중심의 Thinking Filler 패턴 + 화학 용어 발송
"""
import os
import json
from datetime import datetime
from dotenv import load_dotenv
from card_engine import generate_tts, send_audio_to_telegram, send_text_to_telegram

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
# 패턴 데이터 (주 단위 순환)
# -------------------------------------------------------------------
PATTERNS = [
    {
        "day_name": "월",
        "pattern": "Lo que pasa es que...",
        "explanation": "상황을 설명하는 가장 기본적인 표현 (실제로는 뭐냐면...)",
        "example": "Lo que pasa es que la reacción exotérmica libera mucho calor al ambiente.",
        "example_translation": "실제로는, 발열반응은 주변에 많은 열을 방출한다.",
    },
    {
        "day_name": "화",
        "pattern": "Esto se debe a...",
        "explanation": "원인을 설명할 때 쓰는 표현 (이것은 ~때문이다)",
        "example": "Esto se debe a que los reactivos tienen baja energía de activación.",
        "example_translation": "이것은 반응물들이 낮은 활성화 에너지를 가지기 때문이다.",
    },
    {
        "day_name": "수",
        "pattern": "A medida que... , ...",
        "explanation": "변화의 상관관계를 설명 (~함에 따라, ~한다)",
        "example": "A medida que aumenta la temperatura, la velocidad de reacción aumenta.",
        "example_translation": "온도가 올라감에 따라 반응 속도도 올라간다.",
    },
    {
        "day_name": "목",
        "pattern": "Teniendo en cuenta que...",
        "explanation": "전제 조건을 깔 때 유용 (~를 고려하면)",
        "example": "Teniendo en cuenta que el catalizador no se consume, podemos reutilizarlo.",
        "example_translation": "촉매가 소모되지 않는다는 것을 고려하면, 우리는 그것을 재사용할 수 있다.",
    },
    {
        "day_name": "금",
        "pattern": "Me da la impresión de que...",
        "explanation": "의견을 제시할 때 쓰는 세련된 표현 (내 인상은...인 것 같다)",
        "example": "Me da la impresión de que este equilibrio químico es reversible.",
        "example_translation": "내 인상은 이 화학평형이 가역적인 것 같다.",
    },
    {
        "day_name": "토",
        "pattern": "Desde mi punto de vista...",
        "explanation": "관점에서 설명 (내 관점에서는...)",
        "example": "Desde mi punto de vista, la energía de enlace es crucial en las reacciones.",
        "example_translation": "내 관점에서, 결합에너지는 반응에서 결정적이다.",
    },
    {
        "day_name": "일",
        "pattern": "Por lo tanto...",
        "explanation": "결론을 내릴 때 쓰는 표현 (따라서...)",
        "example": "Por lo tanto, el equilibrio químico es dinámico y constante.",
        "example_translation": "따라서 화학평형은 역동적이면서도 항상 유지된다.",
    },
]

# -------------------------------------------------------------------
# 화학 용어 풀 (매주 2-3개씩 다양하게)
# -------------------------------------------------------------------
CHEMISTRY_TERMS = [
    ("reacción exotérmica", "발열반응", "Una reacción que libera energía en forma de calor."),
    ("reacción endotérmica", "흡열반응", "Una reacción que absorbe energía del ambiente."),
    ("catalizador", "촉매", "Una sustancia que acelera una reacción sin ser consumida."),
    ("energía de activación", "활성화 에너지", "La energía mínima necesaria para que ocurra una reacción."),
    ("equilibrio químico", "화학평형", "El estado donde las velocidades de reacción directa e inversa son iguales."),
    ("mol", "몰", "La unidad de medida para la cantidad de sustancia."),
    ("pH", "pH", "Una medida de la acidez o alcalinidad de una solución."),
    ("oxidación", "산화", "La pérdida de electrones en una sustancia."),
    ("reducción", "환원", "La ganancia de electrones en una sustancia."),
    ("enlace químico", "결합", "La fuerza que mantiene unidos los átomos en una molécula."),
]

# -------------------------------------------------------------------
# 메인
# -------------------------------------------------------------------
if __name__ == "__main__":
    print(f"=== 🇪🇸 Spanish Pattern Reflexes ({datetime.now().strftime('%Y-%m-%d %H:%M:%S')}) ===")

    # 오늘의 요일 기반 패턴 선택
    day_of_week = datetime.now().weekday()  # 0=월, 6=일
    pattern_data = PATTERNS[day_of_week % len(PATTERNS)]

    # 이번 주의 화학 용어 2개 선택
    week_num = datetime.now().isocalendar()[1]
    term_indices = [
        (week_num * 2) % len(CHEMISTRY_TERMS),
        (week_num * 2 + 1) % len(CHEMISTRY_TERMS),
    ]

    selected_terms = [CHEMISTRY_TERMS[i] for i in term_indices]

    # 텍스트 생성
    day_name = pattern_data['day_name']
    text_content = f"""📌 *반사 신경 패턴* ({day_name}요일)

*패턴:* `{pattern_data['pattern']}`
*의미:* {pattern_data['explanation']}

*예문:*
"{pattern_data['example']}"

*한국어:*
"{pattern_data['example_translation']}"

*이 주의 화학 용어:*
"""

    for span, meaning, explanation in selected_terms:
        text_content += f"\n• `{span}` — {meaning}\n  {explanation}"

    print(text_content)

    # 텔레그램으로 텍스트 전송
    send_text_to_telegram(text_content, TOKEN, CHAT_ID)

    # 패턴 음성 생성 및 전송
    pattern_text = f"{pattern_data['pattern']}. {pattern_data['example']}"
    pattern_audio = os.path.join(PROJECT_DIR, "pattern_audio.mp3")

    if generate_tts(pattern_text, 'es-ES', pattern_audio):
        send_audio_to_telegram(pattern_audio, TOKEN, CHAT_ID, caption="🎵 반사 신경 패턴 음성")
        if os.path.exists(pattern_audio):
            os.remove(pattern_audio)

    # 용어 음성 생성 및 전송 (첫 번째 용어만)
    term_text = f"{selected_terms[0][0]}. {selected_terms[0][2]}"
    term_audio = os.path.join(PROJECT_DIR, "term_audio.mp3")

    if generate_tts(term_text, 'es-ES', term_audio):
        send_audio_to_telegram(term_audio, TOKEN, CHAT_ID, caption="🎵 화학 용어 발음")
        if os.path.exists(term_audio):
            os.remove(term_audio)

    print("✅ 패턴 발송 완료")
