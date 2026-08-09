"""자동 점검·실패 보고 메일 발송 (Gmail SMTP, 표준 라이브러리만 사용).

사용법:
    python notify_mail.py "제목" 본문파일.md     # 파일 내용을 본문으로
    echo "본문" | python notify_mail.py "제목"   # 표준입력을 본문으로

필요 환경변수:
    GMAIL_USERNAME       발신 Gmail 주소 (예: novalaw.legal@gmail.com)
    GMAIL_APP_PASSWORD   해당 계정의 앱 비밀번호 16자리
                         (Google 계정 → 보안 → 2단계 인증 → 앱 비밀번호)
    MAIL_TO              수신 주소 (미지정 시 GMAIL_USERNAME 으로 발송)

※ 이 스크립트는 보고 전용이다 — 여기서 실패해도 일정 알림 발송과는 무관하다.
"""

import os
import smtplib
import sys
from email.header import Header
from email.mime.text import MIMEText


def main():
    if len(sys.argv) < 2:
        sys.exit("사용법: python notify_mail.py \"제목\" [본문파일]")
    subject = sys.argv[1]
    if len(sys.argv) >= 3:
        with open(sys.argv[2], "r", encoding="utf-8") as f:
            body = f.read()
    else:
        body = sys.stdin.read()

    user = os.environ["GMAIL_USERNAME"]
    password = os.environ["GMAIL_APP_PASSWORD"]
    to = os.environ.get("MAIL_TO") or user

    msg = MIMEText(body, "plain", "utf-8")
    msg["Subject"] = str(Header(subject, "utf-8"))
    msg["From"] = user
    msg["To"] = to

    with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=30) as smtp:
        smtp.login(user, password)
        smtp.sendmail(user, [to], msg.as_string())
    print(f"보고 메일 발송 완료 → {to}")


if __name__ == "__main__":
    main()
