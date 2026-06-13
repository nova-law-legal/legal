"""Discord 웹훅 전송. 2000자 제한 시 줄 단위로 분할."""

import requests

DISCORD_LIMIT = 2000


def split_message(content: str, limit: int = DISCORD_LIMIT):
    if len(content) <= limit:
        return [content]
    chunks, cur = [], ""
    for line in content.split("\n"):
        candidate = f"{cur}\n{line}" if cur else line
        if len(candidate) > limit:
            if cur:
                chunks.append(cur)
            cur = line
        else:
            cur = candidate
    if cur:
        chunks.append(cur)
    return chunks


def send(webhook_url: str, content: str):
    for chunk in split_message(content):
        resp = requests.post(webhook_url, json={"content": chunk}, timeout=30)
        resp.raise_for_status()
