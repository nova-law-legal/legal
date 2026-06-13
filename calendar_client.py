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
    raw = os.environ["GOOGLE_SERVICE_ACCOUNT_JSON"]
    info = json.loads(raw)
    creds = service_account.Credentials.from_service_account_info(info, scopes=SCOPES)
    return build("calendar", "v3", credentials=creds, cache_discovery=False)


def fetch_today_events(calendar_id: str, day=None):
    """
    주어진 캘린더에서 'day'(KST 기준, 기본=오늘) 하루치 일정을 시간순으로 반환.
    반환: (events: list[dict], day: date)
    """
    if day is None:
        day = datetime.now(KST).date()

    start = datetime(day.year, day.month, day.day, tzinfo=KST)
    end = start + timedelta(days=1)

    service = _get_service()
    items, page_token = [], None
    while True:
        resp = (
            service.events()
            .list(
                calendarId=calendar_id,
                timeMin=start.isoformat(),
                timeMax=end.isoformat(),
                singleEvents=True,
                orderBy="startTime",
                pageToken=page_token,
            )
            .execute()
        )
        items.extend(resp.get("items", []))
        page_token = resp.get("nextPageToken")
        if not page_token:
            break

    return items, day
