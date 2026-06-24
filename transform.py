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
  · 출석표기   = 출석변호사 있으면 "> 약칭님"(동사 없음). 출석변호사 미기재면 담당변호사가
                 1명일 때 그 담당변호사로 표기, 아니면 "> 미출석"(법원)/"> 미입회"(경찰·검찰).
                 (출석변호사 칸에 '미입회' 등을 명시하면 폴백 없이 그대로 미입회)
  · 장소 등    = 아랫줄 들여쓰기, 약칭 안 함(원본 그대로). 조사기일은 의뢰인(연락처)도.
  · 정식 기일  = 설명에 '사건번호'+'내용' 모두 보유 → 위 상세 양식
  · 그 외 일정 = 제목 그대로 + 담당(변호사)로 "> 약칭님"
  · 섹션 순서  = 맨 위 [기한](종일 사건 기한·불변기일 등) → [일정](그 외 일정) →
                 맨 아래 [휴무](휴가·반차·연차 등 부재 일정)
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

# 선고기일 한정: 복대리·청취대리·선고청취대리·선고청취 등 대리출석 표기를 '청취대리'로 일원화.
LISTEN_PROXY_TERMS = ("선고청취대리", "청취대리", "선고청취", "복대리")
# 사람이 아니라 출석방식 라벨이므로 '님'을 붙이지 않는 출석표기.
NO_HONORIFIC = {"청취대리"}

# 휴가·반차·연차 등 부재(휴무) 일정 → 맨 아래 [휴무] 섹션에 따로 모은다.
# ('반차'가 '반반차'·'오전반차'·'오후반차'를 모두 포함하므로 별도 추가 불필요)
LEAVE_KEYWORDS = ("휴가", "반차", "휴무", "연차")

# 상담/미팅 의뢰인 전화번호, 접견 기관(구치소·교도소) 추출용 패턴
PHONE_RE = re.compile(r"\d{2,4}-\d{3,4}-\d{4}")
DETENTION_RE = re.compile(r"[가-힣A-Za-z0-9]+(?:교도소|구치소)")

# 원문자(①②③ …) → 일반 숫자
_CIRCLED = {chr(0x2460 + i): str(i + 1) for i in range(20)}


def _normalize(s: str) -> str:
    return "".join(_CIRCLED.get(ch, ch) for ch in s)


class Config:
    """변호사 약칭표·장소 예외표·팀별 출석변호사 명단 묶음."""

    def __init__(self, lawyers: dict, locations: dict, teams: dict = None):
        self.lawyers = lawyers or {}
        self.locations = locations or {}
        self.teams = teams or {}  # 팀명 -> 소속 출석변호사 명단(타팀 대신출석 팔로우용)


def load_config(config_dir: str) -> Config:
    def _load(name, required=True):
        path = os.path.join(config_dir, name)
        if not required and not os.path.exists(path):
            return {}
        with open(path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}

    return Config(
        _load("lawyers.yaml"),
        _load("locations.yaml"),
        _load("teams.yaml", required=False),
    )


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


def is_leave(event: dict) -> bool:
    """휴가·반차·반반차·휴무·연차 등 부재 일정인지(제목 키워드 기준).
    종일/시간 여부와 무관하게 제목에 키워드가 있으면 [휴무]로 분류한다."""
    title = event.get("summary") or ""
    return any(k in title for k in LEAVE_KEYWORDS)


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


def event_in_team(event: dict, team: str, teams: dict = None) -> bool:
    """일정이 해당 팀의 알림에 포함되는지.

    ① 담당직원/담당(직원) 필드에 팀 태그(예 '송무1팀')가 있으면 포함(그 팀의 사건).
    ② teams(팀명→소속 변호사 명단)가 주어지면, 다른 팀 사건이라도 그 일정의
       출석변호사(없으면 담당(변호사))가 이 팀 소속이면 포함한다. 다른 팀 변호사가
       대신 출석하는 경우, 그 변호사 소속 팀에서도 일정을 팔로우하기 위함."""
    fields = parse_description(event.get("description", ""))
    text = f"{fields.get('담당직원', '')} {fields.get('담당(직원)', '')}"
    if team in text:
        return True
    if teams:
        roster = teams.get(team) or []
        # 출석변호사(담당변호사 단독 폴백 포함). 없으면 그 외 일정의 담당(변호사).
        names = _gijil_attendees(fields)
        if not names:
            names = _attendee_names(fields.get("담당(변호사)")) or []
        if any(n in roster for n in names):
            return True
    return False


def gijil_type(content: str) -> str:
    """내용에서 기일종류만. '변론기일(법정 10:00)' -> '변론기일'.
    조사류(고소인조사/피의자조사/피고소인 조사/대질 등)는 '조사기일'로 통일."""
    t = re.split(r"[(\[]", content, 1)[0].strip()
    if "조사" in t:
        return "조사기일"
    return t


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


def _gijil_attendees(fields):
    """정식 기일의 실제 출석변호사 실명 리스트.
    · '결과'가 미출석·미입회 등 불출석 상태값이면, '출석변호사' 칸에 (출석 예정이던)
      이름이 적혀 있어도 출석자 없음으로 본다(직원이 결과를 '미출석'으로 확정한 경우).
    · '출석변호사'에 이름이 있으면 그 이름들.
    · '출석변호사'가 미기재(필드 없음/공백)이고 '담당변호사'가 1명뿐이면, 그 담당변호사가
      출석하는 것으로 간주(담당변호사 단독 폴백).
    · '출석변호사' 칸에 '미입회'·'미출석' 등이 명시되면 폴백하지 않고 빈 리스트(출석자 없음).
      (담당변호사가 2명 이상일 때도 누가 출석인지 불명확하므로 폴백하지 않음.)"""
    if (fields.get("결과") or "").strip() in NON_ATTEND:
        return []
    raw = fields.get("출석변호사")
    names = _attendee_names(raw)
    if names:
        return names
    if raw is None or not str(raw).strip():  # 출석변호사 미기재
        solo = _attendee_names(fields.get("담당변호사"))
        if solo and len(solo) == 1:
            return solo
    return names or []


def _normalize_listen_proxy(names, gtype):
    """선고기일에 한해 복대리/청취대리/선고청취대리/선고청취 표기를 '청취대리'로 일원화.
    (다른 기일종류는 그대로 둔다.) 중복은 순서 유지하며 1건으로 정리."""
    if gtype != "선고기일":
        return names
    out = []
    for n in names:
        norm = "청취대리" if any(term in n for term in LISTEN_PROXY_TERMS) else n
        if norm not in out:
            out.append(norm)
    return out


def _format_attendees(names, lawyers) -> str:
    def one(n):
        label = lawyers.get(n, n)
        return label if n in NO_HONORIFIC else label + "님"  # 청취대리 등은 '님' 없이
    return ", ".join(one(n) for n in names)


def _visit_number_sub(fields: dict):
    """접견 예약번호가 있으면 '접견번호 : 원문' 한 줄로(없으면 None).
    실데이터 키는 '스마트접견예약번호' 등 변형이 있어, '접견'+'번호'가 모두 든
    필드 키를 폭넓게 인식한다(스마트접견·화상접견 공통)."""
    for key, val in fields.items():
        if "접견" in key and "번호" in key and val.strip():
            return f"접견번호 : {val.strip()}"
    return None


def _bigo_sub(fields: dict):
    """비고에 내용이 있으면 '비고 : 원문' 한 줄로(없으면 None). 필터 없이 그대로 노출하며,
    항상 맨 아랫줄에 둔다. (※ 비고 칸 내용이 그대로 알림에 나가므로 민감정보 입력 금지)"""
    raw = fields.get("비고", "").strip()
    return f"비고 : {raw}" if raw else None


def _location_sub(event: dict, fields: dict, cfg: "Config") -> str:
    """장소 아랫줄 텍스트. '내용'에 '화상장치'가 있으면(영상재판) 실제 장소 대신
    '영상재판'으로 대체. 키워드는 '내용' 끝에 '[일방 화상장치]'·'[주문 화상장치]' 등
    대괄호 꼬리표로 들어온다(장소/location 필드가 아님)."""
    if "화상장치" in fields.get("내용", ""):
        return "영상재판"
    raw = (event.get("location") or fields.get("장소", "")).strip()
    return cfg.locations.get(raw, raw)  # 예외표 있으면 치환, 없으면 원본 그대로


# --------------------------------------------------------------------------- #
# 상담/미팅·접견 (정식 기일이 아니지만 의뢰인·담당변호사가 있는 일정)
# --------------------------------------------------------------------------- #
def is_meeting(event: dict) -> bool:
    """'[회의]'로 시작하는 방문상담·대면미팅 등 회의성 일정."""
    return (event.get("summary") or "").lstrip().startswith("[회의]")


def is_visit(event: dict) -> bool:
    """제목에 '접견'이 들어가는 교정시설 접견 일정(화상/대면/스마트접견 등)."""
    return "접견" in (event.get("summary") or "")


def _meeting_phone(fields: dict, desc: str) -> str:
    """상담/미팅 의뢰인 전화. '의뢰인연락처' 필드 우선, 없으면 설명 본문의
    'key: value' 가 아닌 줄(맨 윗줄에 번호만 달랑 적힌 경우)에서 번호를 찾는다."""
    raw = fields.get("의뢰인연락처") or fields.get("의뢰인 연락처") or ""
    m = PHONE_RE.search(raw)
    if m:
        return m.group(0)
    for line in (desc or "").splitlines():
        if ":" in line:  # 구조화된 필드 줄(담당직원 등)은 의뢰인 번호가 아님
            continue
        m = PHONE_RE.search(line)
        if m:
            return m.group(0)
    return ""


def format_meeting(event: dict, fields: dict, cfg: Config, time: str):
    """'[회의] (구분) [의뢰인]내용' → '[의뢰인] 내용 > 담당변호사님' + 장소·전화 아랫줄."""
    s = (event.get("summary") or "").strip()
    s = s[len("[회의]"):].strip() if s.startswith("[회의]") else s
    s = re.sub(r"^\([^)]*\)\s*", "", s)  # 선두 '(구분)' 라벨 제거(장소는 '구분' 필드에서)
    m = re.match(r"\[([^\]]*)\]\s*(.*)", s)  # 선두 '[의뢰인]' 추출
    client, content = (m.group(1).strip(), m.group(2).strip()) if m else ("", s)

    names = _attendee_names(fields.get("담당(변호사)"))
    att = " > " + _format_attendees(names, cfg.lawyers) if names else ""
    head = f"[{client}] {content}" if client else content

    subs = []
    loc = (event.get("location") or fields.get("장소") or fields.get("구분") or "").strip()
    if loc:
        subs.append(cfg.locations.get(loc, loc))
    phone = _meeting_phone(fields, event.get("description", ""))
    if phone and client:
        subs.append(f"{client}({phone})")
    bigo = _bigo_sub(fields)  # 비고는 항상 맨 아랫줄
    if bigo:
        subs.append(bigo)
    return f"{time} {head}{att}".rstrip(), subs


def format_visit(event: dict, fields: dict, cfg: Config, time: str):
    """접견 일정 → 제목 그대로 + 담당변호사. 설명/제목에 구치소·교도소 이름이 있으면
    그 기관을 장소 아랫줄로 표기하고(제목 괄호와 중복되면 괄호는 제거), 없으면 생략.
    설명에 접견 예약번호(스마트접견예약번호 등)가 있으면 '접견번호 : …' 아랫줄을 덧붙인다."""
    title = (event.get("summary") or "").strip()
    desc = event.get("description", "") or ""
    m = DETENTION_RE.search(title) or DETENTION_RE.search(desc)
    place = m.group(0) if m else ""
    if place and f"({place})" in title:  # 제목의 '(서울남부교도소)' 중복 제거
        title = title.replace(f"({place})", "").strip()

    names = _attendee_names(fields.get("담당(변호사)"))
    att = " > " + _format_attendees(names, cfg.lawyers) if names else ""

    subs = []
    if place:
        subs.append(cfg.locations.get(place, place))
    visit_no = _visit_number_sub(fields)  # 접견 예약번호(있으면 장소 아래)
    if visit_no:
        subs.append(visit_no)
    bigo = _bigo_sub(fields)  # 비고는 항상 맨 아랫줄
    if bigo:
        subs.append(bigo)
    return f"{time} {title}{att}", subs


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

        names = _normalize_listen_proxy(_gijil_attendees(fields), gtype)
        if names:
            att = " > " + _format_attendees(names, cfg.lawyers)
        elif verb:
            att = f" > 미{verb}"
        else:
            att = ""

        line = f"{time} [{client}] {gtype}{att}"

        subs = []
        loc = _location_sub(event, fields, cfg)
        if loc:
            subs.append(loc)
        if verb == "입회":  # 조사기일 등 -> 의뢰인 연락처
            phone = fields.get("의뢰인 연락처", "").strip()
            if phone:
                subs.append(f"{client}({phone})")
        bigo = _bigo_sub(fields)  # 비고는 항상 맨 아랫줄
        if bigo:
            subs.append(bigo)
        return line, subs

    if is_meeting(event):  # [회의] 방문상담·대면미팅 → 의뢰인 머리말 + 장소·전화
        return format_meeting(event, fields, cfg, time)
    if is_visit(event):  # 접견 → 구치소·교도소 이름 있으면 장소로 표기
        return format_visit(event, fields, cfg, time)

    # 그 외 일정: 제목 그대로 + 담당(변호사)로 출석표기
    title = (event.get("summary") or "").strip()
    names = _attendee_names(fields.get("담당(변호사)"))
    att = " > " + _format_attendees(names, cfg.lawyers) if names else ""
    bigo = _bigo_sub(fields)
    return f"{time} {title}{att}", ([bigo] if bigo else [])


def format_deadline(event: dict, fields: dict, cfg: Config):
    """정식 기일인 종일 항목([기한] 섹션) -> (메인줄, [아랫줄들])."""
    client = extract_client(event.get("summary", ""), fields)
    gtype = gijil_type(fields["내용"])
    line = f"[{client}] {gtype}"
    subs = []
    loc = _location_sub(event, fields, cfg)
    if loc:
        subs.append(loc)
    bigo = _bigo_sub(fields)  # 장소/제출 성격 비고만 노출
    if bigo:
        subs.append(bigo)
    return line, subs


# --------------------------------------------------------------------------- #
# 전체 메시지 조립
# --------------------------------------------------------------------------- #
def format_header(d: date) -> str:
    return f"📅 {d.strftime('%y%m%d')} {WEEKDAYS[d.weekday()]}요일"


def format_header_lead(lead: str, d: date) -> str:
    """팀별/익일 알림용 한 줄 머리말. 예: '📅 [송무1팀] 내일 일정(260615, 월)'."""
    return f"📅 {lead}({d.strftime('%y%m%d')}, {WEEKDAYS[d.weekday()]})"


def format_header_weekend(team: str, d: date) -> str:
    """금요일 저녁 송무팀 묶음 알림의 '일자별' 머리말.
    예: '📅 [송무3팀] 토요일 일정(260627)'. (요일은 풀네임, 괄호엔 날짜만)"""
    return f"📅 [{team}] {WEEKDAYS[d.weekday()]}요일 일정({d.strftime('%y%m%d')})"


def _emit(body, line, subs):
    body.append(line)
    for s in subs:
        body.append(INDENT + s)
    body.append("")  # 일정 블록 사이 빈 줄


def build_message(events: list, day: date, cfg: Config, lead: str = None, head: str = None) -> str:
    deadlines, allday_other, timed, leaves = [], [], [], []
    for ev in events:
        fields = parse_description(ev.get("description", ""))
        summary = (ev.get("summary") or "").strip()
        if is_leave(ev):  # 휴가·반차·연차 등 → [휴무]
            leaves.append(summary)
        elif is_all_day(ev):
            if is_full_gijil(fields):
                deadlines.append(format_deadline(ev, fields, cfg))
            else:
                allday_other.append(summary)
        else:
            line, subs = format_timed(ev, fields, cfg)
            timed.append((start_hhmm(ev) or "", line, subs))

    timed.sort(key=lambda x: x[0])

    body = []
    # [기한]: 정식 기일의 종일 항목(제출기한·불변기일 등)을 맨 위로
    if deadlines:
        body.append("[기한]")
        for line, subs in deadlines:
            _emit(body, line, subs)
    # [일정]: 그 외 종일(연차 등 제외) + 시간 일정. 둘 중 하나라도 있으면 라벨을 붙인다.
    if allday_other or timed:
        body.append("[일정]")
        if allday_other:
            body.extend(allday_other)
            body.append("")  # 종일과 시간일정 사이 빈 줄
        for _, line, subs in timed:  # 시간 있는 일정(시간순)
            _emit(body, line, subs)
    # [휴무]: 휴가·반차·연차 등 부재 일정을 맨 아래에 모아 표기
    if leaves:
        body.append("[휴무]")
        body.extend(leaves)

    text = "\n".join(body).strip()
    if not text:
        text = "일정 없음"
    # head 직접 지정(금요일 묶음의 일자별 머리말 등) 우선, 없으면 lead/기본 머리말.
    if head is None:
        head = format_header_lead(lead, day) if lead else format_header(day)
    return _normalize(head + "\n\n" + text)
