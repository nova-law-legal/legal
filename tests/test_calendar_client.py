"""calendar_client 조회 필터 회귀테스트.
실행:  python tests/test_calendar_client.py
"""

import os
import sys
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import calendar_client  # noqa: E402
from calendar_client import KST, _timed_starts_within, fetch_events  # noqa: E402
from googleapiclient.errors import HttpError  # noqa: E402


def _window(d: date):
    start = datetime(d.year, d.month, d.day, tzinfo=KST)
    return start, start + timedelta(days=1)


PASS, FAIL = 0, 0


def check(name, cond):
    global PASS, FAIL
    if cond:
        PASS += 1
        print("PASS ", name)
    else:
        FAIL += 1
        print("FAIL ", name)


# 대상일 = 6/17. 윈도우 = [6/17 00:00, 6/18 00:00)
start, end = _window(date(2026, 6, 17))


def timed(dt):
    return {"start": {"dateTime": dt}}


# 핵심 회귀: 6/16 23:30 시작(종료가 자정 넘겨 6/17과 겹쳐 조회됨) -> 6/17 일정에서 제외
check(
    "전날밤_자정넘김_제외",
    _timed_starts_within(timed("2026-06-16T23:30:00+09:00"), start, end) is False,
)

# 정상: 6/17 당일 시작 -> 포함
check(
    "당일_시간일정_포함",
    _timed_starts_within(timed("2026-06-17T10:00:00+09:00"), start, end) is True,
)

# 경계: 6/17 00:00 정각 시작 -> 포함(하한 포함)
check(
    "자정정각_시작_포함",
    _timed_starts_within(timed("2026-06-17T00:00:00+09:00"), start, end) is True,
)

# 경계: 6/18 00:00 시작 -> 제외(상한 배타)
check(
    "익일자정_시작_제외",
    _timed_starts_within(timed("2026-06-18T00:00:00+09:00"), start, end) is False,
)

# 종일 일정은 필터 대상 아님(여러 날 연차가 매일 떠야 함) -> 항상 포함
check(
    "종일일정_필터안함",
    _timed_starts_within({"start": {"date": "2026-06-15"}}, start, end) is True,
)

# UTC 표기여도 KST 변환 후 판정: 2026-06-16T14:30:00Z == 6/16 23:30 KST -> 제외
check(
    "UTC표기_KST변환_제외",
    _timed_starts_within(timed("2026-06-16T14:30:00Z"), start, end) is False,
)


# ── 캘린더 하나가 죽어도(404 등) 나머지는 계속 모으는지 ──────────────
class _FakeReq:
    def __init__(self, result=None, exc=None):
        self._result, self._exc = result, exc

    def execute(self):
        if self._exc:
            raise self._exc
        return self._result


class _FakeEvents:
    """cal_id -> items(list) 또는 raise할 Exception 을 매핑한 가짜 events()."""

    def __init__(self, mapping):
        self.mapping = mapping

    def list(self, calendarId, **kw):
        v = self.mapping[calendarId]
        if isinstance(v, Exception):
            return _FakeReq(exc=v)
        return _FakeReq(result={"items": v})


class _FakeService:
    def __init__(self, mapping):
        self._ev = _FakeEvents(mapping)

    def events(self):
        return self._ev


def _http_error(status):
    resp = type("R", (), {"status": status, "reason": "Not Found"})()
    return HttpError(resp, b"{}")


# 6/17 당일 10:00 시작 일정(윈도우 안에 듦)
_good_ev = {"summary": "정상기일", "start": {"dateTime": "2026-06-17T10:00:00+09:00"}}
_mapping = {
    "dead@group.calendar.google.com": _http_error(404),  # 삭제된 캘린더
    "live@group.calendar.google.com": [_good_ev],         # 정상 캘린더
}
_orig_service = calendar_client._service
calendar_client._service = lambda info: _FakeService(_mapping)
try:
    evs, _ = fetch_events(
        [(object(), ["dead@group.calendar.google.com", "live@group.calendar.google.com"])],
        day=date(2026, 6, 17),
    )
finally:
    calendar_client._service = _orig_service

check("죽은캘린더_건너뛰고_나머지수집", [e["summary"] for e in evs] == ["정상기일"])


print(f"\n{PASS}/{PASS + FAIL} passed")
sys.exit(1 if FAIL else 0)
