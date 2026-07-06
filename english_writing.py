"""
English writing prompt and feedback.
"""
import sys
import json
from datetime import date, datetime

from card_engine import check_budget_exit
from english_core import (
    LEARNED_EN_PHRASE_FILE,
    WRITING_SESSIONS_FILE,
    WRITING_SUBMISSIONS_FILE,
    clear_writing_pending,
    generate_json,
    get_state,
    read_json,
    send_message,
    set_writing_pending,
    write_json,
)

REQUIRED_PROMPT_KEYS = {
    "date",
    "topic_ko",
    "difficulty",
    "target_connectives",
    "structure_map",
    "model_paragraph",
    "vocabulary_boost",
    "submission_prompt",
}


def should_send_today():
    return datetime.now().weekday() == 6


def generate_prompt():
    prompt = f"""
Create one weekly English writing assignment as JSON for a Korean learner.
Date: {date.today().isoformat()}
Target level: B2-C1.

Required keys:
- date
- topic_ko
- difficulty
- target_connectives: 4 useful connectives
- structure_map: object with 5-6 Korean guidance entries
- model_paragraph: 1-2 strong English model sentences
- vocabulary_boost: 4 useful words/phrases
- submission_prompt: Korean instruction for writing 150-200 words

Return raw JSON only. No markdown.
"""
    return generate_json(prompt, REQUIRED_PROMPT_KEYS, expect_list=False)


def format_prompt(item):
    lines = [
        "✍️ *이번 주 영어 글쓰기 과제*",
        "",
        f"주제: {item['topic_ko']}",
        f"목표 난이도: {item['difficulty']} | 150-200단어",
        "",
        "📐 *추천 구조:*",
    ]
    for title, detail in item["structure_map"].items():
        lines.append(f"• {title} — {detail}")
    lines.extend(["", "🔑 *써먹을 표현:*", " / ".join(item["target_connectives"])])
    lines.extend(["", "💡 *모범 문장 힌트:*", f"\"{item['model_paragraph']}\""])
    lines.extend(["", "📚 *어휘 부스터:*", " / ".join(item["vocabulary_boost"])])
    lines.extend(["", item["submission_prompt"]])
    return "\n".join(lines)


def send_writing_prompt(force=False):
    if not force and not should_send_today():
        print("⏭️ 영어 글쓰기 과제는 일요일만 발송합니다.")
        return
    check_budget_exit("en")
    item = generate_prompt()
    sessions = read_json(WRITING_SESSIONS_FILE, [])
    sessions.append({
        "date": date.today().isoformat(),
        "topic_ko": item["topic_ko"],
        "difficulty": item.get("difficulty"),
        "target_connectives": item.get("target_connectives", []),
        "vocabulary_boost": item.get("vocabulary_boost", []),
        "submitted": False,
        "submission_count": 0,
        "latest_scores": None,
        "feedback_sent": False,
    })
    write_json(WRITING_SESSIONS_FILE, sessions[-52:])
    set_writing_pending(item["topic_ko"])
    send_message(format_prompt(item))
    print("✅ 영어 글쓰기 과제 발송 완료")


def recent_phrase_context():
    state = get_state()
    latest = state.get("latest_en_phrase", {}).get("items", [])
    latest_phrases = [item.get("phrase") for item in latest if item.get("phrase")]
    learned = read_json(LEARNED_EN_PHRASE_FILE, [])
    weak_phrases = [item.get("phrase") for item in learned if item.get("weak") and item.get("phrase")]
    return {
        "latest_phrases": latest_phrases[:8],
        "weak_phrases": weak_phrases[:8],
    }


def generate_feedback(submission: str, phrase_context=None):
    phrase_context = phrase_context or recent_phrase_context()
    prompt = f"""
Give Korean feedback on this English writing submission.

Student text:
{submission}

Recent phrase-card expressions:
{json.dumps(phrase_context.get("latest_phrases", []), ensure_ascii=False)}

Weak phrase expressions the learner has marked:
{json.dumps(phrase_context.get("weak_phrases", []), ensure_ascii=False)}

Return JSON with keys:
- strengths: list of 2 short Korean comments
- revisions: list of objects with original, improved, reason_ko
- scores: object with grammar, vocabulary, structure integers from 1 to 5
- phrase_usage: object with used_well, awkward_usage, recommended_phrases lists
- next_step: one Korean actionable suggestion

Evaluate whether the learner used recent/weak phrases naturally. If none were used, recommend 2-3 phrases that would fit the writing. Focus on natural expression, structure, and fluency. Be concise.
"""
    return generate_json(prompt, {"strengths", "revisions", "scores", "phrase_usage", "next_step"}, expect_list=False)


def format_feedback(feedback):
    lines = ["📋 *글쓰기 피드백*", "", "✅ *잘 쓴 부분:*"]
    for strength in feedback["strengths"]:
        lines.append(f"• {strength}")
    lines.extend(["", "✏️ *수정 제안:*"])
    for revision in feedback["revisions"][:4]:
        lines.append(f"• \"{revision['original']}\"")
        lines.append(f"  → \"{revision['improved']}\"")
        lines.append(f"  {revision['reason_ko']}")
    scores = feedback["scores"]
    phrase_usage = feedback.get("phrase_usage", {})
    lines.extend([
        "",
        "📊 *총평:*",
        f"문법: {'⭐' * int(scores.get('grammar', 0))}",
        f"어휘 다양성: {'⭐' * int(scores.get('vocabulary', 0))}",
        f"논리 구조: {'⭐' * int(scores.get('structure', 0))}",
        "",
        "🔗 *이번 주 표현 활용:*",
    ])
    used_well = phrase_usage.get("used_well") or []
    awkward_usage = phrase_usage.get("awkward_usage") or []
    recommended = phrase_usage.get("recommended_phrases") or []
    if used_well:
        lines.append("✅ 잘 쓴 표현: " + " / ".join(used_well))
    if awkward_usage:
        lines.append("⚠️ 어색한 표현: " + " / ".join(awkward_usage))
    if recommended:
        lines.append("💡 다음에 써볼 표현: " + " / ".join(recommended))
    if not used_well and not awkward_usage and not recommended:
        lines.append("최근 표현 카드와 직접 연결된 표현이 거의 없었습니다.")
    lines.extend([
        "",
        f"💪 한 단계 더: {feedback['next_step']}",
    ])
    return "\n".join(lines)


def send_feedback(submission: str):
    check_budget_exit("en")
    phrase_context = recent_phrase_context()
    feedback = generate_feedback(submission, phrase_context=phrase_context)
    send_message(format_feedback(feedback))
    submitted_at = datetime.now().isoformat(timespec="seconds")
    sessions = read_json(WRITING_SESSIONS_FILE, [])
    current_session = sessions[-1] if sessions else {}
    pending = get_state().get("writing_pending", {})
    session_date = current_session.get("date") or pending.get("date") or date.today().isoformat()
    topic_ko = current_session.get("topic_ko") or pending.get("topic_ko")

    submissions = read_json(WRITING_SUBMISSIONS_FILE, [])
    submissions.append({
        "session_date": session_date,
        "submitted_at": submitted_at,
        "topic_ko": topic_ko,
        "difficulty": current_session.get("difficulty"),
        "submission_text": submission,
        "feedback": feedback,
        "scores": feedback.get("scores", {}),
        "phrase_context": phrase_context,
        "phrase_usage": feedback.get("phrase_usage", {}),
    })
    write_json(WRITING_SUBMISSIONS_FILE, submissions[-250:])

    if sessions:
        sessions[-1]["submitted"] = True
        sessions[-1]["submitted_at"] = submitted_at
        sessions[-1]["submission_count"] = sessions[-1].get("submission_count", 0) + 1
        sessions[-1]["latest_scores"] = feedback.get("scores", {})
        sessions[-1]["latest_phrase_usage"] = feedback.get("phrase_usage", {})
        sessions[-1]["feedback_sent"] = True
        write_json(WRITING_SESSIONS_FILE, sessions)
    else:
        sessions.append({
            "date": session_date,
            "topic_ko": topic_ko,
            "difficulty": None,
            "target_connectives": [],
            "vocabulary_boost": [],
            "submitted": True,
            "submitted_at": submitted_at,
            "submission_count": 1,
            "latest_scores": feedback.get("scores", {}),
            "latest_phrase_usage": feedback.get("phrase_usage", {}),
            "feedback_sent": True,
            "ad_hoc_feedback": True,
        })
        write_json(WRITING_SESSIONS_FILE, sessions[-52:])
    clear_writing_pending()
    print("✅ 영어 글쓰기 피드백 발송 완료")


if __name__ == "__main__":
    send_writing_prompt(force="--force" in sys.argv)
