from __future__ import annotations

from functools import cache

from db import Settings, session


@cache
def get_settings(chat_id: int) -> Settings:
    settings = (
        session.query(Settings)
        .filter(
            Settings.chat_id == chat_id,
        )
        .first()
    )

    if not settings:
        settings = Settings(chat_id=chat_id)
        session.add(settings)
        session.commit()

    return settings
