"""
Google Calendar 읽기 (서비스 계정, 읽기 전용).

여러 계정 지원:
  서비스 계정은 '자기에게 공유된 캘린더'만 읽을 수 있으므로, 캘린더가 여러 구글
  계정에 흩어져 있으면 계정마다 키를 따로 줘야 한다. 환경변수에 번호 접미사로 짝을 맞춘다.

    GOOGLE_SERVICE_ACCOUNT_JSON      + GOOGLE_CALENDAR_ID       (1번 계정)
    GOOGLE_SERVICE_ACCOUNT_JSON_2    + GOOGLE_CALENDAR_ID_2     (2번 계정)
    ... _3, _4 ...
  (로컬은 GOOGLE_SERVICE_ACCOUNT_FILE{접미사} 로 키 '파일경로'를 줘도 된다.)
"""

import json
import os
import re
import sys
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

KST = ZoneInfo("Asia/Seoul")
SCOPES = ["https://www.googleapis.com/auth/calendar.readonly"]
SUFFIXES = ["", "_2", "_3", "_4", "_5"]


def _creds_info(suffix: str):
    """해당 계정의 서비스계정 자격증명 dict. 내용(JSON) 우선, 없으면 파일경로."""
    raw = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON" + suffix)
    if raw:
        return json.loads(raw)
    path = os.environ.get("GOOGLE_SERVICE_ACCOUNT_FILE" + suffix)
    if path:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return None


def _calendar_ids(suffix: str):
    raw = os.environ.get("GOOGLE_CALENDAR_ID" + suffix, "")
    return [c.strip() for c in re.split(r"[,\s]+", raw) if c.strip()]


def sources_from_env():
    """환경변수에서 (자격증명, [캘린더ID]) 짝들을 수집. 키+ID가 모두 있을 때만."""
    sources = []
    for suffix in SUFFIXES:
        info = _creds_info(suffix)
        ids = _calendar_ids(suffix)
        if info and ids:
            sources.append((info, ids))
    return sources


def _service(info):
    creds = service_account.Credentials.from_service_account_info(info, scopes=SCOPES)
    return build("calendar", "v3", credentials=creds, cache_discovery=False)


def _timed_starts_within(ev, start, end) -> bool:
    """시간 지정 일정이 [start, end) 구간 안에서 '시작'하는지.

    Google Calendar events.list 는 구간과 '겹치는' 일정을 모두 돌려준다(timeMin=종료
    하한, timeMax=시작 상한). 그래서 전날 밤 23:30 시작이라도 종료가 자정을 넘기면
    다음날 구간과 겹쳐 함께 조회된다. 시간 일정은 '시작한 날'에만 표시해야 하므로,
    시작 시각이 구간 안에 들지 않으면 제외한다.
    (종일 일정은 여러 날 연차 등이 매일 떠야 하므로 이 필터를 적용하지 않는다.)"""
    dt = ev.get("start", {}).get("dateTime")
    if not dt:  # 종일 일정 → 필터 대상 아님(겹침 그대로 둠)
        return True
    s = datetime.fromisoformat(dt).astimezone(KST)
    return start <= s < end


def _list_events_one(service, cal_id, start, end):
    """한 캘린더의 [start, end) 구간 일정(raw)을 페이지네이션으로 모두 모아 반환."""
    out, page_token = [], None
    while True:
        resp = (
            service.events()
            .list(
                calendarId=cal_id,
                timeMin=start.isoformat(),
                timeMax=end.isoformat(),
                singleEvents=True,
                orderBy="startTime",
                pageToken=page_token,
            )
            .execute()
        )
        out.extend(resp.get("items", []))
        page_token = resp.get("nextPageToken")
        if not page_token:
            break
    return out


def fetch_events(sources, day=None):
    """
    여러 (자격증명, 캘린더ID목록) 소스에서 'day'(KST, 기본=오늘) 하루치 일정을 모아 반환.
    여러 캘린더에 겹친 일정은 제목+시작+장소 기준으로 한 번만.
    반환: (events: list[dict], day: date)

    캘린더 하나가 삭제/권한해제(404·403) 등으로 조회에 실패해도 그 캘린더만 건너뛰고
    경고를 남긴 뒤 나머지는 계속 모은다(한 캘린더 때문에 전체 발송이 멈추지 않게).
    서비스계정 초기화 실패도 해당 계정만 건너뛴다.
    """
    if day is None:
        day = datetime.now(KST).date()
    start = datetime(day.year, day.month, day.day, tzinfo=KST)
    end = start + timedelta(days=1)

    items, seen = [], set()
    for info, cal_ids in sources:
        try:
            service = _service(info)
        except Exception as e:  # 자격증명 JSON 파손 등 → 그 계정만 건너뜀
            print(f"[경고] 서비스계정 초기화 실패(건너뜀): {e}", file=sys.stderr)
            continue
        for cal_id in cal_ids:
            try:
                raw = _list_events_one(service, cal_id, start, end)
            except HttpError as e:
                status = getattr(getattr(e, "resp", None), "status", "?")
                print(
                    f"[경고] 캘린더 조회 실패(건너뜀): {cal_id} → HTTP {status}",
                    file=sys.stderr,
                )
                continue
            except Exception as e:  # 네트워크 등 예기치 못한 오류도 그 캘린더만 건너뜀
                print(
                    f"[경고] 캘린더 조회 실패(건너뜀): {cal_id} → {e}",
                    file=sys.stderr,
                )
                continue
            for ev in raw:
                if not _timed_starts_within(ev, start, end):
                    continue  # 자정 넘겨 겹치기만 한 전날 밤 일정 제외
                st = ev.get("start", {})
                key = (
                    ev.get("summary", ""),
                    st.get("dateTime") or st.get("date"),
                    ev.get("location", ""),
                )
                if key in seen:
                    continue
                seen.add(key)
                items.append(ev)

    return items, day


def fetch_today_events(calendar_ids, day=None):
    """단일(기본) 계정용 편의 함수 — 로컬 미리보기 등에서 사용."""
    return fetch_events([(_creds_info(""), calendar_ids)], day)
