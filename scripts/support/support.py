import os
import json
import logging
from dotenv import load_dotenv
from pyairtable import Api
from .prompt_user import prompt_user

# Initialize dotenv
load_dotenv()

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
log = logging.getLogger("PadeaMigration")

# Initialize Airtable
AIRTABLE_API_KEY = os.environ.get("AIRTABLE_API_KEY")
AIRTABLE_ID = os.environ.get("AIRTABLE_ID")

if not AIRTABLE_API_KEY or not AIRTABLE_ID:
    log.error("Missing Airtable configuration in .env!")

api = Api(AIRTABLE_API_KEY) if AIRTABLE_API_KEY else None
base = api.base(AIRTABLE_ID) if api and AIRTABLE_ID else None

def get_table(name):
    if not base:
        raise ValueError("Airtable Base is not initialized. Check your .env file.")
    return base.table(name)

def airtable_get(table_name, filter_formula=None):
    try:
        table = get_table(table_name)
        if filter_formula:
            return table.all(formula=filter_formula)
        return table.all()
    except Exception as e:
        log.error(f"Error fetching from Airtable table {table_name}: {e}")
        return []

def airtable_post(table_name, records):
    """
    Posts records to Airtable.
    records can be a list of dicts:
      - either: [{"fields": {...}}]
      - or: [{...}] (flat list of fields)
    """
    if not records:
        return []
    
    formatted_records = []
    for r in records:
        if isinstance(r, dict) and "fields" in r:
            formatted_records.append(r["fields"])
        else:
            formatted_records.append(r)
            
    table = get_table(table_name)
    inserted_records = []
    # Batch in 10s
    for i in range(0, len(formatted_records), 10):
        batch = formatted_records[i:i+10]
        try:
            res = table.batch_create(batch)
            inserted_records.extend(res)
        except Exception as e:
            log.error(f"Error posting batch to table {table_name}: {e}")
            raise e
    return inserted_records

def clear_table(table_name):
    table = get_table(table_name)
    try:
        records = table.all()
        if not records:
            return
        record_ids = [r["id"] for r in records]
        log.info(f"Clearing {len(record_ids)} records from {table_name}")
        for i in range(0, len(record_ids), 10):
            table.batch_delete(record_ids[i:i+10])
    except Exception as e:
        log.warning(f"Failed to clear table {table_name}: {e}")

def ask_llm(prompt):
    key = os.environ.get("CLAUDE_CODE_API_KEY") or os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        log.warning("No Claude or Anthropic API key found. LLM queries will try prompt the user.")
        answer = prompt_user(prompt)
        return answer
    try:
        from anthropic import Anthropic
        client = Anthropic(api_key=key)
        response = client.messages.create(
            model="claude-3-5-sonnet-latest",
            max_tokens=4000,
            messages=[{"role": "user", "content": prompt}]
        )
        return response.content[0].text
    except Exception as e:
        log.error(f"Error calling Anthropic API: {e}")
        return NotImplemented
