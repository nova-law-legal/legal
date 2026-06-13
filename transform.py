"""
캘린더 원본 이벤트 → 법무법인 노바 표준 양식 변환 (프로젝트의 핵심 로직)

예시(2026-06-11 기준)의 형식을 따른다:

    260611 목요일

    10:00 [조장연] 변론기일 > 아변님
            김포시법원 법정

    14:00 [박설] 조사기일 > 수변님
            박설(010-7904-7204)

    11:00 [김봉주] 공판기일 > 미출석

    14:00 [엄태웅] 스마트접견 > 돈변님

규칙 요약:
  · 줄 형식    = "시간 [의뢰인] 기일종류 > 출석표기"  (대괄호는 의뢰인에만)
  · 출석표기   = 있으면 "> 약칭님"(동사 없음), 없으면 "> 미출석"(법원)/"> 미입회"(경찰·검찰)
  · 장소 등    = 아랫줄 들여쓰기, 약칭 안 함(원본 그대로). 조사기일은 의뢰인(연락처)도.
  · 정식 기일  = 설명에 '사건번호'+'내용' 모두 보유 → 위 상세 양식
  · 그 외 일정 = 제목 그대로 + 담당(변호사)로 "> 약칭님"
  · 종일 사건 마감(불변기일 등)은 [마감] 섹션
"""

import os
import re
from datetime import date, datetime
from zoneinfo import ZoneInfo

import yaml

KST = ZoneInfo("Asia/Seoul")
WEEKDAYS = ["월", "화", "수", "목", "금", "토", "일"]
INDENT = "        "  # 아랫줄(장소 등) 들여쓰기

# 출석변호사 칸에 들어오지만 실제 변호사 출석이 아닌 상태값 → 출석자 아님(미출석/미입회 처리)
NON_ATTEND = {"미입회", "미출석", "불출석", "불참", "공판청취", "청취", "방청", "참관"}

# 원문자(①②③ …) → 일반 숫자
_CIRCLED = {chr(0x2460 + i): str(i + 1) for i in range(20)}


def _normalize(s: str) -> str:
    return "".join(_CIRCLED.get(ch, ch) for ch in s)


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
    start = event.get("start", {})
    return "date" in start and "dateTime" not in start


def is_full_gijil(fields: dict) -> bool:
    """정식 기일(사건번호+내용 모두 보유)인지."""
    return bool(fields.get("사건번호") and fields.get("내용"))


def start_hhmm(event: dict):
    dt = event.get("start", {}).get("dateTime")
    if not dt:
        return None
    return datetime.fromisoformat(dt).astimezone(KST).strftime("%H:%M")


# --------------------------------------------------------------------------- #
# 필드 추출
# --------------------------------------------------------------------------- #
def _shorten_clients(name: str) -> str:
    if not name:
        return ""
    if "외" in name:
        return name
    parts = [p.strip() for p in name.split(",") if p.strip()]
    if len(parts) <= 1:
        return name
    return f"{parts[0]} 외 {len(parts) - 1}명"


def _strip_last_paren(v: str) -> str:
    """의뢰인 필드는 '표시명(표시명)' 형태로 들어온다(맨 끝 괄호가 표시명을 미러링).
    맨 끝 균형 괄호 한 겹만 제거 → 개인 '조장연(조장연)'→'조장연',
    법인 '더 주 주식회사(김주식)(더 주 주식회사(김주식))'→'더 주 주식회사(김주식)'."""
    v = v.strip()
    if not v.endswith(")"):
        return v
    depth = 0
    for i in range(len(v) - 1, -1, -1):
        if v[i] == ")":
            depth += 1
        elif v[i] == "(":
            depth -= 1
            if depth == 0:
                return v[:i].strip()
    return v


def extract_client(summary: str, fields: dict) -> str:
    """의뢰인명. 설명 '의뢰인:' 필드 우선, 없으면 제목 '[' 앞 텍스트."""
    v = fields.get("의뢰인", "").strip()
    if v:
        return _shorten_clients(_strip_last_paren(v))
    if summary and "[" in summary:
        return _shorten_clients(summary.split("[", 1)[0].strip())
    return ""


def gijil_type(content: str) -> str:
    """내용에서 기일종류만. '변론기일(법정 10:00)' -> '변론기일'."""
    return re.split(r"[(\[]", content, 1)[0].strip()


def verb_for_content(content: str):
    """미출석/미입회 동사 판별. 조사류 -> '입회', 재판류 -> '출석', 그 외 -> None."""
    if any(k in content for k in ("조사", "대질", "입회")):
        return "입회"
    if any(k in content for k in ("공판", "변론", "선고", "심문", "심리")):
        return "출석"
    return None


def _attendee_names(raw):
    """출석변호사/담당(변호사) 필드 → 변호사 실명 리스트.
    '(담당: ...)' 제거, '▲' 제거 후 쉼표/공백 분리. 필드 없으면 None."""
    if raw is None:
        return None
    raw_wo = re.sub(r"\([^)]*\)", "", raw).replace("▲", " ").strip()
    toks = [n for n in re.split(r"[,\s]+", raw_wo) if n]
    return [t for t in toks if t not in NON_ATTEND]  # 상태값(공판청취 등) 제외


def _format_attendees(names, lawyers) -> str:
    return ", ".join(lawyers.get(n, n) + "님" for n in names)


# --------------------------------------------------------------------------- #
# 한 건 포맷  ->  (메인줄, [아랫줄들])
# --------------------------------------------------------------------------- #
def format_timed(event: dict, fields: dict, cfg: Config):
    time = start_hhmm(event)

    if is_full_gijil(fields):
        client = extract_client(event.get("summary", ""), fields)
        content = fields["내용"]
        gtype = gijil_type(content)
        verb = verb_for_content(content)

        names = _attendee_names(fields.get("출석변호사"))
        if names:
            att = " > " + _format_attendees(names, cfg.lawyers)
        elif verb:
            att = f" > 미{verb}"
        else:
            att = ""

        line = f"{time} [{client}] {gtype}{att}"

        subs = []
        loc = (event.get("location") or fields.get("장소", "")).strip()
        loc = cfg.locations.get(loc, loc)  # 예외표 있으면 치환, 없으면 원본 그대로
        if loc:
            subs.append(loc)
        if verb == "입회":  # 조사기일 등 -> 의뢰인 연락처
            phone = fields.get("의뢰인 연락처", "").strip()
            if phone:
                subs.append(f"{client}({phone})")
        return line, subs

    # 그 외 일정: 제목 그대로 + 담당(변호사)로 출석표기
    title = (event.get("summary") or "").strip()
    names = _attendee_names(fields.get("담당(변호사)"))
    att = " > " + _format_attendees(names, cfg.lawyers) if names else ""
    return f"{time} {title}{att}", []


def format_deadline(event: dict, fields: dict, cfg: Config):
    """정식 기일인 종일 항목([마감] 섹션) -> (메인줄, [아랫줄들])."""
    client = extract_client(event.get("summary", ""), fields)
    gtype = gijil_type(fields["내용"])
    line = f"[{client}] {gtype}"
    subs = []
    loc = (event.get("location") or fields.get("장소", "")).strip()
    loc = cfg.locations.get(loc, loc)
    if loc:
        subs.append(loc)
    return line, subs


# --------------------------------------------------------------------------- #
# 전체 메시지 조립
# --------------------------------------------------------------------------- #
def format_header(d: date) -> str:
    return f"{d.strftime('%y%m%d')} {WEEKDAYS[d.weekday()]}요일"


def _emit(body, line, subs):
    body.append(line)
    for s in subs:
        body.append(INDENT + s)
    body.append("")  # 일정 블록 사이 빈 줄


def build_message(events: list, day: date, cfg: Config) -> str:
    deadlines, allday_other, timed = [], [], []
    for ev in events:
        fields = parse_description(ev.get("description", ""))
        if is_all_day(ev):
            if is_full_gijil(fields):
                deadlines.append(format_deadline(ev, fields, cfg))
            else:
                allday_other.append((ev.get("summary") or "").strip())
        else:
            line, subs = format_timed(ev, fields, cfg)
            timed.append((start_hhmm(ev) or "", line, subs))

    timed.sort(key=lambda x: x[0])

    body = []
    if deadlines:
        body.append("[마감]")
        for line, subs in deadlines:
            _emit(body, line, subs)
    for _, line, subs in timed:
        _emit(body, line, subs)
    for title in allday_other:
        body.append(title)

    text = "\n".join(body).strip()
    if not text:
        text = "일정 없음"
    return _normalize(format_header(day) + "\n\n" + text)
