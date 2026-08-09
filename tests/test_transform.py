"""
변환 로직 회귀테스트 (예시 양식 기준).
실행:  python tests/test_transform.py
"""

import os
import sys
from datetime import date

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
CONFIG_DIR = os.path.join(ROOT, "config")

from transform import (  # noqa: E402
    Config,
    build_lawyer_message,
    build_message,
    build_office_meeting_message,
    build_section_message,
    build_team_message,
    event_in_team,
    event_in_team_by_staff,
    format_deadline,
    format_header,
    format_header_weekend,
    format_header_weekend_lead,
    format_lawyer_head,
    format_timed,
    lawyer_events,
    lawyer_owners,
    load_config,
    office_meeting_events,
    parse_description,
    team_event_count,
    team_events,
    team_sections,
)

CFG = Config(
    locations={},
    teams={
        "송무1팀": {
            "변호사": ["천기섭", "박정윤", "박준호", "김정아", "이종원"],
            "수습": ["신이나", "정희소", "이하영", "정진실"],
        },
        "송무2팀": {
            "변호사": ["김태환", "채원협", "김수인"],
            "수습": ["임현진", "김윤수", "박건우", "한충호"],
        },
        "상담지원팀": {"변호사": ["이돈호"], "태그": True},
    },
    staff={
        "천기섭": {"주담당": "임지혜", "부담당": "최수빈"},
        "김정아": {"주담당": "우서영", "부담당": "진정은"},
        "박준호": {"주담당": "우서영", "부담당": "진정은"},
        "김태환": {"주담당": "민은선", "부담당": "김영은"},
        "이돈호": {"담당직원": ["조준혁", "윤태린"]},
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
    assert _fmt(ev) == ("10:00 [조장연] 변론기일 > 김정아", ["김포시법원 법정"])


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
    assert _fmt(ev) == ("10:30 [장주원] 공판기일 > 박준호", ["서울고등법원 서관 제502호 법정"])


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
    assert _fmt(ev) == ("14:00 [박설] 조사기일 > 김수인", ["박설(010-7904-7204)"])


def test_investigation_types_unified():
    # 고소인조사 / 피고소인 조사 등 -> '조사기일'로 통일
    for content, summary in [("고소인조사", "윤민아 [고소인조사]"), ("피고소인 조사", "정우 [피고소인 조사]")]:
        ev = {
            "summary": summary,
            "start": {"dateTime": "2026-06-11T10:00:00+09:00"},
            "description": f"사건번호: 9\n의뢰인: 윤민아\n출석변호사: ▲김태환\n내용: {content}",
        }
        line, _ = _fmt(ev)
        assert line == "10:00 [윤민아] 조사기일 > 김태환", line


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
    assert _fmt(ev) == ("14:00 [신혜원] 변론기일 > 김태환, 신이나", ["서울중앙지방법원"])


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
        "14:00 [더 주 주식회사(김주식)] 조사기일 > 채원협",
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
    assert _fmt(ev) == ("10:30 [장주원] 공판기일 > 박준호", ["서울고등법원"])


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
    assert _fmt(ev) == ("14:30 [곽승우] 변론기일 > 이종원", ["영상재판"])


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
    assert _fmt(ev) == ("14:00 [박설] 조사기일 > 김수인", ["영상재판", "박설(010-7904-7204)"])


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
    assert _fmt(ev) == ("10:00 [조장연] 변론기일 > 김정아", ["김포시법원 법정"])


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
        "10:30 [오승곤] 조사기일 > 박준호",
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
    assert line == "10:00 [박선영] 변론기일 > 복대리", line


# --- 그 외 일정(담당변호사로 출석표기, 제목 그대로) ---------------------------- #
def test_non_gijil_with_brackets_title():
    ev = {
        "summary": "[엄태웅] 스마트접견",
        "start": {"dateTime": "2026-06-11T14:00:00+09:00"},
        "description": "담당(변호사): 이돈호\n담당(직원): #송무1팀",
    }
    assert _fmt(ev) == ("14:00 [엄태웅] 스마트접견 > 이돈호", [])


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
    assert _fmt(ev) == ("11:00 [이상열] 스마트접견 > 김태환", ["접견번호 : 002317"])


def test_visit_number_no_colon():
    # 콜론 없이 '접견번호 007504'처럼 띄어쓰기로 적힌 경우도 인식(필드로 안 잡히는 케이스).
    ev = {
        "summary": "[장주원] 스마트접견(돈변님)",
        "start": {"dateTime": "2026-06-25T11:00:00+09:00"},
        "description": (
            "접견번호 007504\n노션접견디비 > 접견예약증 업로드되어있습니다\n"
            "담당(변호사): 이돈호\n담당(직원): #송무1팀,#상담지원팀"
        ),
    }
    assert _fmt(ev) == ("11:00 [장주원] 스마트접견(돈변님) > 이돈호", ["접견번호 : 007504"])


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
        "14:00 [김갑동] 화상접견 > 이돈호",
        ["서울남부교도소", "접견번호 : 12345", "비고 : 통역 필요"],
    )


def test_non_gijil_meeting():
    ev = {
        "summary": "황진주 미팅",
        "start": {"dateTime": "2026-06-11T15:00:00+09:00"},
        "description": "담당(변호사): 이돈호,신이나",
    }
    assert _fmt(ev) == ("15:00 황진주 미팅 > 이돈호, 신이나", [])


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
        "10:00 [조장연] 변론기일 > 김정아\n"
        "        김포시법원 법정\n\n"
        "14:00 [엄태웅] 스마트접견 > 이돈호"
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
        "10:00 [조장연] 변론기일 > 김정아\n"
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
        "10:00 [조장연] 변론기일 > 김정아\n"
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
        "10:00 [조장연] 변론기일 > 김정아\n"
        "        김포시법원 법정"
    )
    assert msg == expected


def test_include_deadlines_false_omits_deadline_section():
    # 상담지원팀 익일 알림 등: include_deadlines=False면 [기한] 섹션을 통째로 생략,
    # 시간 일정은 그대로 [일정]에 남는다.
    deadline = {
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
    msg = build_message([timed, deadline], date(2026, 6, 11), CFG, include_deadlines=False)
    assert "[기한]" not in msg
    assert "항소이유서 제출기한" not in msg
    assert msg == (
        "📅 260611 목요일\n\n"
        "[일정]\n"
        "10:00 [조장연] 변론기일 > 김정아\n"
        "        김포시법원 법정"
    )


def test_lead_prefix():
    ev = {
        "summary": "조장연 [변론기일]", "location": "김포시법원 법정",
        "start": {"dateTime": "2026-06-15T10:00:00+09:00"},
        "description": "사건번호: 1\n의뢰인: 조장연(조장연)\n장소: 김포시법원 법정\n"
                       "출석변호사: ▲김정아\n내용: 변론기일\n담당직원: #송무1팀",
    }
    msg = build_message([ev], date(2026, 6, 15), CFG, lead="[송무1팀] 내일 일정")
    assert msg.startswith("📅 [송무1팀] 내일 일정(260615, 월)\n\n")


def test_mention_morning_inline():
    # 오전 단일 알림: 머리말 끝에 ' @everyone'(한 줄) + 빈 줄 + 본문
    deadline = {
        "summary": "홍길동 [제출기한]",
        "start": {"date": "2026-06-11"},
        "description": "사건번호: 1\n의뢰인: 홍길동(홍길동)\n내용: 항소이유서 제출기한",
    }
    msg = build_message([deadline], date(2026, 6, 11), CFG, mention=True)
    assert msg.startswith("📅 260611 목요일 @everyone\n\n[기한]\n")


def test_mention_afternoon_block():
    # 오후/익일 알림: 머리말 아랫줄 '@everyone' + 빈 줄 + 본문 (v1.14.0에서 빈 줄 추가)
    ev = {
        "summary": "조장연 [변론기일]", "location": "김포시법원 법정",
        "start": {"dateTime": "2026-06-15T10:00:00+09:00"},
        "description": "사건번호: 1\n의뢰인: 조장연(조장연)\n장소: 김포시법원 법정\n"
                       "출석변호사: ▲김정아\n내용: 변론기일\n담당직원: #송무1팀",
    }
    msg = build_message([ev], date(2026, 6, 15), CFG, lead="[송무1팀] 내일 일정", mention=True)
    assert msg.startswith("📅 [송무1팀] 내일 일정(260615, 월)\n@everyone\n\n[일정]\n")


def test_event_in_team():
    # (v1.13.0) 송무팀은 태그가 아니라 담당변호사 소속 팀으로 분류
    gijil = {"description": "사건번호: 1\n담당변호사: 김태환\n내용: 변론기일"}
    assert event_in_team(gijil, "송무2팀", CFG.teams) is True
    assert event_in_team(gijil, "송무1팀", CFG.teams) is False
    nongijil = {"description": "구분: 회의\n담당(변호사): 천기섭"}
    assert event_in_team(nongijil, "송무1팀", CFG.teams) is True
    assert event_in_team(nongijil, "송무2팀", CFG.teams) is False
    # 직원 일정(명단 밖 이름)은 어느 팀에도 미포함
    leave = {"summary": "손진영 오후반차", "description": "담당(직원): 손진영,#운영팀,#휴가"}
    assert event_in_team(leave, "송무1팀", CFG.teams) is False
    assert event_in_team(leave, "송무2팀", CFG.teams) is False


def test_songmu_tag_ignored():
    # 잔존 송무팀 태그는 무시 — 담당변호사 소속(송무2팀)만 따른다
    ev = {"description": "사건번호: 1\n담당변호사: 김태환\n담당직원: #송무1팀\n내용: 변론기일"}
    assert event_in_team(ev, "송무1팀", CFG.teams) is False
    assert event_in_team(ev, "송무2팀", CFG.teams) is True
    # 태그만 있고 담당변호사가 없으면 송무팀 알림에 미포함
    tag_only = {"description": "사건번호: 2\n담당직원: #송무2팀\n내용: 변론기일"}
    assert event_in_team(tag_only, "송무2팀", CFG.teams) is False


def test_team_by_responsible_multi_team():
    # 서로 다른 팀 변호사가 함께 담당 -> 양쪽 팀 모두 포함
    ev = {"description": "사건번호: 1\n담당변호사: 김정아,김태환\n내용: 변론기일"}
    assert event_in_team(ev, "송무1팀", CFG.teams) is True
    assert event_in_team(ev, "송무2팀", CFG.teams) is True


def test_trainee_fallback_only_without_senior():
    # 담당변호사에 수습만 있으면 수습 매핑으로 폴백
    trainee = {"description": "사건번호: 1\n담당변호사: 신이나\n내용: 변론기일"}
    assert event_in_team(trainee, "송무1팀", CFG.teams) is True
    assert event_in_team(trainee, "송무2팀", CFG.teams) is False
    # 정변호사가 하나라도 있으면 수습 매핑 미발동(김태환=2팀, 신이나=1팀 수습이어도 2팀만)
    mixed = {"description": "사건번호: 2\n담당변호사: 김태환,신이나\n내용: 변론기일"}
    assert event_in_team(mixed, "송무2팀", CFG.teams) is True
    assert event_in_team(mixed, "송무1팀", CFG.teams) is False


def test_sangdam_by_tag_or_donho():
    # 상담지원팀은 태그 매칭 유지
    support = {"description": "구분: 상담\n담당(변호사): 김태환\n담당(직원): #상담지원팀"}
    assert event_in_team(support, "상담지원팀", CFG.teams) is True
    assert event_in_team(support, "송무2팀", CFG.teams) is True   # 김태환 담당이라 2팀에도(중복 노출 의도)
    assert event_in_team(support, "송무1팀", CFG.teams) is False
    # 태그가 없어도 이돈호 담당이면 포함
    donho = {"description": "구분: 상담\n담당(변호사): 이돈호"}
    assert event_in_team(donho, "상담지원팀", CFG.teams) is True
    assert event_in_team(donho, "송무1팀", CFG.teams) is False
    # 김태환 담당(태그 없음)은 이제 상담지원팀에 미포함 — 송무2팀 기준으로만
    taehwan = {"description": "구분: 상담\n담당(변호사): 김태환"}
    assert event_in_team(taehwan, "상담지원팀", CFG.teams) is False
    # 이돈호가 출석변호사인 기일도 팔로우(교차출석)
    attend = {"description": "사건번호: 1\n담당변호사: 김태환,김수인\n"
                             "출석변호사: ▲이돈호 (담당: 김태환,김수인)\n내용: 공판기일"}
    assert event_in_team(attend, "상담지원팀", CFG.teams) is True
    assert event_in_team(attend, "송무2팀", CFG.teams) is True


def test_donho_with_trainee_pins_no_songmu():
    # 이돈호(정변호사)+신이나(수습) 담당 -> 1차 매핑 성립(상담지원팀)이라 수습 폴백 미발동
    ev = {"description": "구분: 상담\n담당(변호사): 이돈호,신이나"}
    assert event_in_team(ev, "상담지원팀", CFG.teams) is True
    assert event_in_team(ev, "송무1팀", CFG.teams) is False


def test_no_lawyer_event_in_no_team():
    # 담당변호사 필드가 없거나 명단 밖 이름뿐(운영팀 자체 일정 등) -> 어느 팀에도 미포함
    for ev in (
        {"summary": "사무실 정기점검", "description": ""},
        {"description": "담당(변호사): 김성호\n담당(직원): 손진영"},
    ):
        for team in ("송무1팀", "송무2팀", "상담지원팀"):
            assert event_in_team(ev, team, CFG.teams) is False


def test_damdang_paren_fallback():
    # 독립 '담당변호사' 필드 없이 출석변호사 칸 괄호에만 담당이 적힌 실데이터 형태
    # -> 괄호 안(채원협=송무2팀)으로 사건 팀 판정 + 출석자(이돈호)로 상담지원팀 팔로우
    ev = {"description": "사건번호: 1\n출석변호사: ▲이돈호 (담당: 채원협)\n내용: 공판기일"}
    assert event_in_team(ev, "송무2팀", CFG.teams) is True
    assert event_in_team(ev, "상담지원팀", CFG.teams) is True
    assert event_in_team(ev, "송무1팀", CFG.teams) is False


def test_leave_follow_by_name():
    # 휴무 일정은 담당변호사 필드가 없으므로 제목의 이름으로 팀 판정(정+수습)
    assert event_in_team({"summary": "김정아 연차"}, "송무1팀", CFG.teams) is True
    assert event_in_team({"summary": "김정아 연차"}, "송무2팀", CFG.teams) is False
    assert event_in_team({"summary": "정진실 오전반차"}, "송무1팀", CFG.teams) is True   # 수습 포함
    assert event_in_team({"summary": "한충호 휴가"}, "송무2팀", CFG.teams) is True
    assert event_in_team({"summary": "손진영 오후반반차"}, "송무1팀", CFG.teams) is False


def test_legacy_list_roster_compat():
    # 구형(list) teams.yaml 하위호환: 태그 매칭 + 출석 팔로우 동작 유지
    legacy = Config(locations={}, teams={"송무1팀": ["천기섭"]})
    tagged = {"description": "사건번호: 1\n담당직원: #송무1팀\n내용: 변론기일"}
    assert event_in_team(tagged, "송무1팀", legacy.teams) is True
    attend = {"description": "사건번호: 2\n출석변호사: 천기섭\n내용: 공판기일"}
    assert event_in_team(attend, "송무1팀", legacy.teams) is True


def test_event_in_team_cross_team_attendance():
    # 송무1팀 사건(담당 천기섭)인데 송무2팀 김수인이 대신 출석 -> 양 팀 모두 포함
    ev = {
        "description": "사건번호: 1\n담당변호사: 천기섭\n출석변호사: 김수인\n내용: 조사기일",
    }
    assert event_in_team(ev, "송무1팀", CFG.teams) is True   # 담당변호사 소속
    assert event_in_team(ev, "송무2팀", CFG.teams) is True   # 출석변호사 소속
    # teams 미전달 시(구버전 호출)에는 태그 매칭만 동작하므로 미포함
    assert event_in_team(ev, "송무2팀") is False

    # 출석변호사가 빈칸 + 담당변호사 2명(폴백 없음) -> 담당 소속 팀만
    empty = {"description": "사건번호: 2\n담당변호사: 천기섭,박정윤\n출석변호사: \n내용: 조사기일"}
    assert event_in_team(empty, "송무1팀", CFG.teams) is True
    assert event_in_team(empty, "송무2팀", CFG.teams) is False

    # 그 외 일정은 담당(변호사) 기준으로 판정
    nongijil = {"description": "담당(변호사): 채원협"}
    assert event_in_team(nongijil, "송무2팀", CFG.teams) is True   # 채원협=송무2팀
    assert event_in_team(nongijil, "송무1팀", CFG.teams) is False


def test_solo_damdang_fallback_when_attendee_blank():
    # 실제 2026-06-16 14:00 김현규 케이스: 출석변호사 미기재 + 담당변호사 단독(김수인)
    ev = {
        "summary": "김현규 [조사기일]",
        "start": {"dateTime": "2026-06-16T14:00:00+09:00"},
        "description": "사건번호: 2026-1720\n의뢰인: 김현규(김현규)\n"
                       "담당변호사: 김수인\n내용: 조사기일",
    }
    assert _fmt(ev) == ("14:00 [김현규] 조사기일 > 김수인", [])

    # 출석변호사 칸이 공백이어도 동일하게 담당변호사 단독 폴백
    ev2 = {
        "summary": "김봉주 [공판기일]",
        "start": {"dateTime": "2026-06-11T11:00:00+09:00"},
        "description": "사건번호: 1\n의뢰인: 김봉주\n담당변호사: 천기섭\n"
                       "출석변호사: \n내용: 공판기일",
    }
    assert _fmt(ev2) == ("11:00 [김봉주] 공판기일 > 천기섭", [])


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


def test_solo_damdang_only_own_team():
    # 출석변호사 미기재 + 담당변호사 단독 김수인(송무2팀)
    # -> 담당 소속(송무2팀)에만 포함. 잔존 송무1팀 태그는 무시.
    ev = {
        "description": "사건번호: 1\n담당변호사: 김수인\n담당직원: #송무1팀\n내용: 조사기일",
    }
    assert event_in_team(ev, "송무2팀", CFG.teams) is True   # 담당 소속(폴백 출석자와 일치)
    assert event_in_team(ev, "송무1팀", CFG.teams) is False  # 태그 미사용


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
    assert _fmt(ev2) == ("11:20 [배수현] 공판기일 > 이돈호", ["서울중앙지방법원 서관 526호 법정"])


def test_weekend_bundle_header():
    # 금요일 저녁 묶음 머리말: 요일 풀네임 + 괄호엔 날짜만(요일 약칭 없음).
    assert format_header_weekend("송무1팀", date(2026, 6, 27)) == "📅 [송무1팀] 토요일 일정(260627)"
    assert format_header_weekend("송무1팀", date(2026, 6, 28)) == "📅 [송무1팀] 일요일 일정(260628)"
    assert format_header_weekend("송무2팀", date(2026, 6, 29)) == "📅 [송무2팀] 월요일 일정(260629)"


def test_build_message_head_override():
    # head 직접 지정 시 그 머리말을 그대로 쓰고, 일정 없으면 '일정 없음' 본문.
    head = format_header_weekend("송무2팀", date(2026, 6, 28))
    msg = build_message([], date(2026, 6, 28), CFG, head=head)
    assert msg == "📅 [송무2팀] 일요일 일정(260628)\n\n일정 없음"


# --------------------------------------------------------------------------- #
# v1.14.0 — 오전 [기한]/[일정]/[휴무] 3분할, 팀 알림의 변호사별 분할
# --------------------------------------------------------------------------- #
DEADLINE_EV = {
    "summary": "홍길동 [제출기한]",
    "start": {"date": "2026-08-10"},
    "description": "사건번호: 1\n의뢰인: 홍길동(홍길동)\n담당변호사: 천기섭\n내용: 항소이유서 제출기한",
}
GIJIL_EV = {
    "summary": "조장연 [변론기일]", "location": "김포시법원 법정",
    "start": {"dateTime": "2026-08-10T10:00:00+09:00"},
    "description": "사건번호: 2\n의뢰인: 조장연(조장연)\n장소: 김포시법원 법정\n"
                   "담당변호사: 김정아,박준호\n출석변호사: ▲김정아\n내용: 변론기일",
}
STAFF_LEAVE_EV = {"summary": "우서영 연차", "start": {"date": "2026-08-10"},
                  "description": "담당(변호사): 박준호,김정아\n담당(직원): #휴가,진정은"}
DAY = date(2026, 8, 10)


def test_morning_section_split():
    # 오전 알림은 섹션마다 별도 메시지. 머리말 끝에 '[섹션]'이 붙는다.
    msgs = {s: build_section_message([DEADLINE_EV, GIJIL_EV], DAY, CFG, s) for s in
            ("기한", "일정", "휴무")}
    assert msgs["기한"] == "📅 260810 월요일 [기한]\n\n[홍길동] 항소이유서 제출기한"
    assert msgs["일정"].startswith("📅 260810 월요일 [일정]\n\n10:00 [조장연] 변론기일 > 김정아")
    # 빈 섹션도 '없음'으로 발송한다(그날 확인이 끝났음을 알 수 있게).
    assert msgs["휴무"] == "📅 260810 월요일 [휴무]\n\n없음"


def test_morning_section_mention_only_on_one():
    # @everyone 은 [일정] 메시지에만 — 알림 3연타를 피한다.
    assert "@everyone" in build_section_message([], DAY, CFG, "일정", mention=True)
    assert "@everyone" not in build_section_message([], DAY, CFG, "기한")


def test_team_sections_seniors_then_trainees():
    # 팀 섹션 순서는 정변호사 → 수습변호사. (대표변호사는 팀 알림에 끼지 않는다)
    assert team_sections("송무1팀", CFG) == [
        "천기섭", "박정윤", "박준호", "김정아", "이종원",
        "신이나", "정희소", "이하영", "정진실",
    ]
    assert "이돈호" not in team_sections("송무1팀", CFG)


def test_lawyer_section_head():
    # 팀 알림 안의 변호사 머리말에도 날짜가 붙는다. 라벨이 없으면 이름만.
    # (v1.17.0: '#' 대제목이 Discord 에서 너무 커서 소제목 '###' 으로 변경)
    assert format_lawyer_head("천기섭", DAY, "내일 일정") == "### 천기섭 변호사 내일 일정(260810, 월)"
    assert format_lawyer_head("천기섭", DAY) == "### 천기섭 변호사"


def test_team_message_splits_by_lawyer():
    msg = build_team_message([DEADLINE_EV, GIJIL_EV], DAY, CFG, "송무1팀",
                             lead="[송무1팀] 내일 일정", day_label="내일 일정", mention=True)
    assert msg.startswith(
        "📅 [송무1팀] 내일 일정(260810, 월)\n@everyone\n\n### 천기섭 변호사 내일 일정(260810, 월)\n"
    )
    # 공동담당(김정아·박준호)은 양쪽 변호사 섹션에 모두 실린다.
    assert msg.count("10:00 [조장연] 변론기일 > 김정아") == 2
    # 일정이 없는 변호사도 세 칸을 '없음'으로 보여준다.
    assert "### 정진실 변호사 내일 일정(260810, 월)\n[기한]\n없음\n\n[일정]\n없음\n\n[휴무]\n없음" in msg
    # 담당변호사 섹션 안에서는 [기한]/[일정]/[휴무] 순서를 지킨다.
    assert "[기한]\n[홍길동] 항소이유서 제출기한\n\n[일정]\n없음\n\n[휴무]\n없음" in msg


def test_lawyer_message_standalone():
    # 개인 알림 — '### ○○ 변호사' 섹션 머리말 없이 세 칸만, 본인 일정만 담는다.
    msg = build_lawyer_message([DEADLINE_EV, GIJIL_EV], DAY, CFG, "김정아",
                               day_label="내일 일정", mention=True)
    assert msg == (
        "📅 김정아 변호사 내일 일정(260810, 월)\n@everyone\n\n"
        "[기한]\n없음\n\n"
        "[일정]\n10:00 [조장연] 변론기일 > 김정아\n        김포시법원 법정\n\n"
        "[휴무]\n없음"
    )
    # 본인과 무관한 일정(천기섭 담당 기한)은 들어오지 않는다.
    assert lawyer_events([DEADLINE_EV, GIJIL_EV], CFG, "이돈호") == []


def test_staff_leave_goes_to_their_lawyers():
    # 직원 휴무는 staff.yaml 담당 변호사들의 [휴무] 칸에 함께 실린다.
    names = team_sections("송무1팀", CFG)
    assert lawyer_owners(STAFF_LEAVE_EV, names, CFG) == {"박준호", "김정아"}
    # 변호사 본인의 휴무는 본인 섹션으로.
    own = {"summary": "천기섭 특별휴가(오후반차)", "start": {"date": "2026-08-10"},
           "description": "담당(변호사): 천기섭"}
    assert lawyer_owners(own, names, CFG) == {"천기섭"}
    # 이돈호 담당직원의 휴무는 이돈호 개인 알림으로(송무팀 명단에는 안 잡힘).
    chair = {"summary": "조준혁 연차", "start": {"date": "2026-08-10"},
             "description": "담당(직원): 조준혁,#휴가"}
    assert lawyer_owners(chair, names, CFG) == set()
    assert lawyer_owners(chair, ["이돈호"], CFG) == {"이돈호"}


def test_team_message_other_bucket():
    # 어느 변호사에도 배정 안 되지만 팀 알림 대상인 일정은 맨 아래 '### 기타'로.
    tagged = {"summary": "상담지원팀 회의", "start": {"dateTime": "2026-08-10T09:00:00+09:00"},
              "description": "담당(직원): #상담지원팀"}
    msg = build_team_message([tagged], DAY, CFG, "상담지원팀", lead="[상담지원팀] 내일 일정")
    assert "### 기타\n[기한]\n없음\n\n[일정]\n09:00 상담지원팀 회의" in msg
    # 팀과 무관한 일정은 '기타'에도 실리지 않는다.
    assert "### 기타" not in build_team_message([GIJIL_EV], DAY, CFG, "상담지원팀")


def test_staff_errand_shows_first_staff():
    # 기록 수령·복사·등사는 변호사가 아니라 담당직원 맨 앞 사람이 간다.
    ev = {
        "summary": "[전영상] 기록 수령",
        "start": {"dateTime": "2026-08-10T09:00:00+09:00"},
        "description": "안산지원 재판부\n담당(변호사): 박준호,김정아,신이나,이하영\n담당(직원): 우서영,진정은",
    }
    assert _fmt(ev) == ("09:00 [전영상] 기록 수령 > 우서영", [])
    # 팀 태그(#…)는 사람이 아니므로 건너뛴다.
    ev2 = dict(ev, description="담당(변호사): 김태환\n담당(직원): #송무2팀,민은선,김영은")
    assert _fmt(ev2)[0] == "09:00 [전영상] 기록 수령 > 민은선"
    # 담당직원이 없으면 평소대로 담당변호사 표기.
    ev3 = dict(ev, description="담당(변호사): 김태환")
    assert _fmt(ev3)[0] == "09:00 [전영상] 기록 수령 > 김태환"
    # 수령·복사·등사가 아닌 일정은 영향 없음.
    ev4 = dict(ev, summary="[전영상] 사건 회의")
    assert _fmt(ev4)[0] == "09:00 [전영상] 사건 회의 > 박준호, 김정아, 신이나, 이하영"


def test_html_entities_unescaped():
    # 구글 캘린더가 넘겨주는 '&amp;' 등이 사람이 읽는 글자로 나가야 한다.
    ev = {"summary": "(회의) 개인정보 &amp; AI팀",
          "start": {"dateTime": "2026-08-10T13:00:00+09:00"},
          "description": "담당(변호사): 신이나"}
    msg = build_section_message([ev], DAY, CFG, "일정")
    assert "13:00 (회의) 개인정보 & AI팀 > 신이나" in msg
    assert "&amp;" not in msg


def test_team_event_count_no_double_count():
    # 공동담당으로 두 섹션에 실려도 건수는 1건.
    assert team_event_count([GIJIL_EV], CFG, "송무1팀") == 1
    assert team_event_count([GIJIL_EV], CFG, "송무2팀") == 0


def test_team_message_skip_empty():
    # 금요일 묶음용 — 일정 없는 변호사 섹션은 생략한다.
    msg = build_team_message([DEADLINE_EV], DAY, CFG, "송무1팀", skip_empty=True)
    assert "### 천기섭 변호사" in msg
    assert "### 정진실 변호사" not in msg


def test_weekend_bundle_lawyer_block():
    # 금요일 묶음의 일자별 머리말은 팀·개인 알림이 같은 양식.
    sat = date(2026, 8, 15)
    assert format_header_weekend_lead("이돈호 변호사", sat) == "📅 이돈호 변호사 토요일 일정(260815)"
    assert format_header_weekend("송무1팀", sat) == "📅 [송무1팀] 토요일 일정(260815)"
    # 개인 알림도 head 를 주면 그 머리말로 한 블록을 만든다(묶음용).
    leave = {"summary": "조준혁 연차", "start": {"date": "2026-08-15"},
             "description": "담당(직원): 조준혁,#휴가"}
    msg = build_lawyer_message([leave], sat, CFG, "이돈호",
                               head=format_header_weekend_lead("이돈호 변호사", sat))
    assert msg == ("📅 이돈호 변호사 토요일 일정(260815)\n\n"
                   "[기한]\n없음\n\n[일정]\n없음\n\n[휴무]\n조준혁 연차")


# --------------------------------------------------------------------------- #
# v1.17.0 — 채널 분리: 오전 팀 알림(한 통), 사무실 상담 알림(1006호·404호·인천)
# --------------------------------------------------------------------------- #
def test_morning_team_message_combined():
    # 오전 팀 알림 — 팀 일정 전체를 [기한]/[일정]/[휴무] 한 통으로(변호사별 분할 없음).
    evs = team_events([DEADLINE_EV, GIJIL_EV], CFG, "송무1팀")
    assert len(evs) == 2
    msg = build_message(evs, DAY, CFG, lead="[송무1팀] 오늘 일정", mention=True)
    assert msg.startswith(
        "📅 [송무1팀] 오늘 일정(260810, 월)\n@everyone\n\n[기한]\n[홍길동] 항소이유서 제출기한"
    )
    assert "10:00 [조장연] 변론기일 > 김정아" in msg
    assert "###" not in msg  # 오전 팀 알림은 변호사별 소제목 없이 한 덩어리
    # 다른 팀 일정은 걸러진다.
    assert team_events([DEADLINE_EV, GIJIL_EV], CFG, "송무2팀") == []


def test_office_meeting_message():
    # 사무실 상담 알림 — 1006호·404호·인천 [회의]만, 사무실별 '###' 섹션으로.
    cfg = load_config(CONFIG_DIR)  # locations.yaml 의 사무실 별칭 정규화 필요
    m1006 = {"summary": "[회의] (1006호) [강태오]상속 상담",
             "start": {"dateTime": "2026-08-10T11:00:00+09:00"},
             "description": "구분: 1006호\n담당(변호사): 이돈호"}
    incheon = {"summary": "[회의] (인천) [박설]이혼 상담",
               "start": {"dateTime": "2026-08-10T14:00:00+09:00"},
               "description": "구분: 학익동\n담당(변호사): 김정아"}
    outside = {"summary": "[회의] (외부) [김봉주]현장 미팅",
               "start": {"dateTime": "2026-08-10T15:00:00+09:00"},
               "description": "구분: 강남 카페\n담당(변호사): 천기섭"}
    gijil = dict(GIJIL_EV)  # [회의]가 아닌 일정은 상담 알림에 실리지 않는다

    picked = office_meeting_events([m1006, incheon, outside, gijil], cfg)
    assert [ev["summary"] for ev in picked] == [m1006["summary"], incheon["summary"]]

    msg = build_office_meeting_message([m1006, incheon, outside, gijil], DAY, cfg,
                                       day_label="내일 일정", mention=True)
    assert msg.startswith(
        "📅 [상담] 내일 일정(260810, 월)\n@everyone\n\n"
        "### 서울 1006호\n11:00 [강태오] 상속 상담 > 이돈호"
    )
    # 상담이 없는 사무실도 '없음'으로 표기(그 방이 비어 있음을 확인).
    assert "### 서울 404호\n없음" in msg
    assert "### 인천사무소\n14:00 [박설] 이혼 상담 > 김정아" in msg
    # 섹션 제목이 곧 사무실 이름이므로 같은 장소 아랫줄은 중복 표기하지 않는다.
    assert "        서울 1006호" not in msg
    assert "김봉주" not in msg and "조장연" not in msg


def test_office_meeting_weekend_head():
    # 금요일 묶음용 — head 를 주면 그 머리말로 한 블록을 만든다.
    cfg = load_config(CONFIG_DIR)
    sat = date(2026, 8, 15)
    msg = build_office_meeting_message([], sat, cfg,
                                       head=format_header_weekend_lead("[상담]", sat))
    assert msg.startswith("📅 [상담] 토요일 일정(260815)\n\n### 서울 1006호\n없음")


# --------------------------------------------------------------------------- #
# v1.18.0 — 담당직원 소속팀 폴백, 라벨 없는 접견번호 인식
# --------------------------------------------------------------------------- #
def test_staff_team_fallback_for_donho_only_case():
    # 담당변호사가 이돈호뿐인 사건(접견 제외)은 담당직원 소속팀 알림에도 실린다.
    ev = {"summary": "[강성구] 조사 동행",
          "start": {"dateTime": "2026-08-10T11:00:00+09:00"},
          "description": "담당(변호사): 이돈호\n담당(직원): 민은선,#송무2팀,#상담지원팀"}
    assert event_in_team_by_staff(ev, "송무2팀", CFG) is True    # 민은선=김태환 담당(2팀)
    assert event_in_team_by_staff(ev, "송무1팀", CFG) is False
    assert [e["summary"] for e in team_events([ev], CFG, "송무2팀")] == ["[강성구] 조사 동행"]
    assert team_events([ev], CFG, "송무1팀") == []
    # 팀 알림에서는 어느 변호사 섹션도 아니므로 '### 기타'에 실린다.
    msg = build_team_message([ev], DAY, CFG, "송무2팀")
    assert "### 기타\n[기한]\n없음\n\n[일정]\n11:00 [강성구] 조사 동행 > 이돈호" in msg


def test_staff_team_fallback_not_for_songmu_cases():
    # 송무팀 변호사가 담당·출석인 사건은 직원 소속팀으로 새지 않는다(변호사 매핑 우선).
    ev = {"summary": "[박정민] 기록 검토",
          "start": {"dateTime": "2026-08-10T11:00:00+09:00"},
          "description": "담당(변호사): 김태환\n담당(직원): 우서영"}  # 우서영=1팀 직원
    assert event_in_team_by_staff(ev, "송무1팀", CFG) is False
    # 이돈호 사건이라도 담당직원이 이돈호 전속(조준혁 등)이면 송무팀 알림에 안 실린다.
    own = {"summary": "[안호준] 서면 회의",
           "start": {"dateTime": "2026-08-10T13:00:00+09:00"},
           "description": "담당(변호사): 이돈호\n담당(직원): 조준혁,#상담지원팀"}
    assert event_in_team_by_staff(own, "송무1팀", CFG) is False
    assert event_in_team_by_staff(own, "송무2팀", CFG) is False
    # 담당변호사가 아예 없는 일정(운영팀 등)도 종전대로 미포함.
    none = {"summary": "사무실 정기점검", "description": "담당(직원): 민은선"}
    assert event_in_team_by_staff(none, "송무2팀", CFG) is False


def test_staff_team_fallback_skips_visits():
    # 접견은 담당(변호사)=실제로 가는 변호사 기준 — 직원 소속팀 폴백을 적용하지 않는다.
    # (이돈호 변호사가 가는 접견은 팀 직원이 붙어 있어도 개인 알림에만 실린다)
    visit = {"summary": "[강성구] 스마트접견",
             "start": {"dateTime": "2026-08-10T11:00:00+09:00"},
             "description": "005260\n담당(변호사): 이돈호\n담당(직원): 민은선,#송무2팀"}
    assert event_in_team_by_staff(visit, "송무2팀", CFG) is False
    assert team_events([visit], CFG, "송무2팀") == []
    assert lawyer_events([visit], CFG, "이돈호") == [visit]
    # 송무팀 변호사가 가는 접견은 종전대로 그 변호사 팀·섹션에 실린다.
    team_visit = {"summary": "[이상열] 스마트접견",
                  "start": {"dateTime": "2026-08-10T11:00:00+09:00"},
                  "description": "접견번호 : 007367\n담당(변호사): 김태환\n담당(직원): 민은선"}
    assert event_in_team(team_visit, "송무2팀", CFG.teams) is True


def test_visit_number_without_label():
    # 라벨 없이 숫자만 달랑 적힌 줄도 접견번호로 인식한다.
    bare = {"summary": "[남승규] 스마트접견",
            "start": {"dateTime": "2026-08-10T11:00:00+09:00"},
            "description": "004627\n담당(변호사): 이돈호"}
    assert _fmt(bare) == ("11:00 [남승규] 스마트접견 > 이돈호", ["접견번호 : 004627"])
    # 라벨('스마트접견번호')이 윗줄, 번호가 다음 줄인 형태.
    label_above = {"summary": "[강성구] 스마트 접견",
                   "start": {"dateTime": "2026-08-10T11:00:00+09:00"},
                   "description": "스마트접견번호\n000074\n담당(변호사): 김수인"}
    assert _fmt(label_above)[1] == ["접견번호 : 000074"]
    # 전화번호(하이픈)·사건번호('key:' 꼴)는 접견번호로 오인하지 않는다.
    phone_only = {"summary": "[김성환] 스마트 접견",
                  "start": {"dateTime": "2026-08-10T11:00:00+09:00"},
                  "description": "사건번호: 2026고단41\n의뢰인: 김성환\n"
                                 "의뢰인연락처: 010-8406-5173\n내용: 스마트 접견\n담당변호사: 김태환"}
    assert all("접견번호" not in s for s in _fmt(phone_only)[1])
    # 기존 라벨 형태('접견번호 007504', '접견번호 : 007367')는 종전과 동일.
    labeled = dict(bare, description="접견번호 007504\n담당(변호사): 이돈호")
    assert _fmt(labeled)[1] == ["접견번호 : 007504"]


def test_real_config_rosters_and_staff():
    # 실제 config/*.yaml 이 읽히고, 팀 명단과 담당직원 명단이 서로 맞는지(오타 방지).
    cfg = load_config(CONFIG_DIR)
    for team in ("송무1팀", "송무2팀"):
        for name in team_sections(team, cfg):
            assert cfg.staff.get(name), f"{team}의 {name} 담당직원이 staff.yaml 에 없습니다"
    assert cfg.staff["천기섭"] == ["임지혜", "최수빈"]
    assert cfg.staff["김수인"] == ["김영은", "김유빈"]
    assert "조준혁" in cfg.staff["이돈호"]


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

