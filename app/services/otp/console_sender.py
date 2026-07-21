"""Development OTP sender — logs the code instead of sending an SMS.

Lets the full auth flow be exercised in development without integrating a real
SMS provider. The code is written to the application log at INFO level so it is
visible on the console; swap in a real `OtpSender` for staging/production.
"""

import logging

logger = logging.getLogger(__name__)


class ConsoleOtpSender:
    name = "console"

    def send(self, phone_number: str, code: str, *, doctor_name: str) -> None:
        logger.info(
            "\n"
            "============================================================\n"
            " OTP for %s (%s): %s\n"
            "============================================================",
            phone_number,
            doctor_name,
            code,
        )
