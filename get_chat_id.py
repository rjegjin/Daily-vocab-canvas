"""
새 봇 토큰으로 chat ID 확인하는 헬퍼.
사용법:
  1. 텔레그램에서 해당 봇 대화방 열고 아무 메시지나 (예: /start) 전송
  2. python get_chat_id.py <BOT_TOKEN>
"""
import sys

import requests


def main():
    if len(sys.argv) != 2:
        print("usage: python get_chat_id.py <BOT_TOKEN>")
        sys.exit(1)

    token = sys.argv[1]
    resp = requests.get(f"https://api.telegram.org/bot{token}/getUpdates", timeout=10)
    resp.raise_for_status()
    updates = resp.json().get("result", [])

    if not updates:
        print("메시지가 없습니다. 봇과 대화방에서 먼저 메시지를 보낸 후 다시 실행하세요.")
        return

    seen = {}
    for u in updates:
        msg = u.get("message") or u.get("channel_post")
        if not msg:
            continue
        chat = msg["chat"]
        seen[chat["id"]] = chat.get("title") or chat.get("username") or chat.get("first_name")

    for chat_id, label in seen.items():
        print(f"chat_id={chat_id}  ({label})")


if __name__ == "__main__":
    main()
