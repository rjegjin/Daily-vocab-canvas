"""
스페인어 반사 신경 패턴 + 일상/학술 표현
매일 바로 꺼내 쓸 수 있는 Thinking Filler 패턴과 표현 묶음 발송
"""
import os
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
# 패턴 데이터 (요일별 순환)
# -------------------------------------------------------------------
PATTERNS = [
    {
        "day_name": "월",
        "pattern": "Lo que pasa es que...",
        "explanation": "상황을 설명하는 가장 기본적인 표현 (실제로는 뭐냐면...)",
        "example": "Lo que pasa es que necesito un poco más de tiempo para revisarlo.",
        "example_translation": "실제로는, 검토할 시간이 조금 더 필요해.",
    },
    {
        "day_name": "화",
        "pattern": "Esto se debe a...",
        "explanation": "원인을 설명할 때 쓰는 표현 (이것은 ~때문이다)",
        "example": "Esto se debe a que los datos no son suficientes para sacar una conclusión.",
        "example_translation": "이것은 결론을 내리기에 데이터가 충분하지 않기 때문이다.",
    },
    {
        "day_name": "수",
        "pattern": "A medida que..., ...",
        "explanation": "변화의 상관관계를 설명 (~함에 따라, ~한다)",
        "example": "A medida que practicamos más, hablamos con más naturalidad.",
        "example_translation": "더 많이 연습할수록 더 자연스럽게 말하게 된다.",
    },
    {
        "day_name": "목",
        "pattern": "Teniendo en cuenta que...",
        "explanation": "전제 조건을 깔 때 유용 (~를 고려하면)",
        "example": "Teniendo en cuenta que el plazo es corto, conviene priorizar lo esencial.",
        "example_translation": "기한이 짧다는 점을 고려하면, 핵심을 우선해야 한다.",
    },
    {
        "day_name": "금",
        "pattern": "Me da la impresión de que...",
        "explanation": "의견을 제시할 때 쓰는 세련된 표현 (내 인상은...인 것 같다)",
        "example": "Me da la impresión de que todavía falta una explicación más clara.",
        "example_translation": "아직 더 명확한 설명이 부족한 것 같다.",
    },
    {
        "day_name": "토",
        "pattern": "Desde mi punto de vista...",
        "explanation": "관점에서 설명 (내 관점에서는...)",
        "example": "Desde mi punto de vista, el problema principal es la falta de contexto.",
        "example_translation": "내 관점에서 핵심 문제는 맥락 부족이다.",
    },
    {
        "day_name": "일",
        "pattern": "Por lo tanto...",
        "explanation": "결론을 내릴 때 쓰는 표현 (따라서...)",
        "example": "Por lo tanto, necesitamos comparar las opciones antes de decidir.",
        "example_translation": "따라서 결정하기 전에 선택지를 비교해야 한다.",
    },
]

# -------------------------------------------------------------------
# 표현 풀 (매주 3개씩 순환)
# -------------------------------------------------------------------
EXPRESSION_BANK = [
    ("para ser sincero", "솔직히 말하면", "Para ser sincero, no estoy completamente convencido."),
    ("si no me equivoco", "내가 틀리지 않았다면", "Si no me equivoco, la reunión empieza a las nueve."),
    ("en otras palabras", "다시 말해", "En otras palabras, necesitamos una solución más simple."),
    ("a mi modo de ver", "내가 보기에는", "A mi modo de ver, el argumento necesita más evidencia."),
    ("por una parte... por otra parte...", "한편으로는... 다른 한편으로는...", "Por una parte es práctico; por otra parte, cuesta más."),
    ("vale la pena señalar que", "짚고 넘어갈 만한 점은", "Vale la pena señalar que el resultado no es definitivo."),
    ("no se trata de..., sino de...", "~의 문제가 아니라 ~의 문제다", "No se trata de memorizar, sino de comprender el patrón."),
    ("en la vida cotidiana", "일상생활에서", "En la vida cotidiana, esta expresión suena muy natural."),
    ("desde una perspectiva académica", "학술적 관점에서", "Desde una perspectiva académica, conviene definir los términos."),
    ("a largo plazo", "장기적으로", "A largo plazo, la constancia importa más que la velocidad."),
    ("en resumen", "요약하면", "En resumen, la idea principal es bastante clara."),
    ("me gustaría subrayar que", "강조하고 싶은 것은", "Me gustaría subrayar que la precisión también importa."),
    ("hasta cierto punto", "어느 정도는", "Hasta cierto punto, estoy de acuerdo con esa interpretación."),
    ("por el momento", "현재로서는", "Por el momento, no tenemos suficiente información."),
    ("dicho de otra manera", "다르게 말하면", "Dicho de otra manera, el método funciona solo en ciertos casos."),
]

# -------------------------------------------------------------------
# 메인
# -------------------------------------------------------------------
if __name__ == "__main__":
    print(f"=== 🇪🇸 Spanish Pattern Reflexes ({datetime.now().strftime('%Y-%m-%d %H:%M:%S')}) ===")

    day_of_week = datetime.now().weekday()  # 0=월, 6=일
    pattern_data = PATTERNS[day_of_week % len(PATTERNS)]

    week_num = datetime.now().isocalendar()[1]
    selected_expressions = [
        EXPRESSION_BANK[(week_num * 3 + offset) % len(EXPRESSION_BANK)]
        for offset in range(3)
    ]

    day_name = pattern_data['day_name']
    text_content = f"""📌 *반사 신경 패턴* ({day_name}요일)

*패턴:* `{pattern_data['pattern']}`
*의미:* {pattern_data['explanation']}

*예문:*
"{pattern_data['example']}"

*한국어:*
"{pattern_data['example_translation']}"

*오늘의 일상/학술 표현:*
"""

    for span, meaning, example in selected_expressions:
        text_content += f"\n• `{span}` — {meaning}\n  {example}"

    print(text_content)
    send_text_to_telegram(text_content, TOKEN, CHAT_ID)

    pattern_text = f"{pattern_data['pattern']}. {pattern_data['example']}"
    pattern_audio = os.path.join(PROJECT_DIR, "pattern_audio.mp3")

    if generate_tts(pattern_text, 'es-ES', pattern_audio):
        send_audio_to_telegram(pattern_audio, TOKEN, CHAT_ID, caption="🎵 반사 신경 패턴 음성")
        if os.path.exists(pattern_audio):
            os.remove(pattern_audio)

    expression_text = f"{selected_expressions[0][0]}. {selected_expressions[0][2]}"
    expression_audio = os.path.join(PROJECT_DIR, "expression_audio.mp3")

    if generate_tts(expression_text, 'es-ES', expression_audio):
        send_audio_to_telegram(expression_audio, TOKEN, CHAT_ID, caption="🎵 표현 발음")
        if os.path.exists(expression_audio):
            os.remove(expression_audio)

    print("✅ 패턴 발송 완료")
