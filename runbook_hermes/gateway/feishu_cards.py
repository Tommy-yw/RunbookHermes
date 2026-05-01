from __future__ import annotations

from typing import Any, Dict


def incident_card(title: str, body: str, approval_id: str = "") -> Dict[str, Any]:
    return {
        "config": {"wide_screen_mode": True},
        "header": {"title": {"tag": "plain_text", "content": title}},
        "elements": [
            {"tag": "markdown", "content": body},
            {"tag": "note", "elements": [{"tag": "plain_text", "content": f"approval_id={approval_id}"}]},
        ],
    }
