"""
캘린더 원본 이벤트 → 법무법인 노바 표준 양식 변환 (프로젝트의 핵심 로직)

예시(2026-06-11 기준)의 형식을 따른다:

    260611 목요일

    10:00 [조장연] 변론기일 > 김정아
            김포시법원 법정

    14:00 [박설] 조사기일 > 김수인
            박설(010-7904-7204)

    11:00 [김봉주] 공판기일 > 미출석

    14:00 [엄태웅] 스마트접견 > 이돈호

규칙 요약:
  · 줄 형식    = "시간 [의뢰인] 기일종류 > 출석표기"  (대괄호는 의뢰인에만)
  · 출석표기   = 출석변호사 있으면 "> 실명"(약칭·'님' 없이 이름 그대로, 동사 없음).
                 출석변호사 미기재면 담당변호사가 1명일 때 그 담당변호사로 표기,
                 아니면 "> 미출석"(법원)/"> 미입회"(경찰·검찰).
                 (출석변호사 칸에 '미입회' 등을 명시하면 폴백 없이 그대로 미입회)
  · 장소 등    = 아랫줄 들여쓰기, 약칭 안 함(원본 그대로). 조사기일은 의뢰인(연락처)도.
  · 정식 기일  = 설명에 '사건번호'+'내용' 모두 보유 → 위 상세 양식
  · 그 외 일정 = 제목 그대로 + 담당(변호사)로 "> 실명"
  · 섹션 순서  = 맨 위 [기한](종일 사건 기한·불변기일 등) → [일정](그 외 일정) →
                 맨 아래 [휴무](휴가·반차·연차 등 부재 일정)

  · 수령·복사·등사 = 변호사가 아니라 담당직원이 가는 일정 → '> 담당직원 맨 앞 사람'

메시지 조립은 다섯 가지:
  · build_message                = 세 섹션을 한 통에 (기본 양식·오전 팀 알림)
  · build_section_message        = 오전 전체 알림용, 한 섹션만 한 통에 (하루 3통)
  · build_team_message           = 오후 팀 알림용, 팀 안에서 '### ○○ 변호사' 로 나누고
                                   변호사마다 세 섹션을 모두 표기
  · build_lawyer_message         = 오후 개인 알림용, 한 변호사의 세 섹션만
  · build_office_meeting_message = 오후 사무실 상담 알림용, 1006호·404호·인천 사무소의
                                   [회의] 방문상담만 사무실별 섹션으로
"""

import html
import os
import re
from datetime import date, datetime
from zoneinfo import ZoneInfo

import yaml

KST = ZoneInfo("Asia/Seoul")
WEEKDAYS = ["월", "화", "수", "목", "금", "토", "일"]
INDENT = "        "  # 아랫줄(장소 등) 들여쓰기

# 메시지 섹션 순서. 오전 알림은 이 셋을 각각 별도 메시지로 보내고,
# 팀별 알림은 변호사 섹션마다 이 셋을 모두 표기한다.
SECTIONS = ("기한", "일정", "휴무")

# 출석변호사 칸에 들어오지만 실제 변호사 출석이 아닌 상태값 → 출석자 아님(미출석/미입회 처리)
NON_ATTEND = {"미입회", "미출석", "불출석", "불참", "공판청취", "청취", "방청", "참관"}

# 선고기일 한정: 복대리·청취대리·선고청취대리·선고청취 등 대리출석 표기를 '청취대리'로 일원화.
LISTEN_PROXY_TERMS = ("선고청취대리", "청취대리", "선고청취", "복대리")

# 기록 수령·열람복사·등사 등 '변호사가 아니라 담당직원이 가는' 일정.
# 이런 일정은 담당변호사가 여럿 달려 있어도 실제로 가는 사람은 담당직원 맨 앞 사람이다.
STAFF_ERRAND_KW = ("수령", "복사", "등사")

# 휴가·반차·연차 등 부재(휴무) 일정 → 맨 아래 [휴무] 섹션에 따로 모은다.
# ('반차'가 '반반차'·'오전반차'·'오후반차'를 모두 포함하므로 별도 추가 불필요)
LEAVE_KEYWORDS = ("휴가", "반차", "휴무", "연차")

# 상담/미팅 의뢰인 전화번호, 접견 기관(구치소·교도소) 추출용 패턴
PHONE_RE = re.compile(r"\d{2,4}-\d{3,4}-\d{4}")
DETENTION_RE = re.compile(r"[가-힣A-Za-z0-9]+(?:교도소|구치소)")

# 원문자(①②③ …) → 일반 숫자
_CIRCLED = {chr(0x2460 + i): str(i + 1) for i in range(20)}


def _normalize(s: str) -> str:
    """발송 직전 문자 정리 — 원문자(①)를 숫자로, 구글 캘린더가 넘겨주는 HTML 엔티티를
    사람이 읽는 글자로(&amp;→&, &gt;→>). 제목에 '&'가 든 일정에서 필요하다."""
    return html.unescape("".join(_CIRCLED.get(ch, ch) for ch in s))


def _normalize_team(v):
    """teams.yaml 팀 항목 정규화 → {'변호사': [...], '수습': [...], '태그': bool}.
    구형(list) 값은 {'변호사': v, '수습': [], '태그': True} 로 해석(하위호환)."""
    if isinstance(v, list):
        return {"변호사": v, "수습": [], "태그": True}
    return {
        "변호사": (v or {}).get("변호사") or [],
        "수습": (v or {}).get("수습") or [],
        "태그": bool((v or {}).get("태그")),
    }


def _normalize_staff(v):
    """staff.yaml 한 변호사의 값 → 담당직원 이름 리스트(순서 유지, 중복 제거).
    허용 형태: {'주담당': '임지혜', '부담당': '최수빈'} / {'담당직원': [...]} / ['임지혜', ...]"""
    if v is None:
        return []
    raw = [v] if isinstance(v, str) else (v if isinstance(v, list) else list(v.values()))
    names = []
    for item in raw:
        for n in item if isinstance(item, list) else [item]:
            n = str(n).strip()
            if n and n not in names:
                names.append(n)
    return names


class Config:
    """장소 약칭 예외표·팀별 변호사 명단·변호사별 담당직원 명단 묶음."""

    def __init__(self, locations: dict, teams: dict = None, staff: dict = None):
        self.locations = locations or {}
        # 팀명 -> {'변호사': 정변호사, '수습': 수습변호사, '태그': 담당직원 태그 매칭 여부}
        self.teams = {t: _normalize_team(v) for t, v in (teams or {}).items()}
        # 변호사명 -> [담당직원…]  (팀별 알림의 변호사별 [휴무] 배정에 사용)
        self.staff = {k: _normalize_staff(v) for k, v in (staff or {}).items()}


def load_config(config_dir: str) -> Config:
    def _load(name, required=True):
        path = os.path.join(config_dir, name)
        if not required and not os.path.exists(path):
            return {}
        with open(path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}

    return Config(
        _load("locations.yaml"),
        _load("teams.yaml", required=False),
        _load("staff.yaml", required=False),
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
    """일정이 해당 팀의 알림에 포함되는지. (v1.13.0: 태그 기준 → 담당변호사 소속 기준)

    ① 태그: '태그: true' 팀(상담지원팀)만 담당직원/담당(직원)의 팀 태그로 매칭.
       송무팀 태그(#송무n팀)는 Lawware에서 삭제 예정 + 팀 재편 후 잔존 태그가
       오분류를 유발할 수 있어 사용하지 않는다. (teams 미전달·미등록 팀은 구형
       동작대로 태그 매칭만 유지)
    ② 담당변호사 소속: 담당변호사(정식 기일)/담당(변호사)(그 외 일정)의 정변호사
       소속 팀 — 정변호사가 하나도 없을 때만 수습 매핑 폴백. 서로 다른 팀 변호사가
       함께 담당이면 양쪽 팀 모두 포함.
    ③ 교차출석 팔로우: 다른 팀 사건이라도 출석변호사(미기재 시 담당 단독 폴백,
       그 외 일정은 담당(변호사))가 이 팀 정변호사면 포함. (수습은 직접 출석 안 함)
    ④ 휴무: 휴가·연차 등은 담당변호사 필드가 없으므로 제목에 팀 소속(정+수습)
       이름이 있으면 포함."""
    fields = parse_description(event.get("description", ""))
    cfg = (teams or {}).get(team)

    # ① 태그 — 미등록 팀(구형 호출)도 태그 매칭만은 유지
    if cfg is None or cfg["태그"]:
        staff = f"{fields.get('담당직원', '')} {fields.get('담당(직원)', '')}"
        if team in staff:
            return True
    if cfg is None:
        return False

    # ② 담당변호사 소속 팀 판정
    if team in _teams_of(_responsible_names(fields), teams):
        return True

    # ③ 교차출석 팔로우 — 출석변호사(담당 단독 폴백 포함). 없으면 담당(변호사).
    attendees = _gijil_attendees(fields) or _attendee_names(fields.get("담당(변호사)")) or []
    if any(n in cfg["변호사"] for n in attendees):
        return True

    # ④ 휴무 — 제목의 이름으로 판별
    if is_leave(event):
        title = event.get("summary") or ""
        return any(n in title for n in cfg["변호사"] + cfg["수습"])
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


def is_staff_errand(event: dict, fields: dict) -> bool:
    """기록 수령·열람복사·등사 등 담당직원이 대신 가는 일정인지(제목·내용 키워드)."""
    text = f"{event.get('summary') or ''} {fields.get('내용', '')}"
    return any(k in text for k in STAFF_ERRAND_KW)


def _staff_names(fields: dict) -> list:
    """담당직원/담당(직원) 필드의 사람 이름들(팀 태그 '#…' 은 제외, 순서 유지)."""
    out = []
    for key in ("담당직원", "담당(직원)"):
        for name in re.split(r"[,\s]+", fields.get(key) or ""):
            name = name.strip()
            if name and not name.startswith("#") and name not in out:
                out.append(name)
    return out


def _staff_attendee(fields: dict):
    """담당직원 명단의 맨 앞 사람. 없으면 None.
    수령·복사·등사 일정에서 실제로 가는 직원으로 본다."""
    names = _staff_names(fields)
    return names[0] if names else None


_DAMDANG_PAREN_RE = re.compile(r"\(담당:\s*([^)]*)\)")


def _responsible_names(fields):
    """일정의 담당변호사 실명 리스트(팀 분류용).
    ① 정식 기일의 '담당변호사' 필드 → ② 그 외 일정의 '담당(변호사)' 필드
    → ③ 폴백: 독립 필드 없이 '출석변호사: ▲김정아 (담당: 김정아,김성호)' 처럼
      출석변호사 칸 괄호에만 담당이 적힌 실데이터 형태."""
    for key in ("담당변호사", "담당(변호사)"):
        names = _attendee_names(fields.get(key))
        if names:
            return names
    m = _DAMDANG_PAREN_RE.search(fields.get("출석변호사") or "")
    return (_attendee_names(m.group(1)) or []) if m else []


def _teams_of(names, teams):
    """담당변호사 이름들 → 소속 팀 집합. 정변호사('변호사') 매핑 우선,
    정변호사가 하나도 없을 때만 수습 매핑 폴백. 복수 팀이면 모두 반환."""
    senior = {t for t, c in teams.items() if any(n in c["변호사"] for n in names)}
    if senior:
        return senior
    return {t for t, c in teams.items() if any(n in c["수습"] for n in names)}


def _songmu_roster(teams: dict) -> set:
    """태그 매칭 팀(상담지원팀)을 뺀 송무팀들의 변호사+수습 전체 명단."""
    names = set()
    for tc in (teams or {}).values():
        if not tc["태그"]:
            names.update(tc["변호사"])
            names.update(tc["수습"])
    return names


def event_in_team_by_staff(event: dict, team: str, cfg) -> bool:
    """담당변호사가 송무팀 명단 밖(예: 이돈호 대표변호사 단독)인 사건을
    '담당직원 소속팀'으로 배정하는 폴백. (v1.18.0)

    · 담당변호사·출석변호사 기준으로 어느 송무팀에도 안 잡히는 사건만 대상
      (변호사 기준 매핑이 항상 우선 — 다른 팀 사건이 직원 때문에 새지 않게).
    · 담당직원(사람 이름, '#' 태그 제외) 중 한 명이라도 이 팀 변호사의
      담당직원(staff.yaml)이면 포함. 팀 알림에서는 '### 기타' 섹션에 실린다.
    · 휴무 일정은 제외(직원 휴무는 staff.yaml 로 변호사 섹션에 이미 배정된다)."""
    if is_leave(event):
        return False
    fields = parse_description(event.get("description", ""))
    resp = _responsible_names(fields)
    if not resp:
        return False  # 변호사 없는 일정(운영팀 자체 일정 등)은 종전대로 미포함
    involved = set(resp) | set(_gijil_attendees(fields) or []) \
        | set(_attendee_names(fields.get("담당(변호사)")) or [])
    if involved & _songmu_roster(cfg.teams):
        return False  # 송무팀 변호사가 담당·출석이면 변호사 기준 매핑에 맡긴다
    team_staff = {s for n in team_sections(team, cfg) for s in cfg.staff.get(n, [])}
    return bool(set(_staff_names(fields)) & team_staff)


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


def _format_attendees(names) -> str:
    """출석자 표기: 실명(또는 '청취대리' 등 라벨) 그대로, 약칭·존칭 없이."""
    return ", ".join(names)


def _visit_number_sub(fields: dict, desc: str = ""):
    """접견 예약번호가 있으면 '접견번호 : 원문' 한 줄로(없으면 None).
    ① 구조화된 필드: 키에 '접견'+'번호'가 든 'key: value'('스마트접견예약번호' 등 변형 포함).
    ② 콜론이 없어 필드로 안 잡히는 경우('접견번호 007504'처럼 띄어쓰기): 설명 본문에서
       '접견'·'번호'가 함께 든 줄을 찾아 그 뒤의 번호(숫자/영숫자)를 직접 인식.
    ③ 라벨이 아예 없는 경우: 접견 일정 설명에 숫자만 달랑 적힌 줄('004627')은
       접견번호로 본다 — 라벨이 윗줄에만 있는 '스마트접견번호↵000074' 형태 포함.
       (전화번호는 하이픈, 사건번호는 'key:' 꼴이라 이 규칙에 안 걸린다)"""
    for key, val in fields.items():
        if "접견" in key and "번호" in key and val.strip():
            return f"접견번호 : {val.strip()}"
    for line in (desc or "").splitlines():
        if "접견" in line and "번호" in line:
            m = re.search(r"번호\s*[:\-]?\s*([0-9A-Za-z\-]+)", line)
            if m:
                return f"접견번호 : {m.group(1)}"
    for line in (desc or "").splitlines():
        m = re.fullmatch(r"\s*(\d{3,})\s*", line)
        if m:
            return f"접견번호 : {m.group(1)}"
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
    """'[회의] (구분) [의뢰인]내용' → '[의뢰인] 내용 > 담당변호사' + 장소·전화 아랫줄."""
    s = (event.get("summary") or "").strip()
    s = s[len("[회의]"):].strip() if s.startswith("[회의]") else s
    s = re.sub(r"^\([^)]*\)\s*", "", s)  # 선두 '(구분)' 라벨 제거(장소는 '구분' 필드에서)
    m = re.match(r"\[([^\]]*)\]\s*(.*)", s)  # 선두 '[의뢰인]' 추출
    client, content = (m.group(1).strip(), m.group(2).strip()) if m else ("", s)

    names = _attendee_names(fields.get("담당(변호사)"))
    att = " > " + _format_attendees(names) if names else ""
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
    att = " > " + _format_attendees(names) if names else ""

    subs = []
    if place:
        subs.append(cfg.locations.get(place, place))
    visit_no = _visit_number_sub(fields, desc)  # 접견 예약번호(있으면 장소 아래)
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
    # 기록 수령·열람복사·등사 등은 담당변호사가 여럿이어도 실제로는 직원이 간다
    # → 출석표기를 담당직원 맨 앞 사람으로 대체(담당직원이 없으면 평소대로).
    errand = _staff_attendee(fields) if is_staff_errand(event, fields) else None

    if is_full_gijil(fields):
        client = extract_client(event.get("summary", ""), fields)
        content = fields["내용"]
        gtype = gijil_type(content)
        verb = verb_for_content(content)

        names = _normalize_listen_proxy(_gijil_attendees(fields), gtype)
        if errand:
            att = f" > {errand}"
        elif names:
            att = " > " + _format_attendees(names)
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
    if errand:
        att = f" > {errand}"
    else:
        att = " > " + _format_attendees(names) if names else ""
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


def format_header_weekend_lead(lead: str, d: date) -> str:
    """금요일 저녁 토·일·월 묶음 알림의 '일자별' 머리말.
    예: '📅 [송무1팀] 토요일 일정(260815)', '📅 이돈호 변호사 토요일 일정(260815)'.
    (요일은 풀네임, 괄호엔 날짜만)"""
    return f"📅 {lead} {WEEKDAYS[d.weekday()]}요일 일정({d.strftime('%y%m%d')})"


def format_header_weekend(team: str, d: date) -> str:
    """금요일 저녁 팀 묶음 알림의 '일자별' 머리말. 예: '📅 [송무1팀] 토요일 일정(260815)'."""
    return format_header_weekend_lead(f"[{team}]", d)


def _emit(body, line, subs):
    body.append(line)
    for s in subs:
        body.append(INDENT + s)
    body.append("")  # 일정 블록 사이 빈 줄


def _rstrip_blank(lines: list) -> list:
    while lines and not lines[-1].strip():
        lines.pop()
    return lines


def section_bodies(events: list, cfg: Config) -> dict:
    """이벤트 목록 → {'기한': [줄…], '일정': [줄…], '휴무': [줄…]}.
    각 값은 라벨('[기한]') 없이 본문 줄만 담으며, 해당 섹션이 비면 빈 리스트."""
    deadlines, allday_other, timed, leaves = [], [], [], []
    for ev in events:
        fields = parse_description(ev.get("description", ""))
        summary = (ev.get("summary") or "").strip()
        if is_leave(ev):  # 휴가·반차·연차 등 → [휴무]
            leaves.append(summary)
        elif is_all_day(ev):
            if is_full_gijil(fields):  # 정식 기일의 종일 항목(제출기한·불변기일 등)
                deadlines.append(format_deadline(ev, fields, cfg))
            else:
                allday_other.append(summary)
        else:
            line, subs = format_timed(ev, fields, cfg)
            timed.append((start_hhmm(ev) or "", line, subs))

    timed.sort(key=lambda x: x[0])

    out = {name: [] for name in SECTIONS}
    for line, subs in deadlines:
        _emit(out["기한"], line, subs)
    if allday_other:  # 그 외 종일 일정을 시간 일정보다 위에
        out["일정"].extend(allday_other)
        out["일정"].append("")
    for _, line, subs in timed:  # 시간 있는 일정(시간순)
        _emit(out["일정"], line, subs)
    out["휴무"].extend(leaves)
    return {name: _rstrip_blank(lines) for name, lines in out.items()}


def _wrap(head: str, text: str, mention: bool, inline: bool) -> str:
    """머리말 + 본문 조립. inline=True면 '@everyone'을 머리말 끝에 붙인다."""
    if mention and inline:  # 오전: '📅 … 월요일 [일정] @everyone' + 빈 줄 + 본문
        return _normalize(f"{head} @everyone\n\n{text}")
    if mention:  # 팀별/익일: 머리말 아랫줄에 '@everyone' + 빈 줄 + 본문
        return _normalize(f"{head}\n@everyone\n\n{text}")
    return _normalize(f"{head}\n\n{text}")


def build_message(events: list, day: date, cfg: Config, lead: str = None, head: str = None,
                  mention: bool = False, include_deadlines: bool = True) -> str:
    """[기한]/[일정]/[휴무] 세 섹션을 한 메시지에 담는 기본 양식(내용 있는 섹션만)."""
    sec = section_bodies(events, cfg)
    body = []
    for name in SECTIONS:
        # include_deadlines=False면 [기한] 섹션을 통째로 생략
        if not sec[name] or (name == "기한" and not include_deadlines):
            continue
        body.append(f"[{name}]")
        body.extend(sec[name])
        body.append("")

    text = "\n".join(body).strip() or "일정 없음"
    # head 직접 지정(금요일 묶음의 일자별 머리말 등) 우선, 없으면 lead/기본 머리말.
    inline = head is None and lead is None
    if head is None:
        head = format_header_lead(lead, day) if lead else format_header(day)
    return _wrap(head, text, mention, inline)


def build_section_message(events: list, day: date, cfg: Config, section: str,
                          lead: str = None, mention: bool = False) -> str:
    """오전 알림 분할용 — [기한]/[일정]/[휴무] 중 한 섹션만 담은 메시지.
    머리말은 '📅 260810 월요일 [기한]' 형태이고, 해당 섹션이 비면 본문은 '없음'."""
    lines = section_bodies(events, cfg)[section]
    text = "\n".join(lines).strip() or "없음"
    head = format_header_lead(lead, day) if lead else format_header(day)
    return _wrap(f"{head} [{section}]", text, mention, inline=True)


# --------------------------------------------------------------------------- #
# 팀별 알림 — 팀 안에서 변호사별로 다시 나눈 양식
# --------------------------------------------------------------------------- #
def team_sections(team: str, cfg: Config) -> list:
    """팀 알림에 실을 변호사 섹션 순서 — 정변호사 먼저, 그다음 수습변호사."""
    tc = cfg.teams.get(team) or {}
    return list(tc.get("변호사") or []) + list(tc.get("수습") or [])


def format_lawyer_head(name: str, day: date, day_label: str = None) -> str:
    """팀 알림 안의 변호사 섹션 머리말. Discord 에서 '#'은 대제목이라 너무 커서
    가장 작은 제목인 '###' 을 쓴다. 예: '### 천기섭 변호사 내일 일정(260810, 월)'.
    day_label 이 없으면 이름만."""
    if not day_label:
        return f"### {name} 변호사"
    return f"### {name} 변호사 {day_label}({day.strftime('%y%m%d')}, {WEEKDAYS[day.weekday()]})"


def lawyer_owners(event: dict, names: list, cfg: Config) -> set:
    """이 일정을 실어야 할 변호사들(names 중). 해당 없으면 빈 집합.

    · 휴무: 제목에 이름이 있는 변호사 본인 + 그 이름이 staff.yaml 담당직원인 변호사.
      (한 직원이 여러 변호사의 담당이면 그 변호사들 섹션에 모두 실린다)
    · 그 외: 담당변호사 + 출석변호사(다른 팀 사건의 교차출석도 자기 섹션에 실림).
      공동담당이면 담당 변호사 섹션 모두에 실린다."""
    if is_leave(event):
        title = event.get("summary") or ""
        return {
            n for n in names
            if n in title or any(s in title for s in cfg.staff.get(n, []))
        }
    fields = parse_description(event.get("description", ""))
    who = set(_responsible_names(fields))
    who |= set(_gijil_attendees(fields) or _attendee_names(fields.get("담당(변호사)")) or [])
    return {n for n in names if n in who}


def team_events(events: list, cfg: Config, team: str) -> list:
    """그 팀 알림에 실리는 일정만 추린다(변호사 섹션 대상 + 팀 판정 '기타' 일정
    + 담당직원 소속팀 폴백). 오전 팀 알림(build_message 한 통 발송)의 입력으로도 쓴다."""
    names = team_sections(team, cfg)
    return [
        ev for ev in events
        if lawyer_owners(ev, names, cfg) or event_in_team(ev, team, cfg.teams)
        or event_in_team_by_staff(ev, team, cfg)
    ]


def team_event_count(events: list, cfg: Config, team: str) -> int:
    """그 팀 알림에 실제로 실리는 일정 수(로그용). 변호사 섹션 + '기타' 합계이며,
    공동담당으로 여러 섹션에 중복 표시되는 일정도 1건으로 센다."""
    return len(team_events(events, cfg, team))


def _lawyer_body(events: list, cfg: Config) -> str:
    """변호사 한 명 분량의 [기한]/[일정]/[휴무] 세 칸. 비어 있으면 '없음'을 적는다
    (그 변호사에게 정말 아무것도 없다는 것을 눈으로 확인할 수 있게)."""
    sec = section_bodies(events, cfg)
    out = []
    for name in SECTIONS:
        out.append(f"[{name}]")
        out.extend(sec[name] or ["없음"])
        out.append("")
    return "\n".join(out).rstrip()


def lawyer_events(events: list, cfg: Config, lawyer: str) -> list:
    """그 변호사 몫으로 잡히는 일정만 추린다(본인 담당·출석 + 담당직원 휴무)."""
    return [ev for ev in events if lawyer_owners(ev, [lawyer], cfg)]


def build_lawyer_message(events: list, day: date, cfg: Config, lawyer: str,
                         day_label: str = None, head: str = None,
                         mention: bool = False) -> str:
    """변호사 한 명의 개인 알림 — 팀과 별개로 본인 일정만 담은 메시지.
    예: '📅 이돈호 변호사 내일 일정(260810, 월)' + [기한]/[일정]/[휴무].
    head 를 주면(금요일 묶음의 일자별 머리말 등) 그 머리말을 그대로 쓴다."""
    if head is None:
        lead = f"{lawyer} 변호사" + (f" {day_label}" if day_label else "")
        head = format_header_lead(lead, day)
    text = _lawyer_body(lawyer_events(events, cfg, lawyer), cfg)
    return _wrap(head, text, mention, inline=False)


def build_team_message(events: list, day: date, cfg: Config, team: str, lead: str = None,
                       head: str = None, mention: bool = False, day_label: str = None,
                       skip_empty: bool = False) -> str:
    """팀 알림 — 팀 안에서 변호사별 '# ○○ 변호사' 섹션으로 나눈 메시지.

    어느 변호사에도 배정되지 않지만 팀 알림 대상인 일정(공용 일정 등)은 맨 아래
    '# 기타' 섹션에 모은다(있을 때만). skip_empty=True면 일정이 하나도 없는 변호사는
    건너뛴다(금요일 저녁 토·일·월 묶음처럼 3일치를 이어붙일 때 길이를 줄이기 위함)."""
    names = team_sections(team, cfg)
    buckets = {n: [] for n in names}
    others = []
    for ev in events:
        owners = lawyer_owners(ev, names, cfg)
        if owners:
            for n in owners:
                buckets[n].append(ev)
        elif event_in_team(ev, team, cfg.teams) or event_in_team_by_staff(ev, team, cfg):
            others.append(ev)

    blocks = [
        format_lawyer_head(n, day, day_label) + "\n" + _lawyer_body(buckets[n], cfg)
        for n in names
        if not (skip_empty and not buckets[n])
    ]
    if others:
        blocks.append("### 기타\n" + _lawyer_body(others, cfg))

    text = "\n\n".join(blocks).strip() or "일정 없음"
    if head is None:
        head = format_header_lead(lead, day) if lead else format_header(day)
    return _wrap(head, text, mention, inline=False)


# --------------------------------------------------------------------------- #
# 사무실 상담 알림 — 1006호·404호·인천 사무소의 [회의] 방문상담만 모은 메시지
# --------------------------------------------------------------------------- #
# locations.yaml 정규화를 거친 자사 사무실 이름(별칭 추가·수정은 locations.yaml 에서).
OFFICE_MEETING_PLACES = ("서울 1006호", "서울 404호", "인천사무소")


def meeting_place(event: dict, cfg: Config) -> str:
    """상담([회의]) 일정의 장소를 locations.yaml 예외표로 정규화해 돌려준다.
    (format_meeting 의 장소 추출 순서와 동일: location → 장소 → 구분)"""
    fields = parse_description(event.get("description", ""))
    loc = (event.get("location") or fields.get("장소") or fields.get("구분") or "").strip()
    return cfg.locations.get(loc, loc)


def office_meeting_events(events: list, cfg: Config) -> list:
    """자사 사무실(1006호·404호·인천)에서 잡힌 [회의] 방문상담 일정만 추린다."""
    return [
        ev for ev in events
        if is_meeting(ev) and meeting_place(ev, cfg) in OFFICE_MEETING_PLACES
    ]


def build_office_meeting_message(events: list, day: date, cfg: Config,
                                 day_label: str = None, head: str = None,
                                 mention: bool = False) -> str:
    """사무실 상담 알림 — '### 서울 1006호' 처럼 사무실별 섹션으로 나눠 시간순 표기.
    상담이 없는 사무실도 '없음'으로 보여준다(그 방이 빈다는 것을 눈으로 확인할 수 있게).
    head 를 주면(금요일 묶음의 일자별 머리말 등) 그 머리말을 그대로 쓴다."""
    buckets = {p: [] for p in OFFICE_MEETING_PLACES}
    for ev in office_meeting_events(events, cfg):
        buckets[meeting_place(ev, cfg)].append(ev)

    blocks = []
    for place, evs in buckets.items():
        timed = []
        for ev in evs:
            fields = parse_description(ev.get("description", ""))
            line, subs = format_timed(ev, fields, cfg)
            # 섹션 제목이 곧 사무실 이름이므로 같은 장소 아랫줄은 중복 → 뺀다.
            subs = [s for s in subs if s != place]
            timed.append((start_hhmm(ev) or "", line, subs))
        timed.sort(key=lambda x: x[0])
        lines = []
        for _, line, subs in timed:
            _emit(lines, line, subs)
        body = "\n".join(_rstrip_blank(lines)) or "없음"
        blocks.append(f"### {place}\n{body}")

    text = "\n\n".join(blocks)
    if head is None:
        lead = "[상담]" + (f" {day_label}" if day_label else "")
        head = format_header_lead(lead, day)
    return _wrap(head, text, mention, inline=False)
