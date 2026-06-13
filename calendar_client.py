"""Google Calendar 읽기 (서비스 계정, 읽기 전용)."""

import json
import os
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from google.oauth2 import service_account
from googleapiclient.discovery import build

KST = ZoneInfo("Asia/Seoul")
SCOPES = ["https://www.googleapis.com/auth/calendar.readonly"]


def _get_service():
    # 자격증명: 내용(GOOGLE_SERVICE_ACCOUNT_JSON) 우선, 없으면 파일경로(GOOGLE_SERVICE_ACCOUNT_FILE).
    #   - GitHub Actions: Secrets 로 JSON '내용'을 주입
    #   - 로컬: 다운로드한 키 .json '파일경로'만 적으면 됨
    raw = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON")
    if raw:
        info = json.loads(raw)
    else:
        path = os.environ.get("GOOGLE_SERVICE_ACCOUNT_FILE")
        if not path:
            raise RuntimeError(
                "서비스 계정 자격증명이 없습니다. GOOGLE_SERVICE_ACCOUNT_JSON(내용) 또는 "
                "GOOGLE_SERVICE_ACCOUNT_FILE(파일경로) 중 하나를 설정하세요."
            )
        with open(path, "r", encoding="utf-8") as f:
            info = json.load(f)
    creds = service_account.Credentials.from_service_account_info(info, scopes=SCOPES)
    return build("calendar", "v3", credentials=creds, cache_discovery=False)


def fetch_today_events(calendar_ids, day=None):
    """
    주어진 캘린더(들)에서 'day'(KST 기준, 기본=오늘) 하루치 일정을 반환.
    calendar_ids: 단일 문자열 또는 리스트. 여러 개면 모두 합쳐서 돌려준다.
                  (시간순 정렬은 transform.build_message 가 전체를 다시 수행)
    반환: (events: list[dict], day: date)
    """
    if isinstance(calendar_ids, str):
        calendar_ids = [calendar_ids]

    if day is None:
        day = datetime.now(KST).date()

    start = datetime(day.year, day.month, day.day, tzinfo=KST)
    end = start + timedelta(days=1)

    service = _get_service()
    items, seen = [], set()
    for cal_id in calendar_ids:
        page_token = None
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
            for ev in resp.get("items", []):
                # 같은 일정이 여러 팀 캘린더에 겹쳐 있으면 한 번만 (제목+시작+장소 기준)
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
            page_token = resp.get("nextPageToken")
            if not page_token:
                break

    return items, day
