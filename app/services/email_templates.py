from html import escape
from typing import NamedTuple


class Email(NamedTuple):
    subject: str
    text: str
    html: str


def password_reset(link: str) -> Email:
    return Email(
        subject="Reset your bckpack.ing password",
        text=(
            "Someone asked to reset the password for your bckpack.ing account.\n\n"
            f"To choose a new password, open this link within the next hour:\n{link}\n\n"
            "If you didn't ask for this, you can ignore this email. Your password won't change.\n"
        ),
        html=(
            "<p>Someone asked to reset the password for your bckpack.ing account.</p>"
            f'<p><a href="{escape(link)}">Choose a new password</a></p>'
            "<p>The link works for the next hour. If you didn't ask for this, you can ignore this email. "
            "Your password won't change.</p>"
        ),
    )
