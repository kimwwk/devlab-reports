"""Message parser and stream-json adapter.

Combines two responsibilities:
1. Adapter: converts CLI stream-json JSONL to the old SDK message format
2. Parser: extracts structured data from messages for template rendering
"""

import json
from typing import Any


# ---------------------------------------------------------------------------
# Adapter: stream-json → old SDK format
# ---------------------------------------------------------------------------

def adapt_stream_json(messages: list[dict]) -> list[dict]:
    """Convert stream-json messages to old SDK message format.

    Stream-json (from `claude --output-format stream-json --verbose`) uses
    lowercase type values and nests content under `message.content[]`.
    The old SDK format uses PascalCase type names and puts data under `data`.

    Since stream-json has no per-message timestamps, we use sequence numbers.

    Args:
        messages: List of parsed JSONL lines in stream-json format

    Returns:
        List of messages in old SDK format
    """
    result = []
    seq = 0

    for msg in messages:
        msg_type = msg.get("type", "")

        if msg_type == "system":
            seq += 1
            result.append({
                "type": "SystemMessage",
                "timestamp": f"#{seq}",
                "data": {
                    "model": msg.get("model", "Unknown"),
                    "cwd": msg.get("cwd", "Unknown"),
                    "tools": msg.get("tools", []),
                    "mcp_servers": msg.get("mcp_servers", []),
                },
            })

        elif msg_type == "assistant":
            content_blocks = msg.get("message", {}).get("content", [])
            for block in content_blocks:
                seq += 1
                result.append({
                    "type": "AssistantMessage",
                    "timestamp": f"#{seq}",
                    "data": {"content": block},
                })

        elif msg_type == "user":
            content_blocks = msg.get("message", {}).get("content", [])
            for block in content_blocks:
                seq += 1
                result.append({
                    "type": "UserMessage",
                    "timestamp": f"#{seq}",
                    "data": {"content": block},
                })

        elif msg_type == "result":
            seq += 1
            result.append({
                "type": "ResultMessage",
                "timestamp": f"#{seq}",
                "data": {
                    "is_error": msg.get("is_error", False),
                    "duration_ms": msg.get("duration_ms", 0),
                    "total_cost_usd": msg.get("total_cost_usd", 0.0),
                    "usage": msg.get("usage", {}),
                },
            })

    return result


def is_stream_json(messages: list[dict]) -> bool:
    """Detect whether messages are in stream-json format.

    Stream-json uses lowercase type values like "system", "assistant".
    Old SDK format uses PascalCase like "SystemMessage", "AssistantMessage".
    """
    if not messages:
        return False
    first_type = messages[0].get("type", "")
    return first_type in ("system", "assistant", "user", "result")


# ---------------------------------------------------------------------------
# Parser: extract structured data from old SDK format messages
# ---------------------------------------------------------------------------

def parse_system_message(data: dict) -> dict[str, Any]:
    """Parse SystemMessage data."""
    return {
        "model": data.get("model", "Unknown"),
        "cwd": data.get("cwd", "Unknown"),
        "tools": data.get("tools", []),
        "mcp_servers": data.get("mcp_servers", []),
    }


def parse_assistant_message(data: dict) -> dict[str, Any]:
    """Parse AssistantMessage data."""
    content = data.get("content", "")

    # Dict or list content (from recent SDK or adapted stream-json)
    if isinstance(content, (dict, list)):
        return _parse_content_blocks(content)

    # String representation (legacy SDK)
    if isinstance(content, str):
        if "TextBlock" in content:
            return _parse_text_block(content)
        elif "ToolUseBlock" in content:
            return _parse_tool_use_block(content)

    return {"content_type": "text", "fallback_text": str(content)}


def parse_user_message(data: dict) -> dict[str, Any]:
    """Parse UserMessage data (usually tool results)."""
    content = data.get("content", "")

    if isinstance(content, (dict, list)):
        return _parse_tool_result_blocks(content)

    if isinstance(content, str) and "ToolResultBlock" in content:
        return _parse_tool_result_string(content)

    return {"content_type": "text", "fallback_text": str(content)}


def parse_result_message(data: dict) -> dict[str, Any]:
    """Parse ResultMessage data."""
    return {
        "is_error": data.get("is_error", False),
        "duration_ms": data.get("duration_ms", 0),
        "total_cost": data.get("total_cost_usd", 0.0),
        "usage": {
            "input_tokens": data.get("usage", {}).get("input_tokens", 0),
            "output_tokens": data.get("usage", {}).get("output_tokens", 0),
            "cache_read_input_tokens": data.get("usage", {}).get("cache_read_input_tokens", 0),
            "cache_creation_input_tokens": data.get("usage", {}).get("cache_creation_input_tokens", 0),
        },
    }


# ---------------------------------------------------------------------------
# Content block parsers
# ---------------------------------------------------------------------------

def _parse_content_blocks(content) -> dict[str, Any]:
    """Parse content blocks (dict or list)."""
    if isinstance(content, dict):
        block_type = content.get("type", "")

        if block_type == "text":
            return {"content_type": "text", "text": content.get("text", "")}

        if block_type == "tool_use":
            return {
                "content_type": "tool_use",
                "tool_name": content.get("name", "Unknown"),
                "tool_input": json.dumps(content.get("input", {}), indent=2),
            }

        if block_type == "thinking":
            return {"content_type": "text", "text": content.get("thinking", "")}

    if isinstance(content, list) and len(content) > 0:
        return _parse_content_blocks(content[0])

    return {"content_type": "text", "fallback_text": str(content)}


def _parse_text_block(content: str) -> dict[str, Any]:
    """Parse TextBlock from string representation."""
    try:
        if "text='" in content:
            start = content.index("text='") + 6
            pos = start
            while pos < len(content):
                if content[pos] == "'" and (pos == 0 or content[pos - 1] != "\\"):
                    if pos + 1 < len(content) and content[pos + 1] == ")":
                        break
                pos += 1
            else:
                pos = content.rindex("')")
            end = pos
        else:
            start = content.index('text="') + 6
            pos = start
            while pos < len(content):
                if content[pos] == '"' and (pos == 0 or content[pos - 1] != "\\"):
                    if pos + 1 < len(content) and content[pos + 1] == ")":
                        break
                pos += 1
            else:
                pos = content.rindex('")')
            end = pos

        text = content[start:end]
        text = text.replace("\\n", "\n").replace("\\t", "\t")
        text = text.replace('\\"', '"').replace("\\'", "'")
        text = text.replace("\\\\", "\\")

        return {"content_type": "text", "text": text}
    except Exception:
        return {"content_type": "text", "fallback_text": content}


def _parse_tool_use_block(content: str) -> dict[str, Any]:
    """Parse ToolUseBlock from string representation."""
    try:
        if "name='" in content:
            name_start = content.index("name='") + 6
            name_end = content.index("'", name_start)
        else:
            name_start = content.index('name="') + 6
            name_end = content.index('"', name_start)

        tool_name = content[name_start:name_end]

        tool_input = ""
        if "input={" in content:
            input_start = content.index("input={") + 6
            input_end = content.rindex("}")
            input_str = content[input_start : input_end + 1]
            try:
                input_dict = eval(input_str)  # noqa: S307 - controlled input
                tool_input = json.dumps(input_dict, indent=2)
            except Exception:
                tool_input = input_str

        return {
            "content_type": "tool_use",
            "tool_name": tool_name,
            "tool_input": tool_input,
        }
    except Exception:
        return {"content_type": "text", "fallback_text": content}


# ---------------------------------------------------------------------------
# Tool result parsers
# ---------------------------------------------------------------------------

def _parse_tool_result_blocks(content) -> dict[str, Any]:
    """Parse tool result blocks."""
    if isinstance(content, dict):
        if content.get("type") == "tool_result":
            result_content = content.get("content", "")
            is_error = content.get("is_error", False)
            result_text = _convert_to_text(result_content)
            is_long = _is_long_content(result_text)
            return {
                "content_type": "tool_result",
                "is_error": is_error,
                "result_text": result_text,
                "result_format": "text",
                "is_long_content": is_long,
            }

    if isinstance(content, list) and len(content) > 0:
        return _parse_tool_result_blocks(content[0])

    return {"content_type": "text", "fallback_text": str(content)}


def _parse_tool_result_string(content: str) -> dict[str, Any]:
    """Parse ToolResultBlock from string representation."""
    try:
        is_error = "is_error=True" in content or "<tool_use_error>" in content
        result_text = ""

        if "content=[" in content:
            content_start = content.index("content=[") + 9
            bracket_count = 1
            pos = content_start
            while pos < len(content) and bracket_count > 0:
                if content[pos] == "[":
                    bracket_count += 1
                elif content[pos] == "]":
                    bracket_count -= 1
                pos += 1
            content_end = pos - 1
            list_str = content[content_start:content_end]
            try:
                content_list = eval(list_str)  # noqa: S307
                result_text = _convert_to_text(content_list)
            except Exception:
                result_text = list_str
                result_text = result_text.replace("\\n", "\n").replace("\\t", "\t")

        elif "content='" in content:
            content_start = content.index("content='") + 9
            pos = content_start
            while pos < len(content):
                if content[pos] == "'" and content[pos - 1] != "\\":
                    break
                pos += 1
            result_text = content[content_start:pos]
            result_text = result_text.replace("\\n", "\n").replace("\\t", "\t")

        elif 'content="' in content:
            content_start = content.index('content="') + 9
            pos = content_start
            while pos < len(content):
                if content[pos] == '"' and content[pos - 1] != "\\":
                    break
                pos += 1
            result_text = content[content_start:pos]
            result_text = result_text.replace("\\n", "\n").replace("\\t", "\t")

        else:
            result_text = content

        if "<tool_use_error>" in result_text:
            result_text = result_text.replace("<tool_use_error>", "").replace("</tool_use_error>", "").strip()

        is_long = _is_long_content(result_text)
        return {
            "content_type": "tool_result",
            "is_error": is_error,
            "result_text": result_text,
            "result_format": "text",
            "is_long_content": is_long,
        }
    except Exception:
        return {"content_type": "text", "fallback_text": content}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _convert_to_text(content) -> str:
    """Convert content to plain text, handling nested structures."""
    if isinstance(content, list) and len(content) > 0:
        first = content[0]
        if isinstance(first, dict) and first.get("type") == "text":
            result_text = first.get("text", "")
        else:
            result_text = str(content)
    elif isinstance(content, dict):
        result_text = content.get("text", str(content))
    elif isinstance(content, str):
        result_text = content
    else:
        result_text = str(content)

    result_text = result_text.replace("\\n", "\n")
    result_text = result_text.replace("\\t", "\t")
    result_text = result_text.replace("\\r", "\r")
    return result_text


def _is_long_content(text: str, line_threshold: int = 5) -> bool:
    """Check if content has more than threshold lines."""
    return text.count("\n") >= line_threshold
