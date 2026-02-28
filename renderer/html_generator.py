"""HTML Report Generator for Agent Runs.

Converts JSONL logs to interactive HTML reports using Jinja2 templates.
Auto-detects stream-json vs old SDK format.
"""

import json
from pathlib import Path
from datetime import datetime
from typing import Dict, List

from jinja2 import Environment, FileSystemLoader

from .message_parser import (
    adapt_stream_json,
    is_stream_json,
    parse_system_message,
    parse_assistant_message,
    parse_user_message,
    parse_result_message,
)


class HTMLGenerator:
    """Generate interactive HTML reports from JSONL logs using Jinja2."""

    def __init__(self, jsonl_path: Path):
        self.jsonl_path = Path(jsonl_path)
        self.messages: list = []
        self.stats: dict = {}
        self.templates_dir = Path(__file__).parent / "templates"

        self.jinja_env = Environment(
            loader=FileSystemLoader(self.templates_dir),
            autoescape=True,
        )

    def generate(self, output_path: Path | None = None) -> Path:
        """Generate HTML report.

        Args:
            output_path: Optional custom output path

        Returns:
            Path to generated HTML file
        """
        self._load_messages()
        self._calculate_stats()
        processed_messages = self._process_messages()

        css_content = self._load_css_files()
        js_content = self._load_file("script.js")

        template = self.jinja_env.get_template("base.html")
        html_content = template.render(
            report_name=self.jsonl_path.stem,
            stats=self.stats,
            messages=processed_messages,
            messages_json=json.dumps(self.messages),
            base_css=css_content["base"],
            system_css=css_content["system"],
            assistant_css=css_content["assistant"],
            user_css=css_content["user"],
            result_css=css_content["result"],
            script_js=js_content,
        )

        if output_path is None:
            output_path = self.jsonl_path.with_suffix(".html")

        output_path.write_text(html_content, encoding="utf-8")
        return output_path

    def _load_file(self, filename: str) -> str:
        """Load file content from templates directory."""
        return (self.templates_dir / filename).read_text(encoding="utf-8")

    def _load_css_files(self) -> Dict[str, str]:
        """Load all CSS files."""
        styles_dir = self.templates_dir / "styles"
        return {
            "base": (styles_dir / "base.css").read_text(encoding="utf-8"),
            "system": (styles_dir / "system.css").read_text(encoding="utf-8"),
            "assistant": (styles_dir / "assistant.css").read_text(encoding="utf-8"),
            "user": (styles_dir / "user.css").read_text(encoding="utf-8"),
            "result": (styles_dir / "result.css").read_text(encoding="utf-8"),
        }

    def _load_messages(self):
        """Load messages from JSONL file, auto-detecting format."""
        raw_messages = []
        with open(self.jsonl_path, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    raw_messages.append(json.loads(line))

        # Auto-detect: stream-json uses lowercase type values
        if is_stream_json(raw_messages):
            self.messages = adapt_stream_json(raw_messages)
        else:
            self.messages = raw_messages

    def _calculate_stats(self):
        """Calculate session statistics."""
        self.stats = {
            "total_messages": len(self.messages),
            "message_types": {},
            "start_time": None,
            "end_time": None,
            "duration": None,
            "model": "Unknown",
            "total_cost": 0.0,
            "total_tokens": {
                "input": 0,
                "output": 0,
                "cache_read": 0,
                "cache_write": 0,
            },
            "tools_used": set(),
        }

        for msg in self.messages:
            msg_type = msg.get("type", "Unknown")

            self.stats["message_types"][msg_type] = (
                self.stats["message_types"].get(msg_type, 0) + 1
            )

            if msg_type == "SystemMessage" and not self.stats["start_time"]:
                self.stats["start_time"] = msg.get("timestamp")
                data = msg.get("data", {})
                self.stats["model"] = data.get("model", "Unknown")

            if msg_type == "ResultMessage":
                self.stats["end_time"] = msg.get("timestamp")
                data = msg.get("data", {})
                self.stats["total_cost"] = data.get("total_cost_usd", 0.0)

                usage = data.get("usage", {})
                self.stats["total_tokens"]["input"] += usage.get("input_tokens", 0)
                self.stats["total_tokens"]["output"] += usage.get("output_tokens", 0)
                self.stats["total_tokens"]["cache_read"] += usage.get(
                    "cache_read_input_tokens", 0
                )
                self.stats["total_tokens"]["cache_write"] += usage.get(
                    "cache_creation_input_tokens", 0
                )

        # Calculate duration from timestamps (ISO) or skip for sequence numbers
        if self.stats["start_time"] and self.stats["end_time"]:
            start_ts = self.stats["start_time"]
            end_ts = self.stats["end_time"]

            # Sequence numbers (from adapter) start with #
            if not start_ts.startswith("#"):
                try:
                    start = datetime.fromisoformat(start_ts.replace("Z", "+00:00"))
                    end = datetime.fromisoformat(end_ts.replace("Z", "+00:00"))
                    duration_seconds = (end - start).total_seconds()
                    self.stats["duration"] = self._format_duration(duration_seconds)
                except Exception:
                    pass

        # For stream-json, use duration_ms from result if available
        if not self.stats["duration"]:
            for msg in self.messages:
                if msg.get("type") == "ResultMessage":
                    duration_ms = msg.get("data", {}).get("duration_ms", 0)
                    if duration_ms:
                        self.stats["duration"] = self._format_duration(
                            duration_ms / 1000
                        )
                    break

        # Convert sets to lists for JSON serialization
        self.stats["tools_used"] = list(self.stats["tools_used"])

    def _format_duration(self, seconds: float) -> str:
        """Format duration in human-readable format."""
        if seconds < 60:
            return f"{seconds:.1f}s"
        elif seconds < 3600:
            return f"{seconds / 60:.1f}m"
        else:
            return f"{seconds / 3600:.1f}h"

    def _process_messages(self) -> List[Dict]:
        """Process messages for rendering."""
        processed = []

        for index, msg in enumerate(self.messages):
            msg_type = msg.get("type", "Unknown")
            timestamp = msg.get("timestamp", "")
            data = msg.get("data", {})

            # Format timestamp
            if timestamp.startswith("#"):
                formatted_time = timestamp
            else:
                try:
                    dt = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
                    formatted_time = dt.strftime("%H:%M:%S")
                except Exception:
                    formatted_time = timestamp

            # Determine message type class
            type_class = "system"
            if "User" in msg_type:
                type_class = "user"
            elif "Assistant" in msg_type:
                type_class = "assistant"
            elif "Tool" in msg_type or "mcp" in msg_type.lower():
                type_class = "tool"
            elif "Result" in msg_type:
                type_class = "result"

            rendered_content = self._render_message(msg_type, data, index)

            processed.append(
                {
                    "type": msg_type,
                    "type_class": type_class,
                    "formatted_time": formatted_time,
                    "rendered_content": rendered_content,
                    "raw_data": json.dumps(data, indent=2),
                }
            )

        return processed

    def _render_message(self, msg_type: str, data: Dict, msg_index: int = 0) -> str:
        """Render message using appropriate Jinja2 template."""
        if msg_type == "SystemMessage":
            template = self.jinja_env.get_template("components/system_message.html")
            parsed_data = parse_system_message(data)
            return template.render(data=parsed_data)

        elif msg_type == "AssistantMessage":
            template = self.jinja_env.get_template("components/assistant_message.html")
            parsed_data = parse_assistant_message(data)
            return template.render(**parsed_data)

        elif msg_type == "UserMessage":
            template = self.jinja_env.get_template("components/user_message.html")
            parsed_data = parse_user_message(data)
            return template.render(**parsed_data, msg_index=msg_index)

        elif msg_type == "ResultMessage":
            template = self.jinja_env.get_template("components/result_message.html")
            parsed_data = parse_result_message(data)
            return template.render(**parsed_data)

        else:
            return f'<p class="unknown-message">{json.dumps(data)}</p>'
