"""
엔트리포인트: 오늘 일정 읽기 → 회사 양식 변환 → Discord 전송.

사용법:
    python main.py            # 실제 전송
    python main.py --dry-run  # 전송하지 않고 콘솔에만 출력(검증용)

필요 환경변수:
    GOOGLE_SERVICE_ACCOUNT_JSON   서비스계정 키(JSON 문자열)
    GOOGLE_CALENDAR_ID            대상 캘린더 ID(들). 여러 개면 쉼표/줄바꿈/공백으로 구분
    DISCORD_WEBHOOK_URL           기본 채널 웹훅 URL(오전 전체 알림, 오후 이돈호·상담 알림)
    DISCORD_WEBHOOK_URL_SONGMU1   송무1팀 전용 채널 웹훅(오전 팀 알림 + 오후 팀 알림)
    DISCORD_WEBHOOK_URL_SONGMU2   송무2팀 전용 채널 웹훅(오전 팀 알림 + 오후 팀 알림)
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
from transform import (
    SECTIONS,
    build_lawyer_message,
    build_message,
    build_office_meeting_message,
    build_section_message,
    build_team_message,
    format_header_weekend,
    format_header_weekend_lead,
    lawyer_events,
    load_config,
    office_meeting_events,
    team_event_count,
    team_events,
)

CONFIG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config")

# 저녁 익일 알림 — 발송 대상과 순서.
#   env_key 가 None 이면 기본 채널(DISCORD_WEBHOOK_URL)로,
#   지정돼 있으면 그 전용 웹훅으로 발송(미설정 시 기본 채널로 폴백).
#   ("변호사", 이름)  = 개인 알림. 본인 담당·출석 일정과 담당직원 휴무만 담는다.
#   ("상담", 라벨)    = 사무실 상담 알림. 1006호·404호·인천 사무소의 [회의] 방문상담만.
#   ("팀",   팀이름)  = 팀 알림. 팀 안에서 다시 변호사별 섹션으로 나뉜다.
EVENING_TARGETS = [
    ("변호사", "이돈호", None),
    ("상담", "상담", None),
    ("팀", "송무1팀", "DISCORD_WEBHOOK_URL_SONGMU1"),
    ("팀", "송무2팀", "DISCORD_WEBHOOK_URL_SONGMU2"),
]

# 오전 팀별 알림 — 팀 일정 전체를 [기한]/[일정]/[휴무] 한 통에 모아 전용 채널로.
# (기본 채널의 오전 전체 알림 3분할과 별개. 전용 웹훅이 미설정이면 건너뛴다 —
#  기본 채널로 폴백하면 전체 알림과 중복되기 때문)
MORNING_TEAM_TARGETS = [
    ("송무1팀", "DISCORD_WEBHOOK_URL_SONGMU1"),
    ("송무2팀", "DISCORD_WEBHOOK_URL_SONGMU2"),
]

# 오전 전체 알림에서 '@everyone' 을 붙일 섹션 (알림 3연타를 피해 한 번만 멘션)
MORNING_MENTION_SECTION = "일정"

# 금요일 저녁(익일=토요일) 묶음 대상 — 토·일·월 3일치를 한 메시지로 보낸다.
WEEKEND_BUNDLE_TARGETS = {"이돈호", "상담", "송무1팀", "송무2팀"}


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
        help="송무1/2팀·상담지원팀별로 분류해 팀마다 따로 발송",
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
        # 금요일 저녁(익일=토요일) → 송무1/2팀은 토·일·월 3일치를 한 메시지로 묶는다.
        # 묶음 대상이면 토·일·월 각 날짜의 일정을 미리 한 번씩만 조회해 둔다.
        bundle = day.weekday() == 5  # 대상일이 토요일 == 금요일 저녁 실행
        bundle_days, bundle_events = [], {}
        if bundle:
            bundle_days = [day + timedelta(days=i) for i in range(3)]  # 토·일·월
            bundle_events = {d: fetch_events(sources, day=d)[0] for d in bundle_days}

        for kind, name, env_key in EVENING_TARGETS:
            if bundle and name in WEEKEND_BUNDLE_TARGETS:
                # 토/일/월 각 블록을 일자별 머리말과 함께 이어붙인다.
                # 팀 알림은 3일치라 길어지므로 일정 없는 변호사 섹션은 생략(skip_empty).
                blocks, total = [], 0
                for d in bundle_days:
                    if kind == "변호사":
                        total += len(lawyer_events(bundle_events[d], cfg, name))
                        blocks.append(build_lawyer_message(
                            bundle_events[d], d, cfg, name,
                            head=format_header_weekend_lead(f"{name} 변호사", d),
                            include_deadlines=False,
                        ))
                    elif kind == "상담":
                        total += len(office_meeting_events(bundle_events[d], cfg))
                        blocks.append(build_office_meeting_message(
                            bundle_events[d], d, cfg,
                            head=format_header_weekend_lead("[상담]", d),
                        ))
                    else:
                        total += team_event_count(bundle_events[d], cfg, name)
                        blocks.append(build_team_message(
                            bundle_events[d], d, cfg, name,
                            head=format_header_weekend(name, d), skip_empty=True,
                        ))
                message = "@everyone\n" + "\n\n".join(blocks) + "\n​"
                count_desc = f"토·일·월 {total}건"
            elif kind == "변호사":  # 개인 알림(팀 알림과 별개로 본인 일정만, [기한] 제외)
                message = build_lawyer_message(
                    events, day, cfg, name, day_label=day_label, mention=True,
                    include_deadlines=False,
                ) + "\n​"
                count_desc = f"{len(lawyer_events(events, cfg, name))}건"
            elif kind == "상담":  # 사무실 상담 알림(1006호·404호·인천)
                message = build_office_meeting_message(
                    events, day, cfg, day_label=day_label, mention=True,
                ) + "\n​"
                count_desc = f"{len(office_meeting_events(events, cfg))}건"
            else:
                lead = f"[{name}]" + (f" {day_label}" if day_label else "")
                message = build_team_message(
                    events, day, cfg, name, lead=lead, day_label=day_label, mention=True,
                ) + "\n​"
                count_desc = f"{team_event_count(events, cfg, name)}건"
            # 메시지 끝에 빈 줄 하나(구분용). Discord가 일반 공백은 잘라내므로
            # 보이지 않는 zero-width space 로 빈 줄을 강제한다.
            if args.dry_run:
                print(message)
                continue
            webhook = (os.environ.get(env_key) if env_key else None) or default_webhook
            if not webhook:
                sys.exit(f"{name} 웹훅 미설정 (DISCORD_WEBHOOK_URL{('/' + env_key) if env_key else ''})")
            send(webhook, message)
            print(f"[{name}] 전송 완료 ({day}, {count_desc})")
        return

    # 오전 전체 알림 — 팀 구분 없이, [기한]/[일정]/[휴무] 를 각각 별도 메시지로 3회 발송.
    # (섹션이 비어도 '없음'으로 발송해 그날 확인이 끝났음을 알 수 있게 한다)
    messages = [
        build_section_message(
            events, day, cfg, section, lead=day_label,
            mention=(section == MORNING_MENTION_SECTION),
        )
        for section in SECTIONS
    ]

    # 오전 팀별 알림 — 팀 전용 채널로, 그 팀 일정 전체를 한 통에 모아 발송.
    team_messages = [
        (team, env_key,
         build_message(team_events(events, cfg, team), day, cfg,
                       lead=f"[{team}] 오늘 일정", mention=True) + "\n​",
         team_event_count(events, cfg, team))
        for team, env_key in MORNING_TEAM_TARGETS
    ]

    if args.dry_run:
        print("\n\n".join(messages))
        for _, _, message, _ in team_messages:
            print("\n" + message)
        return

    if not default_webhook:
        print("DISCORD_WEBHOOK_URL 미설정 — 전송 건너뜀. 결과:\n", file=sys.stderr)
        print("\n\n".join(messages))
        sys.exit(1)

    for section, message in zip(SECTIONS, messages):
        send(default_webhook, message)
        print(f"[{section}] 전송 완료 ({day})")

    for team, env_key, message, count in team_messages:
        webhook = os.environ.get(env_key)
        if not webhook:  # 기본 채널로 폴백하면 전체 알림과 중복 → 건너뜀
            print(f"[{team}] 전용 웹훅({env_key}) 미설정 — 오전 팀 알림 건너뜀")
            continue
        send(webhook, message)
        print(f"[{team}] 오전 팀 알림 전송 완료 ({day}, {count}건)")

    print(f"전송 완료 ({day}, {len(events)}건)")


if __name__ == "__main__":
    main()
