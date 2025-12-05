# test_agent.py
import logging
import os
import asyncio
import datetime
from pathlib import Path
from dotenv import load_dotenv

# Agents
from src.agents.authorizer_agent import AuthorizerAgent
from src.agents.monitor_agent import MonitorAgent, monitor
from src.agents.comparison_agent import ComparisonAgent

#from src.tools.docs_fetcher import fetch_temp_docs
from src.tools.docs_fetcher_auth import fetch_temp_docs
# Logging setup
logging.basicConfig(format="[%(levelname)s]: %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

load_dotenv()

DEFAULT_POLICY_PATH = Path(__file__).parent
DEFAULT_USER_EMAIL = os.getenv("USER_EMAIL")
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")

# Interval (days) for auto-run
WORKFLOW_INTERVAL_DAYS = float(os.getenv("WORKFLOW_RUN_INTERVAL_DAYS", 7))

APP_NAME = "monitor_app"
USER_ID = "monitor_user"
SESSION_ID = "monitor_session_0"


# ---------------------------------------------------------
# ORIGINAL COMMENTED CODE — Monitor Agent Loading
# ---------------------------------------------------------
logger.info("Loading monitor agent...")

try:
    builder = MonitorAgent(api_key=os.getenv("GOOGLE_API_KEY"))
    root_agent = builder.get_agent()
    logger.info("Monitor agent loaded successfully as root_agent")
except Exception as e:
    root_agent = None
    logger.error(f"Failed to load monitor agent: {e}")


# ---------------------------------------------------------
# ORIGINAL COMMENTED CODE — Authorizer Agent
# ---------------------------------------------------------
async def run_authorizer():
    input_dir = DEFAULT_POLICY_PATH / "src" / "temp" / "data" / "monitored_snapshots" / f"{DEFAULT_USER_EMAIL}_monitored_file"
    output_dir = DEFAULT_POLICY_PATH / "src" / "temp" / "data" / "authorized_snapshots" / f"{DEFAULT_USER_EMAIL}_authorized_file"

    agent = AuthorizerAgent()
    return await agent.analyze_and_process(input_dir, output_dir)


# ---------------------------------------------------------
# ACTIVE AUTHORIZE FUNCTION
# ---------------------------------------------------------
async def run_authorizer():
    input_dir = (
        DEFAULT_POLICY_PATH
        / "src"
        / "temp"
        / "data"
        / "monitored_snapshots"
        / f"{DEFAULT_USER_EMAIL}_monitored_file"
    )
    output_dir = (
        DEFAULT_POLICY_PATH
        / "src"
        / "temp"
        / "data"
        / "authorized_snapshots"
        / f"{DEFAULT_USER_EMAIL}_authorized_file"
    )

    agent = AuthorizerAgent()
    return await agent.analyze_and_process(input_dir, output_dir)


# ---------------------------------------------------------
# COMPARISON AGENT WORKFLOW
# ---------------------------------------------------------
async def run_comparison():
    comp = ComparisonAgent(api_key=GOOGLE_API_KEY)

    old_file = DEFAULT_POLICY_PATH / "src" / "temp" / "data" / "temp.txt"
    if not old_file.exists():
        print(f"Old baseline file not found: {old_file}")
        return None

    base_dir = (
        DEFAULT_POLICY_PATH
        / "src"
        / "temp"
        / "data"
        / "authorized_snapshots"
        / f"{DEFAULT_USER_EMAIL}_authorized_file"
    )

    raw_files = sorted(
        [f for f in base_dir.glob("raw_*") if f.is_file()],
        key=lambda f: f.stat().st_mtime,
    )

    if not raw_files:
        print("No raw_* files found in authorised snapshot directory.")
        return None

    new_file = raw_files[-1]

    print("\nComparing snapshots:")
    print("OLD (baseline):", old_file.name)
    print("NEW (latest raw file):", new_file.name)

    return await comp.compare(old_file, new_file)


# ---------------------------------------------------------
# FULL WORKFLOW (monitor → authorize → compare)
# ---------------------------------------------------------
async def full_workflow():
    print("\n[Workflow] Starting full agentic process...")

    # STEP 1 — Monitor
    print("[Workflow] Running Monitor step...")
    try:
        monitor_result = await monitor()
        print("[Workflow] Monitor result:", monitor_result)
    except Exception as e:
        print("[Workflow] Monitor error:", e)

    # STEP 2 — Authorize
    print("[Workflow] Running Authorizer step...")
    try:
        auth_result = await run_authorizer()
        print("[Workflow] Authorization result:", auth_result)
    except Exception as e:
        print("[Workflow] Authorization error:", e)

    # STEP 3 — Compare
    print("[Workflow] Running Comparison step...")
    try:
        compare_result = await run_comparison()
        print("[Workflow] Comparison result:", compare_result)
    except Exception as e:
        print("[Workflow] Comparison error:", e)

    print("[Workflow] Completed.\n")


# ---------------------------------------------------------
# SCHEDULER — RUN WORKFLOW EVERY N DAYS
# ---------------------------------------------------------
async def run_every_n_days(n_days: float, workflow_coroutine):
    interval = float(n_days) * 24 * 60 * 60  # seconds

    while True:
        print(f"[Scheduler] Running workflow...")

        # Documents fetching step
        print("[Scheduler] Fetching latest documents from Google Drive...")
        fetch_temp_docs()

        try:
            await workflow_coroutine()
        except Exception as e:
            print(f"[Scheduler] Error: {e}")

        print(f"[Scheduler] Sleeping {n_days} days...")
        await asyncio.sleep(interval)



# ---------------------------------------------------------
# ORIGINAL COMMENTED MAIN EXECUTION BLOCK
# ---------------------------------------------------------
# if __name__ == "__main__":
#     print("Running monitor workflow once...")
#     try:
#         monitor_output = asyncio.run(monitor())
#         print("Monitor result:", monitor_output)
#     except Exception as e:
#         print("Monitor error:", e)
#
#     print("\nRunning policy authorization workflow...")
#     try:
#         result = asyncio.run(run_authorizer())
#         print("Authorization result:", result)
#     except Exception as e:
#         print("Authorizer error:", e)
#
#     print("\nRunning comparison workflow...")
#     try:
#         comparison_result = asyncio.run(run_comparison())
#         print("Comparison result:", comparison_result)
#     except Exception as e:
#         print("Comparison error:", e)


# ---------------------------------------------------------
# ACTIVE ENTRY POINT — AUTOSCHEDULED
# ---------------------------------------------------------
if __name__ == "__main__":
    print(
        f"Starting auto-scheduler... workflow runs every {WORKFLOW_INTERVAL_DAYS} days."
    )
    asyncio.run(run_every_n_days(WORKFLOW_INTERVAL_DAYS, full_workflow))
