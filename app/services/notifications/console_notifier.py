"""Development notifier — logs the message instead of sending WhatsApp/SMS.

Lets the full agent/booking flow be exercised without integrating a real
provider. Swap in a real `Notifier` for staging/production.
"""

import logging

from app.services.notifications.base import Message

logger = logging.getLogger(__name__)


class ConsoleNotifier:
    name = "console"

    def send(self, to_phone: str, message: Message, *, channel: str = "whatsapp") -> None:
        # Log the template key too, so dev output shows which template a real
        # provider would have used for this message.
        logger.info(
            "\n"
            "------------------------------------------------------------\n"
            " [%s → %s] template=%s\n"
            "%s\n"
            "------------------------------------------------------------",
            channel.upper(),
            to_phone,
            message.template,
            message.text,
        )
