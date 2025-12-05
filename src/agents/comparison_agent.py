# src/agents/comparison_agent_wo_vertexai.py

import os
import time
import json
from pathlib import Path
from dataclasses import dataclass
from typing import Optional, Dict, Any

from dotenv import load_dotenv

# ADK imports
from google.adk.agents import LlmAgent
from google.adk.tools.google_search_tool import google_search
from google.adk.runners import Runner
from google.adk.sessions.in_memory_session_service import InMemorySessionService

#from src.tools.notifier_tool import send_email
from src.tools.notifier_tool_auth import send_email

# Gemini base SDK types for constructing messages
from google.genai import types

load_dotenv()


# ---------------------------------------------------------
# Utility — newest file helper
# ---------------------------------------------------------
def newest_file(files: list[Path]):
    if not files:
        return None
    return max(files, key=lambda f: f.stat().st_mtime)


# ---------------------------------------------------------
# Placeholder notification hook
# ---------------------------------------------------------
def notification_agent(summary: str):
    print(">>> Notification Agent Triggered!")
    print(summary)

    print(">>> Send notification email.")
    send_email(
        #to_email="hrf.devops@gmail.com",
        to_email="lwangucr@gmail.com",
        subject="Policy Compliance Guardian Notification",
        body="""Greetings,
        \nYour latest policy update has been processed successfully. Please check the updated documents from Google Drive for details.
        \n\nBest regards,\nPolicy Compliance Guardian Team
        """,
    )


# ---------------------------------------------------------
# Agent Config
# ---------------------------------------------------------
@dataclass
class ComparisonAgentConfig:
    api_key: str
    model: str = "gemini-2.5-pro"
    temperature: float = 0.2
    top_p: float = 0.9
    top_k: int = 20


# ---------------------------------------------------------
# Comparison Agent
# ---------------------------------------------------------
class ComparisonAgent:

    def __init__(self, api_key: Optional[str] = None):
        api_key = api_key or os.getenv("GOOGLE_API_KEY")
        if not api_key:
            raise ValueError("Missing GOOGLE_API_KEY")

        self.config = ComparisonAgentConfig(api_key=api_key)

        # ADK LlmAgent: the model can be the model string directly
        self.agent = LlmAgent(
            name="comparison_agent",
            model=self.config.model,
            instruction=(
                "You are an expert in semantic comparison of policy documents. "
                "Compare meaning, not wording. Identify any real changes in rights, "
                "liabilities, responsibilities, scope, deadlines, compliance factors. "
                "Ignore paraphrasing unless the meaning truly changes. "
                "Respond strictly in JSON: {\"changed\": true/false, \"summary\": \"...\"}."
            ),
            # tools=[google_search],
        )

        # ADK runner session service
        self.session_service = InMemorySessionService()
        self.runner = Runner(
            agent=self.agent,
            app_name="comparison_agent_app",
            session_service=self.session_service,
        )

    # ---------------------------------------------------------
    # Find latest snapshot in a directory
    # ---------------------------------------------------------
    def get_latest_authorized_snapshot(self, base_dir: Path) -> Optional[Path]:
        if not base_dir.exists():
            return None

        files = list(base_dir.glob("*.json")) + list(base_dir.glob("*.txt"))
        return newest_file(files)

    # ---------------------------------------------------------
    # Read local file
    # ---------------------------------------------------------
    def _read_file(self, path: Path) -> str:
        if not path.exists():
            return ""
        return path.read_text(encoding="utf-8")

    # ---------------------------------------------------------
    # Parse JSON output safely
    # ---------------------------------------------------------
    def _parse_response(self, raw_text: str) -> Dict[str, Any]:
        try:
            return json.loads(raw_text)
        except Exception:
            return {"changed": True, "summary": "Model returned unstructured output."}

    # ---------------------------------------------------------
    # MAIN: Compare two policy docs
    # ---------------------------------------------------------
    async def compare(self, old_file: Path, new_file: Path) -> Dict[str, Any]:
        old_text = self._read_file(old_file)
        new_text = self._read_file(new_file)

        prompt = f"""
Compare the following two documents for meaningful policy updates:

OLD DOCUMENT:
{old_text}

NEW DOCUMENT:
{new_text}

Respond in JSON format:
{{
  "changed": true/false,
  "summary": "Short explanation"
}}
"""

        # Create ADK session
        user_id = "comparison_user"
        session_id = f"comparison_session_{int(time.time())}"

        await self.session_service.create_session(
            app_name="comparison_agent_app",
            user_id=user_id,
            session_id=session_id,
        )

        # Wrap prompt per ADK format
        content = types.Content(
            role="user",
            parts=[types.Part(text=prompt)]
        )

        final_text = None

        # Invoke the agent via Runner
        async for event in self.runner.run_async(
            user_id=user_id,
            session_id=session_id,
            new_message=content
        ):
            if event.is_final_response():
                if event.content and event.content.parts:
                    final_text = event.content.parts[0].text
                break

        if not final_text:
            return {"changed": True, "summary": "No final response from comparison agent."}

        # Parse JSON
        #print("final_text Debug: ", final_text[:50])
        parsed = self._parse_response(final_text)
        #print("Debug: ", parsed[:100])

        # Trigger notification
        if parsed.get("changed"):
            notification_agent(parsed.get("summary", "Changes detected."))

        return parsed
