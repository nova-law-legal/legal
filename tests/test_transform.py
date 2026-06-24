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
    event_in_team,
    format_deadline,
    format_header,
    format_header_weekend,
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
    teams={
        "송무1팀": ["천기섭", "박정윤", "박준호", "김정아"],
        "송무2팀": ["김태환", "김수인"],
        "송무3팀": ["채원협", "이종원"],
    },
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


# --- 화상장치 -> 영상재판 (장소 대체) --------------------------------------- #
def test_video_trial_replaces_location():
    # '내용' 끝의 '[일방 화상장치]' 꼬리표 -> 장소 대신 '영상재판'
    ev = {
        "summary": "곽승우 [변론기일(제419호 법정 14:30) [일방 화상장치]]",
        "location": "인천지방법원 제419호 법정",
        "start": {"dateTime": "2026-06-17T14:30:00+09:00"},
        "description": (
            "사건번호: 2025가단214056\n의뢰인: 곽승우(곽승우)\n장소: 인천지방법원 제419호 법정\n"
            "출석변호사: ▲이종원\n내용: 변론기일(제419호 법정 14:30) [일방 화상장치]"
        ),
    }
    assert _fmt(ev) == ("14:30 [곽승우] 변론기일 > 종변님", ["영상재판"])


def test_video_trial_investigation_keeps_phone():
    # 화상장치라도 조사기일 의뢰인(연락처) 아랫줄은 유지, 장소만 영상재판으로 대체
    ev = {
        "summary": "박설 [조사기일 [주문 화상장치]]",
        "location": "서울중앙지방법원",
        "start": {"dateTime": "2026-06-17T14:00:00+09:00"},
        "description": (
            "사건번호: 1\n의뢰인: 박설(박설)\n의뢰인 연락처: 010-7904-7204\n장소: 서울중앙지방법원\n"
            "출석변호사: ▲김수인\n내용: 조사기일 [주문 화상장치]"
        ),
    }
    assert _fmt(ev) == ("14:00 [박설] 조사기일 > 수변님", ["영상재판", "박설(010-7904-7204)"])


def test_no_video_keyword_keeps_location():
    # 키워드 없으면 기존대로 실제 장소 표시(회귀)
    ev = {
        "summary": "조장연 [변론기일]",
        "location": "김포시법원 법정",
        "start": {"dateTime": "2026-06-17T10:00:00+09:00"},
        "description": (
            "사건번호: 1\n의뢰인: 조장연(조장연)\n장소: 김포시법원 법정\n"
            "출석변호사: ▲김정아\n내용: 변론기일(법정 10:00)"
        ),
    }
    assert _fmt(ev) == ("10:00 [조장연] 변론기일 > 아변님", ["김포시법원 법정"])


# --- 비고: 필터 없이 '비고 : 원문' 으로 맨 아랫줄에 노출 ----------------------- #
def test_bigo_shown_below_place_and_phone():
    # 비고는 장소·연락처 아래(맨 끝)에 '비고 : 원문' 으로 표시
    ev = {
        "summary": "오승곤 [조사기일]",
        "start": {"dateTime": "2026-06-19T10:30:00+09:00"},
        "description": (
            "사건번호: 2026형제16481\n의뢰인: 오승곤(오승곤)\n의뢰인 연락처: 010-3257-8715\n"
            "장소: 남양주북부경찰서 수사과 지능범죄수사팀\n출석변호사: ▲박준호\n"
            "내용: 조사기일\n비고: 서울남부지방검찰청 형사조정실 02-3219-4586"
        ),
    }
    assert _fmt(ev) == (
        "10:30 [오승곤] 조사기일 > 박변님",
        [
            "남양주북부경찰서 수사과 지능범죄수사팀",
            "오승곤(010-3257-8715)",
            "비고 : 서울남부지방검찰청 형사조정실 02-3219-4586",
        ],
    )


def test_bigo_always_shown():
    # 필터 폐지: 복대리 같은 메모도 그대로 '비고 :' 로 노출
    ev = {
        "summary": "박선영 [선고기일]",
        "location": "부산지방법원 제352호 법정",
        "start": {"dateTime": "2026-06-19T10:00:00+09:00"},
        "description": (
            "사건번호: 2025노4196\n의뢰인: 박선영\n장소: 부산지방법원 제352호 법정\n"
            "출석변호사: ▲청취대리(권)\n내용: 선고기일(제352호 법정 10:00)\n비고: 복대리"
        ),
    }
    assert _fmt(ev) == (
        "10:00 [박선영] 선고기일 > 청취대리",
        ["부산지방법원 제352호 법정", "비고 : 복대리"],
    )


def test_bigo_on_deadline():
    # 종일 제출기한([기한])의 비고 -> 장소 아래 '비고 :' 로 표시 (예: 항소X)
    ev = {
        "summary": "남기태외1 [상소제기]",
        "start": {"date": "2026-06-24"},
        "description": (
            "사건번호: 2025가단13014\n의뢰인: 남기태외1(남기태외1)\n장소: 서울서부지방법원\n"
            "내용: 상소제기(민사)\n비고: 항소X"
        ),
    }
    fields = parse_description(ev["description"])
    assert format_deadline(ev, fields, CFG) == (
        "[남기태외1] 상소제기",
        ["서울서부지방법원", "비고 : 항소X"],
    )


# --- 선고기일: 대리출석 표기를 '청취대리'로 일원화 ----------------------------- #
def test_seongo_listen_proxy_unified():
    for raw in ["▲복대리", "▲청취대리", "▲선고청취대리", "▲선고청취"]:
        ev = {
            "summary": "박선영 [선고기일]",
            "location": "부산지방법원 제352호 법정",
            "start": {"dateTime": "2026-06-19T10:00:00+09:00"},
            "description": (
                f"사건번호: 1\n의뢰인: 박선영\n장소: 부산지방법원 제352호 법정\n"
                f"출석변호사: {raw}\n내용: 선고기일(제352호 법정 10:00)"
            ),
        }
        line, _ = _fmt(ev)
        assert line == "10:00 [박선영] 선고기일 > 청취대리", f"{raw} -> {line}"


def test_listen_proxy_only_for_seongo():
    # 선고기일이 아니면 일원화하지 않음(복대리 표기 그대로 유지)
    ev = {
        "summary": "박선영 [변론기일]",
        "location": "부산지방법원 제352호 법정",
        "start": {"dateTime": "2026-06-19T10:00:00+09:00"},
        "description": (
            "사건번호: 1\n의뢰인: 박선영\n장소: 부산지방법원 제352호 법정\n"
            "출석변호사: ▲복대리\n내용: 변론기일(제352호 법정 10:00)"
        ),
    }
    line, _ = _fmt(ev)
    assert line == "10:00 [박선영] 변론기일 > 복대리님", line


# --- 그 외 일정(담당변호사로 출석표기, 제목 그대로) ---------------------------- #
def test_non_gijil_with_brackets_title():
    ev = {
        "summary": "[엄태웅] 스마트접견",
        "start": {"dateTime": "2026-06-11T14:00:00+09:00"},
        "description": "담당(변호사): 이돈호\n담당(직원): #송무1팀",
    }
    assert _fmt(ev) == ("14:00 [엄태웅] 스마트접견 > 돈변님", [])


def test_visit_shows_reservation_number():
    # 스마트/화상 접견: 설명의 접견 예약번호를 '접견번호 :' 아랫줄로 노출
    ev = {
        "summary": "[이상열] 스마트접견",
        "start": {"dateTime": "2026-06-24T11:00:00+09:00"},
        "description": (
            "사건번호: 2026고단100798\n의뢰인: 이상열\n"
            "스마트접견예약번호: 002317\n담당(변호사): 김태환\n담당(직원): #송무2팀"
        ),
    }
    assert _fmt(ev) == ("11:00 [이상열] 스마트접견 > 김변님", ["접견번호 : 002317"])


def test_visit_number_below_place_above_bigo():
    # 장소(교도소)·접견번호·비고가 모두 있으면 장소 → 접견번호 → 비고 순
    ev = {
        "summary": "[김갑동] 화상접견 (서울남부교도소)",
        "start": {"dateTime": "2026-06-24T14:00:00+09:00"},
        "description": (
            "의뢰인: 김갑동\n접견예약번호: 12345\n담당(변호사): 이돈호\n비고: 통역 필요"
        ),
    }
    assert _fmt(ev) == (
        "14:00 [김갑동] 화상접견 > 돈변님",
        ["서울남부교도소", "접견번호 : 12345", "비고 : 통역 필요"],
    )


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
    assert format_header(date(2026, 6, 11)) == "📅 260611 목요일"


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
        "📅 260611 목요일\n\n"
        "[일정]\n"
        "10:00 [조장연] 변론기일 > 아변님\n"
        "        김포시법원 법정\n\n"
        "14:00 [엄태웅] 스마트접견 > 돈변님"
    )
    assert msg == expected


def test_allday_goes_to_top():
    allday = {  # 종일(비-기일·비-휴무) -> [일정]에서 시간일정 위
        "summary": "전사 워크숍",
        "start": {"date": "2026-06-11"},
        "description": "담당(직원): 김진우",
    }
    timed = {
        "summary": "조장연 [변론기일]", "location": "김포시법원 법정",
        "start": {"dateTime": "2026-06-11T10:00:00+09:00"},
        "description": "사건번호: 1\n의뢰인: 조장연(조장연)\n장소: 김포시법원 법정\n"
                       "출석변호사: ▲김정아\n내용: 변론기일",
    }
    msg = build_message([timed, allday], date(2026, 6, 11), CFG)
    expected = (
        "📅 260611 목요일\n\n"
        "[일정]\n"
        "전사 워크숍\n\n"
        "10:00 [조장연] 변론기일 > 아변님\n"
        "        김포시법원 법정"
    )
    assert msg == expected


def test_leave_section_at_bottom():
    leave_half = {  # 시간 있는 반차 -> [휴무]
        "summary": "오바다 오후반차",
        "start": {"dateTime": "2026-06-11T13:00:00+09:00"},
        "description": "",
    }
    leave_allday = {  # 종일 연차 -> [휴무]
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
    msg = build_message([leave_half, timed, leave_allday], date(2026, 6, 11), CFG)
    expected = (
        "📅 260611 목요일\n\n"
        "[일정]\n"
        "10:00 [조장연] 변론기일 > 아변님\n"
        "        김포시법원 법정\n\n"
        "[휴무]\n"
        "오바다 오후반차\n"
        "김진우 연차"
    )
    assert msg == expected


def test_leave_only_day():
    leave = {"summary": "김진우 연차", "start": {"date": "2026-06-11"}, "description": ""}
    msg = build_message([leave], date(2026, 6, 11), CFG)
    assert msg == "📅 260611 목요일\n\n[휴무]\n김진우 연차"


def test_empty_day():
    assert build_message([], date(2026, 6, 13), CFG) == "📅 260613 토요일\n\n일정 없음"


def test_deadline_then_schedule_sections():
    deadline = {  # 종일 + 사건번호+내용 -> [기한]
        "summary": "홍길동 [제출기한]",
        "start": {"date": "2026-06-11"},
        "description": "사건번호: 1\n의뢰인: 홍길동(홍길동)\n장소: 서울중앙지방법원\n내용: 항소이유서 제출기한",
    }
    timed = {
        "summary": "조장연 [변론기일]", "location": "김포시법원 법정",
        "start": {"dateTime": "2026-06-11T10:00:00+09:00"},
        "description": "사건번호: 1\n의뢰인: 조장연(조장연)\n장소: 김포시법원 법정\n"
                       "출석변호사: ▲김정아\n내용: 변론기일",
    }
    msg = build_message([timed, deadline], date(2026, 6, 11), CFG)
    expected = (
        "📅 260611 목요일\n\n"
        "[기한]\n"
        "[홍길동] 항소이유서 제출기한\n"
        "        서울중앙지방법원\n\n"
        "[일정]\n"
        "10:00 [조장연] 변론기일 > 아변님\n"
        "        김포시법원 법정"
    )
    assert msg == expected


def test_lead_prefix():
    ev = {
        "summary": "조장연 [변론기일]", "location": "김포시법원 법정",
        "start": {"dateTime": "2026-06-15T10:00:00+09:00"},
        "description": "사건번호: 1\n의뢰인: 조장연(조장연)\n장소: 김포시법원 법정\n"
                       "출석변호사: ▲김정아\n내용: 변론기일\n담당직원: #송무1팀",
    }
    msg = build_message([ev], date(2026, 6, 15), CFG, lead="[송무1팀] 내일 일정")
    assert msg.startswith("📅 [송무1팀] 내일 일정(260615, 월)\n\n")


def test_event_in_team():
    gijil = {"description": "사건번호: 1\n담당직원: #송무2팀\n내용: 변론기일"}
    nongijil = {"description": "담당(변호사): 이돈호\n담당(직원): #송무1팀"}
    leave = {"description": "담당(직원): 손진영,#운영팀,#휴가"}
    assert event_in_team(gijil, "송무2팀") is True
    assert event_in_team(gijil, "송무1팀") is False
    assert event_in_team(nongijil, "송무1팀") is True
    assert event_in_team(leave, "송무1팀") is False
    assert event_in_team(leave, "송무2팀") is False
    support = {"description": "구분: 상담\n담당(변호사): 김태환\n담당(직원): #상담지원팀"}
    assert event_in_team(support, "상담지원팀") is True
    assert event_in_team(support, "송무1팀") is False


def test_event_in_team_cross_team_attendance():
    # 송무1팀 사건인데 송무2팀 김수인이 대신 출석 -> 송무1팀(사건)·송무2팀(출석) 모두 포함
    ev = {
        "description": "사건번호: 1\n출석변호사: 김수인\n담당직원: #송무1팀\n내용: 조사기일",
    }
    assert event_in_team(ev, "송무1팀", CFG.teams) is True   # 담당직원 태그
    assert event_in_team(ev, "송무2팀", CFG.teams) is True   # 출석변호사 소속
    assert event_in_team(ev, "송무3팀", CFG.teams) is False
    # teams 미전달 시(구버전 호출)에는 출석변호사 기반 포함이 동작하지 않음
    assert event_in_team(ev, "송무2팀") is False

    # 출석변호사가 빈칸(미입회)이면 어느 팀도 출석 기준으로 끌어오지 않음
    empty = {"description": "사건번호: 2\n출석변호사: \n담당직원: #송무3팀\n내용: 조사기일"}
    assert event_in_team(empty, "송무3팀", CFG.teams) is True   # 담당직원 태그만
    assert event_in_team(empty, "송무2팀", CFG.teams) is False

    # 그 외 일정은 담당(변호사) 기준으로 출석팀 판정
    nongijil = {"description": "담당(변호사): 채원협\n담당(직원): #송무1팀"}
    assert event_in_team(nongijil, "송무3팀", CFG.teams) is True   # 채원협=송무3팀


def test_solo_damdang_fallback_when_attendee_blank():
    # 실제 2026-06-16 14:00 김현규 케이스: 출석변호사 미기재 + 담당변호사 단독(김수인)
    ev = {
        "summary": "김현규 [조사기일]",
        "start": {"dateTime": "2026-06-16T14:00:00+09:00"},
        "description": "사건번호: 2026-1720\n의뢰인: 김현규(김현규)\n"
                       "담당변호사: 김수인\n내용: 조사기일",
    }
    assert _fmt(ev) == ("14:00 [김현규] 조사기일 > 수변님", [])

    # 출석변호사 칸이 공백이어도 동일하게 담당변호사 단독 폴백
    ev2 = {
        "summary": "김봉주 [공판기일]",
        "start": {"dateTime": "2026-06-11T11:00:00+09:00"},
        "description": "사건번호: 1\n의뢰인: 김봉주\n담당변호사: 천기섭\n"
                       "출석변호사: \n내용: 공판기일",
    }
    assert _fmt(ev2) == ("11:00 [김봉주] 공판기일 > 천변님", [])


def test_no_fallback_when_multiple_damdang_or_explicit_misiphoe():
    # 담당변호사 2명이면 누가 출석인지 불명확 -> 폴백하지 않고 미입회
    multi = {
        "summary": "김민지 [조사기일]",
        "start": {"dateTime": "2026-06-11T14:00:00+09:00"},
        "description": "사건번호: 2\n담당변호사: 김수인,천기섭\n출석변호사: \n내용: 조사기일",
    }
    assert _fmt(multi) == ("14:00 [김민지] 조사기일 > 미입회", [])

    # 출석변호사 칸에 '미입회' 명시 -> 담당변호사 단독이어도 미입회 유지
    explicit = {
        "summary": "김민지 [조사기일]",
        "start": {"dateTime": "2026-06-11T14:00:00+09:00"},
        "description": "사건번호: 3\n담당변호사: 김수인\n출석변호사: 미입회\n내용: 조사기일",
    }
    assert _fmt(explicit) == ("14:00 [김민지] 조사기일 > 미입회", [])


def test_solo_damdang_fallback_drives_cross_team():
    # 송무1팀 사건이고 출석변호사 미기재 + 담당변호사 단독 김수인(송무2팀)
    # -> 폴백된 출석자 기준으로 송무2팀에도 포함
    ev = {
        "description": "사건번호: 1\n담당변호사: 김수인\n담당직원: #송무1팀\n내용: 조사기일",
    }
    assert event_in_team(ev, "송무1팀", CFG.teams) is True   # 담당직원 태그
    assert event_in_team(ev, "송무2팀", CFG.teams) is True   # 폴백 출석자=김수인


def test_result_non_attend_overrides_listed_attorney():
    # 출석변호사 칸에 (출석 예정이던) 이름이 있어도, 결과가 '미출석'이면 미출석으로 표기.
    ev = {
        "summary": "<미출석> 배수현 [공판기일]",
        "location": "서울중앙지방법원 서관 526호 법정",
        "start": {"dateTime": "2026-06-25T11:20:00+09:00"},
        "description": (
            "사건번호: 2025고단6173\n의뢰인: 배수현(배수현)\n장소: 서울중앙지방법원 서관 526호 법정\n"
            "담당변호사: 김태환,김수인\n출석변호사: ▲이돈호 (담당: 김태환,김수인)\n"
            "담당직원: #송무2팀\n내용: 공판기일(서관 526호 법정 11:20)\n결과: 미출석"
        ),
    }
    assert _fmt(ev) == ("11:20 [배수현] 공판기일 > 미출석", ["서울중앙지방법원 서관 526호 법정"])
    # 결과가 진행결과(변론종결 등)면 영향 없음 — 출석변호사 그대로.
    ev2 = dict(ev, description=ev["description"].replace("결과: 미출석", "결과: 변론종결"))
    assert _fmt(ev2) == ("11:20 [배수현] 공판기일 > 돈변님", ["서울중앙지방법원 서관 526호 법정"])


def test_weekend_bundle_header():
    # 금요일 저녁 묶음 머리말: 요일 풀네임 + 괄호엔 날짜만(요일 약칭 없음).
    assert format_header_weekend("송무3팀", date(2026, 6, 27)) == "📅 [송무3팀] 토요일 일정(260627)"
    assert format_header_weekend("송무1팀", date(2026, 6, 28)) == "📅 [송무1팀] 일요일 일정(260628)"
    assert format_header_weekend("송무2팀", date(2026, 6, 29)) == "📅 [송무2팀] 월요일 일정(260629)"


def test_build_message_head_override():
    # head 직접 지정 시 그 머리말을 그대로 쓰고, 일정 없으면 '일정 없음' 본문.
    head = format_header_weekend("송무3팀", date(2026, 6, 28))
    msg = build_message([], date(2026, 6, 28), CFG, head=head)
    assert msg == "📅 [송무3팀] 일요일 일정(260628)\n\n일정 없음"


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

