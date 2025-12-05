# monitor_agent_single.py
"""
Single-file Monitor Agent.

- Exposes MonitorAgent class.
- Implements the LLM tools used by the agent (fetch_file_content, save_updated_file, save_snapshot).
- Provides run_monitor_once() coroutine for local testing.
"""

import os
import json
import asyncio
import datetime
from pathlib import Path
from typing import Dict, Any, Optional

from dotenv import load_dotenv

load_dotenv()

# NOTE: These imports assume you have Google ADK installed in your environment.
# If you don't, you will need to install or stub these when testing locally.
from google.adk.agents import LlmAgent
from google.adk.models.google_llm import Gemini
from google.adk.tools.agent_tool import AgentTool
from google.adk.tools.google_search_tool import google_search
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types as genai_types

APP_NAME = "monitor_app"
USER_ID = "monitor_user"
SESSION_ID = "monitor_session_0"

# Directory to store snapshots and updated files
SNAPSHOT_DIR = Path(__file__).parent.parent /"temp/data/monitored_snapshots"
SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)

DEFAULT_POLICY_PATH = Path(__file__).parent.parent /"temp/data/temp.txt"

DEFAULT_USER_EMAIL = os.getenv("USER_EMAIL")

print(f"MonitorAgent initialized with USER_EMAIL={DEFAULT_USER_EMAIL}")


class MonitorAgent:
    """
    MonitorAgent builds an LlmAgent which:
    - reads a local file,
    - optionally uses a google_search sub-agent,
    - writes an updated text file and JSON snapshot,
    - exposes tools that the LlmAgent can call.
    """

    def __init__(self, api_key: Optional[str] = None) -> None:
        self.api_key = api_key or os.getenv("GOOGLE_API_KEY")
        if not self.api_key:
            raise RuntimeError("GOOGLE_API_KEY is not set. Provide it via environment or pass api_key.")

        # Retry options for genai client
        retry_options = genai_types.HttpRetryOptions(
            attempts=5,
            exp_base=7,
            initial_delay=1,
            http_status_codes=[429, 500, 503, 504],
        )

        # LLMs
        self.search_llm = Gemini(
            model="gemini-2.5-flash-lite",
            api_key=self.api_key,
            retry_options=retry_options,
        )

        self.monitor_llm = Gemini(
            model="gemini-2.5-flash-lite",
            api_key=self.api_key,
            retry_options=retry_options,
        )

        # Sub-agent for Google Search
        self.google_search_agent = LlmAgent(
            name="google_search_agent",
            model=self.search_llm,
            description="Agent used for performing web checks via google_search tool.",
            instruction="Use the `google_search` tool to look up relevant facts.",
            tools=[google_search],
        )

        # Main monitor agent
        self.agent = LlmAgent(
            name="monitor_agent",
            model=self.monitor_llm,
            description="Monitor and minimally correct a text file and save snapshot.",
            instruction=self._instruction_text(),
            tools=[
                # tools are actual callables or AgentTool wrappers
                self.fetch_file_content,
                AgentTool(agent=self.google_search_agent),
                self.save_updated_file,
                self.save_snapshot,
            ],
        )

    def get_agent(self) -> LlmAgent:
        return self.agent

    # ---------------- Tools ----------------
    @staticmethod
    def fetch_file_content(file_path: str) -> str:
        path = Path(file_path)
        if not path.is_file():
            raise FileNotFoundError(f"File not found: {file_path}")
        return path.read_text(encoding="utf-8")

    @staticmethod
    def save_updated_file(file_path: str, updated_text: str) -> str:
        timestamp = datetime.datetime.utcnow().strftime("%Y%m%d_%H%M%S")

        user_dir = SNAPSHOT_DIR / f"{DEFAULT_USER_EMAIL}_monitored_file"

        # Create the directory only if it does not already exist
        if not user_dir.exists():
            user_dir.mkdir(parents=True)

        # File name: <email>.monitored_file.<timestamp>.txt
        out_name = f"raw_monitored_file.{timestamp}.txt"
        out_path = user_dir / out_name

        # Write updated content
        out_path.write_text(updated_text, encoding="utf-8")
        return str(out_path)

    @staticmethod
    def save_snapshot(file_path: str, file_content: str, search_result: Dict[str, Any]) -> str:
        timestamp = datetime.datetime.utcnow().strftime("%Y%m%d_%H%M%S")

        user_dir = SNAPSHOT_DIR / f"{DEFAULT_USER_EMAIL}_monitored_file"

        # Create the directory only if it does not already exist
        if not user_dir.exists():
            user_dir.mkdir(parents=True)

        # File name
        snapshot_name = f"monitored_file.{timestamp}.json"
        snapshot_path = user_dir / snapshot_name

        snapshot = {
            "timestamp_utc": timestamp,
            "file_path": file_path,
            "file_content": file_content,
            "search_result": search_result,
        }

        snapshot_path.write_text(
            json.dumps(snapshot, ensure_ascii=False, indent=2),
            encoding="utf-8"
        )
        return str(snapshot_path)

    # ---------------- Helpers ----------------
    @staticmethod
    def _instruction_text() -> str:
        # Keep instruction concise but sufficient for the agent to follow the described workflow
        return (
            "You are a monitoring and correction agent for a text file.\n\n"
            "Tools available:\n"
            "- fetch_file_content(file_path)\n"
            "- google_search_agent (via AgentTool)\n"
            "- save_updated_file(file_path, updated_text)\n"
            "- save_snapshot(file_path, file_content, search_result)\n\n"
            "Workflow:\n"
            "1) Read the original file using fetch_file_content.\n"
            "2) Identify typos, formatting issues, logical errors, and clearly outdated information.\n"
            "3) Use google_search_agent if verification or updated facts are required.\n"
            "4) Produce a concise summary of findings.\n"
            "5) Create updated_text by making minimal changes (preserve structure).\n"
            "6) Save updated_text with save_updated_file and save snapshot via save_snapshot.\n\n"
            "Final reply must include three parts in order: (A) Summary of Findings, (B) Updated File Path, (C) Snapshot File Path."
        )

# ---------------- Convenience runner ----------------
async def monitor(policy_path: str = DEFAULT_POLICY_PATH) -> str:
    policy_file = Path(policy_path)
    if not policy_file.exists():
        raise FileNotFoundError(f"Policy file not found: {policy_file.resolve()}")

    builder = MonitorAgent()
    agent = builder.get_agent()

    session_service = InMemorySessionService()
    await session_service.create_session(app_name=APP_NAME, user_id=USER_ID, session_id=SESSION_ID)

    runner = Runner(agent=agent, app_name=APP_NAME, session_service=session_service)

    user_text = (
        "You are monitoring a policy file on disk. "
        f"The file path is: {policy_path}\n"
        "Use fetch_file_content to read it, analyze, optionally search, save updated + snapshot, and produce the summary with paths."
    )

    user_content = genai_types.Content(role="user", parts=[genai_types.Part(text=user_text)])

    full_response_text = ""
    last_tool_result = None
    final_answer = None

    async for event in runner.run_async(user_id=USER_ID, session_id=SESSION_ID, new_message=user_content):
        # Collect content parts
        content = getattr(event, "content", None)
        if content and getattr(content, "parts", None):
            for part in content.parts:
                if getattr(part, "text", None):
                    if getattr(event, "partial", False):
                        full_response_text += part.text
                    else:
                        full_response_text += part.text + "\n"

        # Collect tool responses
        if callable(getattr(event, "get_function_responses", None)):
            responses = event.get_function_responses()
            if responses:
                try:
                    last_tool_result = json.dumps(responses[0].response, ensure_ascii=False, indent=2)
                except TypeError:
                    last_tool_result = str(responses[0].response)

        if event.is_final_response():
            if full_response_text.strip():
                final_answer = full_response_text.strip()
            elif last_tool_result:
                final_answer = "[Tool result]\n" + last_tool_result
            else:
                final_answer = "[monitor_agent] Final event had no text or tool result."
            break

    if final_answer is None:
        if full_response_text.strip():
            final_answer = full_response_text.strip()
        elif last_tool_result:
            final_answer = "[Tool result]\n" + last_tool_result
        else:
            final_answer = "[monitor_agent] No final text or tool result received."

    # Save a simple text snapshot with the final answer
    timestamp = datetime.datetime.utcnow().strftime("%Y%m%d_%H%M%S")

    user_dir = SNAPSHOT_DIR / f"{DEFAULT_USER_EMAIL}_monitored_file"

    # Create the directory only if it does not already exist
    if not user_dir.exists():
        user_dir.mkdir(parents=True)

    # File path
    text_snapshot_file = user_dir / f"monitored_file_summary.{timestamp}.txt"

    # Write fileC
    text_snapshot_file.write_text(final_answer, encoding="utf-8")


    return final_answer

if __name__ == "__main__":
    # CLI: run monitor once when invoked directly
    try:
        output = asyncio.run(monitor())
        print(output)
    except Exception as exc:
        print("Error running monitor:", exc)
        raise
