"""자동 점검 항목을 담당변호사의 직원에게 메일로 발송 (v1.38.0, Gmail SMTP·표준 라이브러리만).

main.py 가 실발송 때 만든 staff-warnings.json 을 읽어, 메일마다
받는 사람 = 주담당, 참조 = 부담당 으로 보낸다. 보낸 결과는 run-warnings.md(관리자 보고)
끝에 덧붙여, 이어지는 이슈·관리자 메일에 함께 실린다.

사용법:
    python notify_staff.py staff-warnings.json [run-warnings.md]

필요 환경변수: GMAIL_USERNAME, GMAIL_APP_PASSWORD (notify_mail.py 와 같음)

※ 보고 전용 — 여기서 실패해도 일정 알림 발송과는 무관하며, 항상 종료코드 0.
※ 메일마다 새로 연결한다(한 통의 연결 끊김이 다음 메일로 번지지 않게). 연결이 끊기거나
  타임아웃이면 한 번 더 보낸다 — 빠지는 것보다 중복이 낫다(04. 기일예정알림 v1.18 과 같은 방침).
"""

import json
import os
import smtplib
import sys
from email.mime.text import MIMEText
from email.utils import formatdate, make_msgid

SMTP_TIMEOUT = 60
# 서버가 거부 응답을 준 경우 — 다시 보내도 또 거부된다
_SERVER_REJECTED = (smtplib.SMTPResponseException, smtplib.SMTPRecipientsRefused)


def _build(sender, m):
    msg = MIMEText(m["text"], "plain", "utf-8")
    msg["Subject"] = m["subject"]
    msg["From"] = sender
    msg["Date"] = formatdate(localtime=True)
    msg["Message-ID"] = make_msgid(domain=(sender.split("@")[-1] or None))
    msg["To"] = ", ".join(m["to"])
    if m.get("cc"):
        msg["Cc"] = ", ".join(m["cc"])
    return msg.as_string()


def send_one(user, password, m, smtp_factory=smtplib.SMTP_SSL):
    """메일 1통 발송 → None(성공) / 오류 문자열."""
    raw = _build(user, m)
    rcpts = list(m["to"]) + list(m.get("cc") or [])
    err = None
    for _ in range(2):
        try:
            with smtp_factory("smtp.gmail.com", 465, timeout=SMTP_TIMEOUT) as smtp:
                smtp.login(user, password)
                refused = smtp.sendmail(user, rcpts, raw)
            return f"일부 수신 거부: {', '.join(refused)}" if refused else None
        except _SERVER_REJECTED as e:  # 로그인 실패(SMTPAuthenticationError)도 여기 — 다시 해도 같다
            return f"{type(e).__name__}: {e}"
        except Exception as e:  # noqa: BLE001 — 연결 끊김·타임아웃 → 한 번 더
            err = f"{type(e).__name__}: {e}"
    return err


def main():
    if len(sys.argv) < 2:
        sys.exit("사용법: python notify_staff.py staff-warnings.json [run-warnings.md]")
    try:  # Windows 한글 콘솔(cp949)에서 '—' 등 출력 시 깨지지 않게 (main.py 와 같음)
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass
    report_path = sys.argv[2] if len(sys.argv) >= 3 else "run-warnings.md"
    with open(sys.argv[1], "r", encoding="utf-8") as f:
        mails = json.load(f)
    if not mails:
        return

    user = os.environ.get("GMAIL_USERNAME", "")
    password = os.environ.get("GMAIL_APP_PASSWORD", "")
    lines = ["", "### 담당직원 메일 (출석변호사 복수 표기·접견번호 미검출)"]
    for m in mails:
        err = send_one(user, password, m) if user and password else "GMAIL 시크릿 미설정"
        status = f"발송 실패: {err}" if err else "발송 완료"
        lines.append(f"- {m['label']} — {status}")
        print(f"[담당직원 메일] {m['label']} — {status}")

    with open(report_path, "a", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


if __name__ == "__main__":
    main()
