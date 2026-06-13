"""
캘린더 원본 이벤트 → 법무법인 노바 표준 양식 변환 (프로젝트의 핵심 로직)

출력 양식 예:
    📅 6/15(월) 오늘 일정

    [마감]
    [홍길동(서울중앙지법)] 항소이유서 제출기한

    [고명수(강남서)] 09:30 고소인조사 > 김변님 입회
    20:00 대면상담(학익동)
"""

import os
import re
from datetime import date, datetime
from zoneinfo import ZoneInfo

import yaml

KST = ZoneInfo("Asia/Seoul")
WEEKDAYS = ["월", "화", "수", "목", "금", "토", "일"]

# 광역시/도 (경찰서 약칭 시 접두 제거 대상)
METRO = [
    "서울", "부산", "대구", "인천", "광주", "대전", "울산", "세종",
    "경기", "강원", "충북", "충남", "전북", "전남", "경북", "경남", "제주",
]


class Config:
    """변호사/장소 약칭표 묶음."""

    def __init__(self, lawyers: dict, locations: dict):
        self.lawyers = lawyers or {}
        self.locations = locations or {}


def load_config(config_dir: str) -> Config:
    def _load(name):
        path = os.path.join(config_dir, name)
        with open(path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}

    return Config(_load("lawyers.yaml"), _load("locations.yaml"))


# --------------------------------------------------------------------------- #
# 원본 파싱
# --------------------------------------------------------------------------- #
def parse_description(desc: str) -> dict:
    """설명란의 'key: value' 줄들을 dict 로 변환."""
    fields = {}
    for line in (desc or "").splitlines():
        if ":" in line:
            key, _, value = line.partition(":")
            fields[key.strip()] = value.strip()
    return fields


def is_all_day(event: dict) -> bool:
    """시간 없는 종일(=마감/제출기한) 항목인지."""
    start = event.get("start", {})
    return "date" in start and "dateTime" not in start


def has_case(fields: dict) -> bool:
    """사건번호가 있으면 사건 연계 일정으로 본다."""
    return bool(fields.get("사건번호"))


def start_hhmm(event: dict):
    """시작시각을 KST 'HH:MM' 으로. 종일이면 None."""
    dt = event.get("start", {}).get("dateTime")
    if not dt:
        return None
    parsed = datetime.fromisoformat(dt).astimezone(KST)
    return parsed.strftime("%H:%M")


# --------------------------------------------------------------------------- #
# 필드 추출
# --------------------------------------------------------------------------- #
def extract_client(summary: str, fields: dict) -> str:
    """의뢰인명. 제목 '[' 앞 텍스트 우선, 없으면 설명 '의뢰인:' 필드."""
    name = ""
    if summary and "[" in summary:
        name = summary.split("[", 1)[0].strip()
    if not name:
        name = fields.get("의뢰인", "").split("(", 1)[0].strip()
    return _shorten_clients(name)


def _shorten_clients(name: str) -> str:
    """여러 명이면 '첫의뢰인 외 N명'."""
    if not name:
        return ""
    if "외" in name:  # Lawware 가 이미 '외 N명' 형태로 준 경우
        return name
    parts = [p.strip() for p in name.split(",") if p.strip()]
    if len(parts) <= 1:
        return name
    return f"{parts[0]} 외 {len(parts) - 1}명"


def extract_content(summary: str, fields: dict) -> str:
    """일정 내용. 설명 '내용:' 우선, 없으면 제목 '[ ]' 안, 그것도 없으면 제목 전체."""
    if fields.get("내용"):
        return fields["내용"]
    if summary and "[" in summary and "]" in summary:
        return summary[summary.index("[") + 1 : summary.index("]")].strip()
    return (summary or "").strip()


# --------------------------------------------------------------------------- #
# 장소 약칭
# --------------------------------------------------------------------------- #
def abbreviate_location(loc: str, overrides: dict) -> str:
    if not loc:
        return ""
    loc = loc.strip()
    if loc in overrides:
        return overrides[loc]

    # 경찰서: 광역시/도 접두 제거 + '경찰서' -> '서'
    if "경찰서" in loc:
        base = loc.replace("경찰서", "")
        for m in METRO:
            if base.startswith(m) and base != m:
                base = base[len(m):]
                break
        return base + "서"

    # 법원/검찰 지원·지청: 마지막 '...지원' / '...지청' 토큰만
    for marker in ("지원", "지청"):
        if marker in loc:
            for token in reversed(loc.split()):
                if token.endswith(marker):
                    return token

    # 법원 (광역시명 유지)
    if "고등법원" in loc:
        return loc.replace("고등법원", "고법")
    if "지방법원" in loc:
        return loc.replace("지방법원", "지법")

    # 검찰 (광역시명 유지)
    if "고등검찰청" in loc:
        return loc.replace("고등검찰청", "고검")
    if "지방검찰청" in loc:
        return loc.replace("지방검찰청", "지검")

    return loc


# --------------------------------------------------------------------------- #
# 출석/입회 표기
# --------------------------------------------------------------------------- #
def institution_verb(loc: str):
    """경찰/검찰 -> '입회', 법원 -> '출석', 그 외 -> None(표기 생략)."""
    if any(k in loc for k in ("경찰", "검찰", "지검", "지청")):
        return "입회"
    if any(k in loc for k in ("법원", "지원", "법정")):
        return "출석"
    return None


def _abbrev_lawyer(name: str, lawyers: dict) -> str:
    return lawyers.get(name, name) + "님"


def attendance_text(fields: dict, loc: str, lawyers: dict) -> str:
    """
    '> ' 뒤에 붙는 출석표기 문자열. 없으면 빈 문자열.
      - ▲지정자 있음        -> '김변님 입회' / '김변님 출석'
      - 필드 있으나 ▲없음   -> '미입회' / '미출석'
      - 출석변호사 줄 자체 없음(완전 미기재) -> '' (생략)
      - 경찰/검찰/법원이 아닌 장소 -> '' (생략)
    """
    verb = institution_verb(loc)
    if verb is None:
        return ""

    raw = fields.get("출석변호사")
    if raw is None:
        return ""  # 완전 미기재

    # '(담당: ...)' 괄호부분 제거 — 담당단일 뿐 실제 출석과 무관
    raw_wo = re.sub(r"\([^)]*\)", "", raw).strip()
    marked = re.findall(r"▲\s*([^\s,▲]+)", raw_wo)
    if not marked:
        return f"미{verb}"

    names = ", ".join(_abbrev_lawyer(n, lawyers) for n in marked)
    return f"{names} {verb}"


# --------------------------------------------------------------------------- #
# 한 건 포맷
# --------------------------------------------------------------------------- #
def format_timed(event: dict, fields: dict, cfg: Config) -> str:
    time = start_hhmm(event)
    content = extract_content(event.get("summary", ""), fields)
    loc_raw = event.get("location") or fields.get("장소", "")

    if has_case(fields):
        client = extract_client(event.get("summary", ""), fields)
        loc_abbr = abbreviate_location(loc_raw, cfg.locations)
        line = f"[{client}({loc_abbr})] {time} {content}"
        att = attendance_text(fields, loc_raw, cfg.lawyers)
        if att:
            line += f" > {att}"
        return line

    # 사건 없는 일정: 시간 내용(장소)
    if loc_raw:
        return f"{time} {content}({loc_raw})"
    return f"{time} {content}"


def format_deadline(event: dict, fields: dict, cfg: Config) -> str:
    content = extract_content(event.get("summary", ""), fields)
    if has_case(fields):
        client = extract_client(event.get("summary", ""), fields)
        loc_raw = event.get("location") or fields.get("장소", "")
        loc_abbr = abbreviate_location(loc_raw, cfg.locations)
        if loc_abbr:
            return f"[{client}({loc_abbr})] {content}"
        return f"[{client}] {content}"
    return content


# --------------------------------------------------------------------------- #
# 전체 메시지 조립
# --------------------------------------------------------------------------- #
def format_date(d: date) -> str:
    return f"{d.month}/{d.day}({WEEKDAYS[d.weekday()]})"


def build_message(events: list, day: date, cfg: Config) -> str:
    deadlines, timed = [], []
    for ev in events:
        fields = parse_description(ev.get("description", ""))
        if is_all_day(ev):
            deadlines.append(format_deadline(ev, fields, cfg))
        else:
            timed.append((start_hhmm(ev) or "", format_timed(ev, fields, cfg)))

    timed.sort(key=lambda x: x[0])

    header = f"📅 {format_date(day)} 오늘 일정"
    body = []
    if deadlines:
        body.append("[마감]")
        body.extend(deadlines)
        body.append("")  # 마감과 시간일정 사이 빈 줄
    body.extend(line for _, line in timed)

    if not deadlines and not timed:
        body.append("오늘 일정 없음")

    return header + "\n\n" + "\n".join(body).strip()
