"""Small request helpers shared by the view modules."""

from __future__ import annotations

import json


def parse_json_body(request) -> dict | None:
    """The request body as a dict, or None when it is not valid JSON."""
    try:
        return json.loads(request.body or b"{}")
    except (ValueError, TypeError):
        return None
