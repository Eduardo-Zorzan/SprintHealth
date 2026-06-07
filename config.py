import json
import os

COMPLETED_WORK_FIELD = 'Microsoft.VSTS.Scheduling.CompletedWork'
REMAINING_WORK_FIELD = 'Microsoft.VSTS.Scheduling.RemainingWork'
CONFIG_FILE = 'devops_config.json'
MEMBERS_CACHE_FILE = 'members_cache.json'
ITERATIONS_CACHE_FILE = 'iterations_cache.json'


def load_config():
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except: pass
    return {}


def save_config(url, area, sprint, token, start_date, end_date):
    config = {
        "url": url, "area": area, "sprint": sprint, "token": token,
        "start_date": start_date, "end_date": end_date
    }
    with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
        json.dump(config, f, indent=4)


def load_members_cache():
    if os.path.exists(MEMBERS_CACHE_FILE):
        try:
            with open(MEMBERS_CACHE_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except: pass
    return []


def save_members_cache(members):
    with open(MEMBERS_CACHE_FILE, 'w', encoding='utf-8') as f:
        json.dump(members, f, indent=4)


def load_iterations_cache():
    """Load iterations from cache file. Returns dict with 'timestamp' and 'data', or None."""
    if os.path.exists(ITERATIONS_CACHE_FILE):
        try:
            with open(ITERATIONS_CACHE_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except: pass
    return None


def save_iterations_cache(iterations_data):
    """Save iterations tree with current timestamp."""
    from datetime import datetime
    cache = {
        'timestamp': datetime.now().isoformat(),
        'data': iterations_data
    }
    with open(ITERATIONS_CACHE_FILE, 'w', encoding='utf-8') as f:
        json.dump(cache, f, indent=4)
