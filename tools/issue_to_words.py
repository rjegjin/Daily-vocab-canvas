import os
import sys
import re

# 프로젝트 루트 경로 설정
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LEARNED_WORDS_FILE = os.path.join(BASE_DIR, 'learned_words.txt')

def main():
    issue_title = os.getenv('ISSUE_TITLE', '')
    issue_body = os.getenv('ISSUE_BODY', '')

    print(f"🔍 이슈 제목: {issue_title}")
    
    # 1. 이슈 본문에서 단어 추출 (한 줄에 하나씩 또는 쉼표 구분)
    # 마크다운 코드 블록이나 리스트 형태 지원
    raw_words = []
    if issue_body:
        # 본문에서 '### Words' 또는 '단어 목록' 섹션 아래 내용을 찾거나 전체 본문 사용
        lines = issue_body.split('\n')
        for line in lines:
            line = line.strip()
            if not line or line.startswith('#'): continue
            
            # -, *, 1. 등 리스트 기호 제거
            clean_line = re.sub(r'^[\-\*\d\.]+\s*', '', line)
            # 쉼표로 구분된 경우 분리
            parts = [p.strip() for p in clean_line.split(',') if p.strip()]
            raw_words.extend(parts)

    if not raw_words:
        print("⚠️ 이슈 본문에서 추가할 단어를 찾지 못했습니다.")
        return

    # 2. 기존 단어 로드 (중복 체크용)
    existing_words = set()
    if os.path.exists(LEARNED_WORDS_FILE):
        with open(LEARNED_WORDS_FILE, 'r', encoding='utf-8') as f:
            existing_words = {line.strip() for line in f if line.strip()}

    # 3. 새로운 단어 필터링 및 추가
    added_count = 0
    with open(LEARNED_WORDS_FILE, 'a', encoding='utf-8') as f:
        for word in raw_words:
            if word not in existing_words:
                f.write(word + '\n')
                existing_words.add(word)
                print(f"✅ 추가됨: {word}")
                added_count += 1
            else:
                print(f"ℹ️ 이미 존재함 (건너뜀): {word}")

    print(f"🎉 총 {added_count}개의 단어가 learned_words.txt에 추가되었습니다.")

if __name__ == "__main__":
    main()
