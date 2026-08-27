"""SMS 발송 어댑터.

Phase 1은 개발용 콘솔 발송만 실제 동작한다.
운영 배포 시 국내 SMS 벤더 중 하나를 골라 아래 Provider를 구현하면 된다.

후보 (2026년 기준, 소규모 단체 기준 추천순):
  1) Solapi(구 쿨SMS)  — 가입 즉시 API 사용 가능, 건당 약 20원, 문서/파이썬 SDK 양호. 소규모에 가장 무난.
  2) NHN Cloud SMS     — 대형 클라우드 안정성, 콘솔에서 발신번호 사전등록 필요.
  3) 알리고(Aligo)      — 저렴하고 절차 간단, 이후 카카오 친구톡 확장 시 같은 벤더로 처리 가능.

어느 벤더든 "발신번호 사전등록"(통신사 규제)이 필요하므로, 교회 대표번호 또는
총무 담당자 번호로 미리 등록해두어야 한다.
"""

from __future__ import annotations

import logging

from app.config import SMS_PROVIDER

logger = logging.getLogger("dcb.sms")


class SmsProvider:
    def send(self, *, to: str, text: str) -> None:  # pragma: no cover - 인터페이스
        raise NotImplementedError


class ConsoleSmsProvider(SmsProvider):
    """개발용. 실제 발송 대신 서버 로그에 출력한다."""

    def send(self, *, to: str, text: str) -> None:
        logger.warning("[SMS-DEV] to=%s | %s", to, text)
        print(f"\n>>> [개발용 SMS] {to} : {text}\n", flush=True)


class UnconfiguredSmsProvider(SmsProvider):
    def __init__(self, name: str) -> None:
        self.name = name

    def send(self, *, to: str, text: str) -> None:
        raise RuntimeError(
            f"SMS 공급자 '{self.name}' 연동이 아직 구현되지 않았습니다. "
            "app/sms.py 에 Provider를 추가하고 API 키를 환경변수로 설정하세요."
        )


def get_sms_provider() -> SmsProvider:
    if SMS_PROVIDER == "console":
        return ConsoleSmsProvider()
    return UnconfiguredSmsProvider(SMS_PROVIDER)


def send_auth_code(phone_number: str, code: str) -> None:
    get_sms_provider().send(
        to=phone_number,
        text=f"[대청부 수련회] 인증번호 {code} (3분 이내 입력)",
    )
