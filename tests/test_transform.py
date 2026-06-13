"""
변환 로직 회귀테스트 (예시 양식 기준).
실행:  python tests/test_transform.py
"""

import os
import sys
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from transform import (  # noqa: E402
    Config,
    build_message,
    format_header,
    format_timed,
    parse_description,
)

CFG = Config(
    lawyers={
        "이돈호": "돈변", "김태환": "김변", "천기섭": "천변", "박정윤": "정윤변",
        "김정아": "아변", "김수인": "수변", "채원협": "채변", "이종원": "종변",
        "정희소": "정변", "김윤수": "윤변", "임현진": "임변", "신이나": "신변",
        "박건우": "건변", "이하영": "하변", "한충호": "충변", "정진실": "진변",
        "박준호": "박변",
    },
    locations={},
)


def _fmt(event):
    return format_timed(event, parse_description(event.get("description", "")), CFG)


# --------------------------------------------------------------------------- #
def test_court_attendance_no_verb():
    ev = {
        "summary": "조장연 [변론기일]",
        "location": "김포시법원 법정",
        "start": {"dateTime": "2026-06-11T10:00:00+09:00"},
        "description": (
            "사건번호: 2025가소5592\n의뢰인: 조장연(조장연)\n장소: 김포시법원 법정\n"
            "출석변호사: ▲김정아 (담당: 김정아,김성호)\n내용: 변론기일(법정 10:00)"
        ),
    }
    assert _fmt(ev) == ("10:00 [조장연] 변론기일 > 아변님", ["김포시법원 법정"])


def test_attendee_without_triangle():
    # 출석변호사가 ▲ 없이 이름만 있어도 출석자로 인식
    ev = {
        "summary": "장주원 [공판기일]",
        "location": "서울고등법원 서관 제502호 법정",
        "start": {"dateTime": "2026-06-11T10:30:00+09:00"},
        "description": (
            "사건번호: 2026노894\n의뢰인: 장주원(이진희)\n장소: 서울고등법원 서관 제502호 법정\n"
            "출석변호사: 박준호\n내용: 공판기일(서관 제502호 법정 10:30)"
        ),
    }
    assert _fmt(ev) == ("10:30 [장주원] 공판기일 > 박변님", ["서울고등법원 서관 제502호 법정"])


def test_police_with_phone():
    # 조사기일: 장소 없음(데이터 누락) + 의뢰인(연락처) 아랫줄
    ev = {
        "summary": "박설 [조사기일]",
        "start": {"dateTime": "2026-06-11T14:00:00+09:00"},
        "description": (
            "사건번호: 2026-4410\n의뢰인: 박설(박설)\n의뢰인 연락처: 010-7904-7204\n"
            "출석변호사: ▲김수인 (담당: 천기섭,김태환)\n내용: 조사기일"
        ),
    }
    assert _fmt(ev) == ("14:00 [박설] 조사기일 > 수변님", ["박설(010-7904-7204)"])


def test_investigation_types_unified():
    # 고소인조사 / 피고소인 조사 등 -> '조사기일'로 통일
    for content, summary in [("고소인조사", "윤민아 [고소인조사]"), ("피고소인 조사", "정우 [피고소인 조사]")]:
        ev = {
            "summary": summary,
            "start": {"dateTime": "2026-06-11T10:00:00+09:00"},
            "description": f"사건번호: 9\n의뢰인: 윤민아\n출석변호사: ▲김태환\n내용: {content}",
        }
        line, _ = _fmt(ev)
        assert line == "10:00 [윤민아] 조사기일 > 김변님", line


def test_missing_attendee_court():
    ev = {
        "summary": "김봉주 [공판기일]",
        "start": {"dateTime": "2026-06-11T11:00:00+09:00"},
        "description": "사건번호: 2026-1\n의뢰인: 김봉주\n출석변호사: \n내용: 공판기일",
    }
    assert _fmt(ev) == ("11:00 [김봉주] 공판기일 > 미출석", [])


def test_missing_attendee_police():
    ev = {
        "summary": "김민지 [조사기일]",
        "start": {"dateTime": "2026-06-11T14:00:00+09:00"},
        "description": "사건번호: 2026-2\n의뢰인: 김민지\n출석변호사: \n내용: 조사기일",
    }
    assert _fmt(ev) == ("14:00 [김민지] 조사기일 > 미입회", [])


def test_multiple_attendees():
    ev = {
        "summary": "신혜원 [변론기일]",
        "location": "서울중앙지방법원",
        "start": {"dateTime": "2026-06-11T14:00:00+09:00"},
        "description": (
            "사건번호: 2026-3\n의뢰인: 신혜원\n장소: 서울중앙지방법원\n"
            "출석변호사: ▲김태환, ▲신이나\n내용: 변론기일"
        ),
    }
    assert _fmt(ev) == ("14:00 [신혜원] 변론기일 > 김변님, 신변님", ["서울중앙지방법원"])


def test_status_token_is_absent():
    # 출석변호사 칸에 '공판청취' 같은 상태값 -> 미출석
    ev = {
        "summary": "김봉주 [공판기일]",
        "start": {"dateTime": "2026-06-11T11:00:00+09:00"},
        "description": "사건번호: 1\n의뢰인: 김봉주\n출석변호사: 공판청취\n내용: 공판기일",
    }
    assert _fmt(ev) == ("11:00 [김봉주] 공판기일 > 미출석", [])


def test_literal_misiphoe_token():
    # 출석변호사 칸에 '미입회'가 직접 기재 -> '미입회님'이 아니라 '미입회'
    ev = {
        "summary": "김민지 [조사기일]",
        "start": {"dateTime": "2026-06-11T14:00:00+09:00"},
        "description": "사건번호: 2\n의뢰인: 김민지\n출석변호사: 미입회\n내용: 조사기일",
    }
    assert _fmt(ev) == ("14:00 [김민지] 조사기일 > 미입회", [])


def test_company_client_keeps_representative():
    # 실데이터: 의뢰인 필드가 '표시명(표시명)' 형태로 중첩되어 들어옴
    ev = {
        "summary": "더 주 주식회사 [조사기일]",
        "start": {"dateTime": "2026-06-11T14:00:00+09:00"},
        "description": (
            "사건번호: 3\n의뢰인: 더 주 주식회사(김주식)(더 주 주식회사(김주식))\n"
            "의뢰인 연락처: 010-7242-5517\n출석변호사: ▲채원협\n내용: 피고소인 조사"
        ),
    }
    assert _fmt(ev) == (
        "14:00 [더 주 주식회사(김주식)] 조사기일 > 채변님",
        ["더 주 주식회사(김주식)(010-7242-5517)"],
    )


def test_individual_client_strips_mirror():
    ev = {
        "summary": "장주원 [공판기일]",
        "location": "서울고등법원",
        "start": {"dateTime": "2026-06-11T10:30:00+09:00"},
        "description": "사건번호: 4\n의뢰인: 장주원(이진희)\n장소: 서울고등법원\n"
                       "출석변호사: 박준호\n내용: 공판기일",
    }
    assert _fmt(ev) == ("10:30 [장주원] 공판기일 > 박변님", ["서울고등법원"])


# --- 그 외 일정(담당변호사로 출석표기, 제목 그대로) ---------------------------- #
def test_non_gijil_with_brackets_title():
    ev = {
        "summary": "[엄태웅] 스마트접견",
        "start": {"dateTime": "2026-06-11T14:00:00+09:00"},
        "description": "담당(변호사): 이돈호\n담당(직원): #송무1팀",
    }
    assert _fmt(ev) == ("14:00 [엄태웅] 스마트접견 > 돈변님", [])


def test_non_gijil_meeting():
    ev = {
        "summary": "황진주 미팅",
        "start": {"dateTime": "2026-06-11T15:00:00+09:00"},
        "description": "담당(변호사): 이돈호,신이나",
    }
    assert _fmt(ev) == ("15:00 황진주 미팅 > 돈변님, 신변님", [])


def test_non_gijil_no_lawyer():
    ev = {
        "summary": "손진영 오후반반차",
        "start": {"dateTime": "2026-06-11T16:30:00+09:00"},
        "description": "담당(직원): 손진영,#운영팀,#휴가",
    }
    assert _fmt(ev) == ("16:30 손진영 오후반반차", [])


# --- 전체 메시지 / 헤더 ------------------------------------------------------ #
def test_header():
    assert format_header(date(2026, 6, 11)) == "#260611 목요일"


def test_full_message():
    a = {
        "summary": "조장연 [변론기일]", "location": "김포시법원 법정",
        "start": {"dateTime": "2026-06-11T10:00:00+09:00"},
        "description": "사건번호: 1\n의뢰인: 조장연(조장연)\n장소: 김포시법원 법정\n"
                       "출석변호사: ▲김정아\n내용: 변론기일(법정 10:00)",
    }
    b = {
        "summary": "[엄태웅] 스마트접견",
        "start": {"dateTime": "2026-06-11T14:00:00+09:00"},
        "description": "담당(변호사): 이돈호",
    }
    msg = build_message([b, a], date(2026, 6, 11), CFG)
    expected = (
        "#260611 목요일\n\n"
        "10:00 [조장연] 변론기일 > 아변님\n"
        "        김포시법원 법정\n\n"
        "14:00 [엄태웅] 스마트접견 > 돈변님"
    )
    assert msg == expected


def test_allday_goes_to_top():
    leave = {  # 시간 미특정(종일) -> 맨 위
        "summary": "김진우 연차",
        "start": {"date": "2026-06-11"},
        "description": "담당(직원): 김진우,#휴가",
    }
    timed = {
        "summary": "조장연 [변론기일]", "location": "김포시법원 법정",
        "start": {"dateTime": "2026-06-11T10:00:00+09:00"},
        "description": "사건번호: 1\n의뢰인: 조장연(조장연)\n장소: 김포시법원 법정\n"
                       "출석변호사: ▲김정아\n내용: 변론기일",
    }
    msg = build_message([timed, leave], date(2026, 6, 11), CFG)
    expected = (
        "#260611 목요일\n\n"
        "김진우 연차\n\n"
        "10:00 [조장연] 변론기일 > 아변님\n"
        "        김포시법원 법정"
    )
    assert msg == expected


def test_empty_day():
    assert build_message([], date(2026, 6, 13), CFG) == "#260613 토요일\n\n일정 없음"


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
