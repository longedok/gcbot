from typing import Any


def get_ttl_buttons(command: str) -> list[list[dict]]:
    return [
        [{"text": f"/{command} 30 seconds"}, {"text": f"/{command} 5 minutes"}],
        [{"text": f"/{command} 30 minutes"}, {"text": f"/{command} 6 hours"}],
        [{"text": f"/{command} 1 day"}, {"text": f"/{command} 1 day 16 hours"}],
    ]


def get_remove_keyboard() -> dict[str, Any]:
    return {
        "remove_keyboard": True,
        "selective": True,
    }
