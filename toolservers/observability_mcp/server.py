from __future__ import annotations

import json, sys
from .tools import TOOL_HANDLERS


def invoke(tool: str, args: dict):
    handler = TOOL_HANDLERS.get(tool)
    if not handler:
        return {"error": f"unknown tool {tool}"}
    return json.loads(handler(args))


def main():
    payload = json.loads(sys.stdin.read() or '{}')
    if payload.get('method') == 'list_tools':
        print(json.dumps({'tools': sorted(TOOL_HANDLERS)}))
        return
    result = invoke(payload.get('tool', ''), payload.get('args', {}))
    print(json.dumps(result, ensure_ascii=False))

if __name__ == '__main__':
    main()
