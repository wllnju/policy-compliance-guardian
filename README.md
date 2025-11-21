# Policy Compliance Guardian

AI-powered assistant that monitors official policy sources, compares them with internal policy drafts (e.g. Google Docs), and notifies stakeholders when meaningful changes are detected.

> ⚠️ **MVP scope (2 weeks):**  
> One external policy URL + one internal Google Docs draft, manual trigger, email-style change summary.  
> No automatic edits to drafts yet. Human review required.

---

## 1. Overview

Policy Compliance Guardian helps teams stay aligned with changing regulations and institutional policies.

**Core idea:**

1. Fetch the latest text from an **official policy source** (e.g. a government or institutional web page).
2. Fetch the current **internal policy draft** from Google Docs.
3. Use an LLM-based agent to **detect and summarize differences**.
4. Generate a **notification email body** for policy owners / stakeholders.

This is an internal research/prototype project, not a production compliance tool.

---

## 2. Features (MVP)

- ✅ Monitor **one configured policy URL**  
- ✅ Fetch **one configured Google Docs draft**  
- ✅ AI-powered **comparison agent**:
  - Detects whether there are material changes.
  - Summarizes what changed in plain language.
  - Assigns a rough **criticality** level (low / medium / high).
- ✅ **Notification generator**:
  - Produces an email-style message: what changed, why it matters, suggested next steps.
- ✅ Basic logging of each run (timestamp, URL, doc ID, has_change, criticality).

**Out of scope for MVP**

- Automatic editing of the Google Doc draft.
- Multiple policy sources / drafts.
- Full UI dashboard.
- Formal legal/compliance guarantees.

---

## 3. Architecture (High-Level)

### Components

- **Policy Fetcher (`src/services/policy_fetcher.py`)**  
  Fetches HTML content from the configured policy URL and extracts the main text.

- **Docs Fetcher (`src/services/docs_fetcher.py`)**  
  Uses the Google Docs API to pull the internal draft text by document ID.

- **Comparison Agent (`src/agents/comparison_agent.py`)**  
  LLM-based component that:
  - Inputs: `policy_text`, `draft_text`
  - Outputs (conceptually):
    ```json
    {
      "has_change": true,
      "change_summary": "...",
      "criticality": "low" | "medium" | "high"
    }
    ```

- **Notification Agent (`src/agents/notification_agent.py`)**  
  Turns the change summary into an email-style body (and optional subject suggestion).

- **Workflow Orchestrator (`src/main_workflow.py`)**  
  Glue script that:
  1. Fetches policy + draft.
  2. Calls the comparison agent.
  3. Logs results.
  4. Prints or sends the notification email (in `--dry-run` mode by default).

---

## 4. Getting Started

### Prerequisites

- Python 3.10+ (or your chosen version)
- Access to:
  - A Google Cloud project with:
    - Vertex AI / Generative AI API enabled (for LLM calls).
    - Google Docs API enabled.
  - Service account credentials with:
    - Permission to read the chosen Google Doc.
- (Optional) Access to Gmail API or SMTP server if you want to send real emails.

### Clone the Repository

```bash
git clone https://github.com/wllnju/policy-compliance-guardian.git
cd policy-compliance-guardian
```

### repository top-level structure
```bash
policy-compliance-guardian/
├── src/
│   ├── agents/
│   │   ├── OPTIONAL (orchestrator_agent.py)
│   │   ├── monitor_agent.py
│   │   ├── comparison_agent.py
│   │   ├── notification_agent.py
│   │   └── __init__.py
│   ├── services/
│   │   ├── policy_fetcher.py      # HTTP + scraping
│   │   ├── docs_fetcher.py        # Google Docs API
│   │   ├── X NOT NEEDED (email_sender.py        # Gmail or SMTP)
│   │   └── X NOT NEEDED (storage.py             # Firestore / SQLite wrapper)
│   └── main_workflow.py           # end-to-end check
│
├── docs/
│   ├── architecture.md
│   └── capstone_summary.md
│
├── tests/
│   └── test_comparison_agent.py
│
├── README.md
├── ROADMAP.md
├── requirements.txt
└── .gitignore
