"""
엔트리포인트: 오늘 일정 읽기 → 회사 양식 변환 → Discord 전송.

사용법:
    python main.py            # 실제 전송
    python main.py --dry-run  # 전송하지 않고 콘솔에만 출력(검증용)

필요 환경변수:
    GOOGLE_SERVICE_ACCOUNT_JSON  서비스계정 키(JSON 문자열)
    GOOGLE_CALENDAR_ID           대상 캘린더 ID
    DISCORD_WEBHOOK_URL          발송 채널 웹훅 URL
"""

import argparse
import os
import sys

from calendar_client import fetch_today_events
from discord_sender import send
from transform import build_message, load_config

CONFIG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config")


def main():
    parser = argparse.ArgumentParser(description="법무법인 노바 기일 일정 알림 봇")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="전송하지 않고 변환 결과만 콘솔에 출력",
    )
    args = parser.parse_args()

    cfg = load_config(CONFIG_DIR)
    calendar_id = os.environ["GOOGLE_CALENDAR_ID"]

    events, day = fetch_today_events(calendar_id)
    message = build_message(events, day, cfg)

    if args.dry_run:
        print(message)
        return

    webhook = os.environ.get("DISCORD_WEBHOOK_URL")
    if not webhook:
        print("DISCORD_WEBHOOK_URL 미설정 — 전송 건너뜀. 결과:\n", file=sys.stderr)
        print(message)
        sys.exit(1)

    send(webhook, message)
    print(f"전송 완료 ({day}, {len(events)}건)")


if __name__ == "__main__":
    main()
