import os
import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

# -------------------------------------------------
# Logging
# -------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="[%(levelname)s] %(asctime)s %(name)s – %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("padea_migration")

# -------------------------------------------------
# Environment
# -------------------------------------------------
def load_env() -> None:
    """Load .env if present."""
    from dotenv import load_dotenv

    dotenv_path = Path.cwd() / ".env"
    if dotenv_path.is_file():
        load_dotenv(dotenv_path)
        log.info("Loaded environment from %s", dotenv_path)
    else:
        log.warning(".env file not found – ensure AIRTABLE_API_KEY is set in the shell.")


# -------------------------------------------------
# Airtable helpers
# -------------------------------------------------
BASE_ID = os.getenv("AIRTABLE_ID")  # constant base ID
AIRTABLE_TOKEN = os.getenv("AIRTABLE_API_KEY")
HEADERS = {
    "Authorization": f"Bearer {AIRTABLE_TOKEN}",
    "Content-Type": "application/json",
}


def airtable_post(table_name: str, records: List[Dict[str, Any]]) -> None:
    """
    POST a batch of records (max 10 per request) to the Data API.
    """
    from urllib import request
    import urllib.error

    url = f"https://api.airtable.com/v0/{BASE_ID}/{table_name}"
    payload = json.dumps({"records": records}).encode()
    req = request.Request(url, data=payload, headers=HEADERS, method="POST")

    try:
        with request.urlopen(req) as resp:
            result = json.load(resp)
            log.info("Inserted %d rows into %s", len(result.get("records", [])), table_name)
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        log.error("Airtable POST failed (%s) – %s", e.code, body)
        raise


def airtable_get(table_name: str, filter_formula: Optional[str] = None) -> List[Dict]:
    """
    Retrieve all records from a table (simple pagination, 100 per page).
    """
    from urllib import request
    import urllib.parse

    records = []
    offset = None
    while True:
        params = {}
        if filter_formula:
            params["filterByFormula"] = filter_formula
        if offset:
            params["offset"] = offset
        query = urllib.parse.urlencode(params)
        url = f"https://api.airtable.com/v0/{BASE_ID}/{table_name}?{query}"
        req = request.Request(url, headers=HEADERS, method="GET")
        with request.urlopen(req) as resp:
            data = json.load(resp)
            records.extend(data.get("records", []))
            offset = data.get("offset")
            if not offset:
                break
    return records


# -------------------------------------------------
# LLM proxy (Claude) – placeholder until API key is added
# -------------------------------------------------
def ask_llm(prompt: str) -> str:
    """
    Send `prompt` to Claude via the Claude Code API.
    Returns the raw response text.
    """
    from scripts.support import log  # local import to avoid circularity

    # This is a thin wrapper – actual implementation will be added once
    # `CLAUDE_API_KEY` is present in .env.
    log.info("[AGENT] %s", prompt)
    # Placeholder – the calling script should handle `NotImplemented` by flagging the record.
    return NotImplemented
