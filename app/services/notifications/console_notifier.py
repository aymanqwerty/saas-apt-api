"""Development notifier — logs the message instead of sending WhatsApp/SMS.

Lets the full agent/booking flow be exercised without integrating a real
provider. Swap in a real `Notifier` for staging/production.
"""

import logging

logger = logging.getLogger(__name__)


class ConsoleNotifier:
    name = "console"

    def send(self, to_phone: str, message: str, *, channel: str = "whatsapp") -> None:
        logger.info(
            "\n"
            "------------------------------------------------------------\n"
            " [%s → %s]\n"
            "%s\n"
            "------------------------------------------------------------",
            channel.upper(),
            to_phone,
            message,
        )
