"""
변환 로직 회귀테스트.
실행:  pytest tests/         또는        python tests/test_transform.py
"""

import os
import sys
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from transform import Config, build_message, format_timed, parse_description  # noqa: E402

CFG = Config(
    lawyers={
        "이돈호": "돈변", "김태환": "김변", "천기섭": "천변", "박정윤": "정윤변",
        "김정아": "아변", "김수인": "수변", "채원협": "채변", "이종원": "종변",
    },
    locations={},
)

# 별첨 양식의 기준 샘플
SAMPLE_POLICE = {
    "summary": "고명수 [고소인조사]",
    "location": "서울강남경찰서",
    "start": {"dateTime": "2026-06-15T09:30:00+09:00"},
    "description": (
        "사건번호: 2026-011859\n"
        "사건명: 공갈 및 전자금융거래법위반\n"
        "의뢰인: 고명수(고명수)\n"
        "의뢰인 연락처: 010-9129-8930\n"
        "상대방: 이건웅외4\n"
        "장소: 서울강남경찰서\n"
        "담당변호사: 김태환,김수인,박건우\n"
        "출석변호사: ▲김태환 (담당: 김태환,김수인,박건우)\n"
        "담당직원: #송무2팀\n"
        "내용: 고소인조사"
    ),
}


def _line(event):
    return format_timed(event, parse_description(event.get("description", "")), CFG)


def test_police_attendance():
    assert _line(SAMPLE_POLICE) == "[고명수(강남서)] 09:30 고소인조사 > 김변님 입회"


def test_no_case_event():
    ev = {
        "summary": "대면상담",
        "location": "학익동",
        "start": {"dateTime": "2026-06-15T20:00:00+09:00"},
        "description": "",
    }
    assert _line(ev) == "20:00 대면상담(학익동)"


def test_court_attendance():
    ev = {
        "summary": "홍길동 [변론기일]",
        "location": "서울동부지방법원",
        "start": {"dateTime": "2026-06-15T14:00:00+09:00"},
        "description": (
            "사건번호: 2026-000001\n장소: 서울동부지방법원\n"
            "출석변호사: ▲이돈호 (담당: 이돈호,김태환)\n내용: 변론기일"
        ),
    }
    assert _line(ev) == "[홍길동(서울동부지법)] 14:00 변론기일 > 돈변님 출석"


def test_missing_attendee_police():
    ev = {
        "summary": "김의뢰 [피의자조사]",
        "location": "경주경찰서",
        "start": {"dateTime": "2026-06-15T10:00:00+09:00"},
        "description": (
            "사건번호: 2026-000002\n장소: 경주경찰서\n"
            "출석변호사:  (담당: 김태환)\n내용: 피의자조사"
        ),
    }
    assert _line(ev) == "[김의뢰(경주서)] 10:00 피의자조사 > 미입회"


def test_no_attendee_line():
    ev = {
        "summary": "박의뢰 [현장검증]",
        "location": "수원지방법원 안산지원",
        "start": {"dateTime": "2026-06-15T11:00:00+09:00"},
        "description": "사건번호: 2026-000003\n장소: 수원지방법원 안산지원\n내용: 현장검증",
    }
    # 출석변호사 줄 자체가 없음 -> '> ...' 생략, 지원명만 약칭
    assert _line(ev) == "[박의뢰(안산지원)] 11:00 현장검증"


def test_unknown_lawyer_fullname():
    ev = {
        "summary": "최의뢰 [고소인조사]",
        "location": "서울강남경찰서",
        "start": {"dateTime": "2026-06-15T09:00:00+09:00"},
        "description": (
            "사건번호: 2026-000004\n장소: 서울강남경찰서\n"
            "출석변호사: ▲박건우 (담당: 박건우)\n내용: 고소인조사"
        ),
    }
    assert _line(ev) == "[최의뢰(강남서)] 09:00 고소인조사 > 박건우님 입회"


def test_full_message_with_deadline():
    deadline = {
        "summary": "홍길동 [항소이유서 제출기한]",
        "location": "서울중앙지방법원",
        "start": {"date": "2026-06-15"},
        "description": "사건번호: 2026-000010\n장소: 서울중앙지방법원\n내용: 항소이유서 제출기한",
    }
    msg = build_message([SAMPLE_POLICE, deadline], date(2026, 6, 15), CFG)
    expected = (
        "📅 6/15(월) 오늘 일정\n\n"
        "[마감]\n"
        "[홍길동(서울중앙지법)] 항소이유서 제출기한\n\n"
        "[고명수(강남서)] 09:30 고소인조사 > 김변님 입회"
    )
    assert msg == expected


def test_empty_day():
    msg = build_message([], date(2026, 6, 13), CFG)
    assert msg == "📅 6/13(토) 오늘 일정\n\n오늘 일정 없음"


if __name__ == "__main__":
    funcs = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    failed = 0
    for fn in funcs:
        try:
            fn()
            print(f"PASS  {fn.__name__}")
        except AssertionError as e:
            failed += 1
            print(f"FAIL  {fn.__name__}: {e}")
    print(f"\n{len(funcs) - failed}/{len(funcs)} passed")
    sys.exit(1 if failed else 0)
