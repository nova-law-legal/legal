"""
엔트리포인트: 오늘 일정 읽기 → 회사 양식 변환 → Discord 전송.

사용법:
    python main.py            # 실제 전송
    python main.py --dry-run  # 전송하지 않고 콘솔에만 출력(검증용)

필요 환경변수:
    GOOGLE_SERVICE_ACCOUNT_JSON   서비스계정 키(JSON 문자열)
    GOOGLE_CALENDAR_ID            대상 캘린더 ID(들). 여러 개면 쉼표/줄바꿈/공백으로 구분
    DISCORD_WEBHOOK_URL           발송 채널 웹훅 URL
  (다른 구글 계정의 캘린더는 _2,_3 접미사로 키+ID를 추가:
    GOOGLE_SERVICE_ACCOUNT_JSON_2 + GOOGLE_CALENDAR_ID_2 ...)
"""

import argparse
import os
import sys
from datetime import datetime, timedelta

# 로컬 실행 시 .env 자동 로드(있을 때만). GitHub Actions 등에서는 .env 없이 환경변수로 동작.
try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass

from calendar_client import KST, fetch_events, sources_from_env
from discord_sender import send
from transform import build_message, event_in_team, load_config

CONFIG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config")

# 송무 팀 → 팀별 전용 웹훅 환경변수(없으면 기본 DISCORD_WEBHOOK_URL 로 폴백)
SONGMU_TEAMS = [
    ("송무1팀", "DISCORD_WEBHOOK_URL_SONGMU1"),
    ("송무2팀", "DISCORD_WEBHOOK_URL_SONGMU2"),
    ("송무3팀", "DISCORD_WEBHOOK_URL_SONGMU3"),
]


def main():
    parser = argparse.ArgumentParser(description="법무법인 노바 기일 일정 알림 봇")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="전송하지 않고 변환 결과만 콘솔에 출력",
    )
    parser.add_argument(
        "--date",
        metavar="YYYY-MM-DD",
        help="특정 날짜(KST)로 테스트. 미지정 시 오늘. 예: --date 2026-06-15",
    )
    parser.add_argument(
        "--next-day",
        action="store_true",
        help="익일(내일) 일정으로 발송",
    )
    parser.add_argument(
        "--teams",
        action="store_true",
        help="송무1/2/3팀별로 분류해 팀마다 따로 발송",
    )
    args = parser.parse_args()

    # Windows 한글 콘솔(cp949)에서 이모지/특수문자 출력 시 깨지지 않도록 UTF-8 고정.
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass

    cfg = load_config(CONFIG_DIR)
    sources = sources_from_env()
    if not sources:
        sys.exit("서비스계정 키/캘린더ID 환경변수가 없습니다. (GOOGLE_SERVICE_ACCOUNT_* / GOOGLE_CALENDAR_ID*)")

    # 대상 날짜: --date 우선, 그다음 --next-day(내일), 기본 오늘
    target_day = None
    if args.date:
        target_day = datetime.strptime(args.date, "%Y-%m-%d").date()
    elif args.next_day:
        target_day = datetime.now(KST).date() + timedelta(days=1)

    events, day = fetch_events(sources, day=target_day)
    day_label = "내일 일정" if args.next_day else None

    default_webhook = os.environ.get("DISCORD_WEBHOOK_URL")

    # 송무 팀별 분류 발송 모드
    if args.teams:
        for team, env_key in SONGMU_TEAMS:
            filtered = [ev for ev in events if event_in_team(ev, team)]
            lead = f"[{team}]" + (f" {day_label}" if day_label else "")
            # 팀 메시지 끝에 빈 줄 하나(구분용). Discord가 일반 공백은 잘라내므로
            # 보이지 않는 zero-width space 로 빈 줄을 강제한다.
            message = build_message(filtered, day, cfg, lead=lead) + "\n​"
            if args.dry_run:
                print(message)
                continue
            webhook = os.environ.get(env_key) or default_webhook
            if not webhook:
                sys.exit(f"{team} 웹훅 미설정 (DISCORD_WEBHOOK_URL{'/' + env_key})")
            send(webhook, message)
            print(f"[{team}] 전송 완료 ({day}, {len(filtered)}건)")
        return

    # 단일 메시지(아침=오늘 전체, --next-day=내일 전체)
    message = build_message(events, day, cfg, lead=day_label)
    if args.dry_run:
        print(message)
        return

    if not default_webhook:
        print("DISCORD_WEBHOOK_URL 미설정 — 전송 건너뜀. 결과:\n", file=sys.stderr)
        print(message)
        sys.exit(1)

    send(default_webhook, message)
    print(f"전송 완료 ({day}, {len(events)}건)")


if __name__ == "__main__":
    main()
