from collections import defaultdict
from datetime import datetime, timedelta


DEMO_SERVER_URL = "mock://sprint-health"
DEMO_AREA_OPTIONS = [
    "SprintHealth\\Platform",
    "SprintHealth\\Mobile",
]
DEMO_SPRINT_OPTIONS = [
    "SprintHealth\\Sprint 2026.15",
    "SprintHealth\\Sprint 2026.14",
]
DEMO_SPRINT_DATES = {
    "SprintHealth\\Sprint 2026.15": ("06/07/2026", "17/07/2026"),
    "SprintHealth\\Sprint 2026.14": ("22/06/2026", "03/07/2026"),
}
DEMO_MEMBERS = [
    "Ana Silva",
    "Bruno Costa",
    "Camila Rocha",
    "Diego Martins",
    "Eva Almeida",
]
DEMO_TASKS = [
    {"id": "9101", "title": "Checkout validation", "assignee": "Ana Silva", "initial": 10.0, "burn": 1.7},
    {"id": "9102", "title": "Payment retry states", "assignee": "Ana Silva", "initial": 8.0, "burn": 1.1, "scope_day": 3, "scope_add": 2.0},
    {"id": "9103", "title": "Capacity import", "assignee": "Bruno Costa", "initial": 13.0, "burn": 1.8},
    {"id": "9104", "title": "Burndown tooltip polish", "assignee": "Camila Rocha", "initial": 5.0, "burn": 1.3},
    {"id": "9105", "title": "Historical membership fallback", "assignee": "Diego Martins", "initial": 16.0, "burn": 2.0, "scope_day": 4, "scope_add": 4.0},
    {"id": "9106", "title": "Reassignment table filtering", "assignee": "Eva Almeida", "initial": 7.0, "burn": 1.4},
    {"id": "9107", "title": "Analytics timeout handling", "assignee": "Bruno Costa", "initial": 9.0, "burn": 1.2},
    {"id": "9108", "title": "Chart export styling", "assignee": "Camila Rocha", "initial": 6.0, "burn": 1.0},
]
DEMO_CAPACITY_BY_MEMBER = {
    "Ana Silva": 6.0,
    "Bruno Costa": 5.5,
    "Camila Rocha": 6.0,
    "Diego Martins": 5.0,
    "Eva Almeida": 4.5,
}
DEMO_DAYS_OFF = {
    "Bruno Costa": [("13/07/2026", "13/07/2026")],
    "Eva Almeida": [("10/07/2026", "10/07/2026")],
}
DEMO_REASSIGNMENT_TEMPLATES = [
    ("9106", "(Unassigned)", "Eva Almeida", 0.00, "09:15", "Ana Silva"),
    ("9102", "Ana Silva", "Camila Rocha", 0.27, "14:20", "Diego Martins"),
    ("9105", "Diego Martins", "Bruno Costa", 0.36, "10:45", "Ana Silva"),
    ("9107", "Bruno Costa", "Ana Silva", 0.73, "16:05", "Camila Rocha"),
    ("9108", "Camila Rocha", "Eva Almeida", 0.82, "11:30", "Diego Martins"),
]


def is_demo_url(base_url):
    value = (base_url or "").strip().casefold()
    return value in {"mock", "demo", DEMO_SERVER_URL} or value.startswith(("mock://", "demo://"))


def get_demo_area_options():
    return list(DEMO_AREA_OPTIONS)


def get_demo_sprint_options():
    return list(DEMO_SPRINT_OPTIONS)


def get_demo_sprint_dates(sprint_name=None):
    sprint = (sprint_name or "").strip()
    if sprint in DEMO_SPRINT_DATES:
        return DEMO_SPRINT_DATES[sprint]
    return DEMO_SPRINT_DATES[DEMO_SPRINT_OPTIONS[0]]


def get_demo_members(selected_members=None):
    selected = _selected_member_names(selected_members)
    return selected if selected_members else list(DEMO_MEMBERS)


def get_demo_date_range(start_date=None, end_date=None):
    default_start, default_end = get_demo_sprint_dates()
    return start_date or default_start, end_date or default_end


def get_demo_task_ids(selected_members=None):
    return [task["id"] for task in _selected_tasks(selected_members)]


def get_demo_snapshot_rows(start_date=None, end_date=None, selected_members=None):
    start_text, end_text = get_demo_date_range(start_date, end_date)
    work_days = _work_days(_parse_br_date(start_text), _parse_br_date(end_text))
    rows = []
    total_days = len(work_days) or 1

    for task in _selected_tasks(selected_members):
        for index, day in enumerate(work_days):
            remaining = _task_remaining(task, index, total_days)
            completed = max((task["initial"] + _scope_for_day(task, index)) - remaining, 0.0)
            state = "Done" if remaining <= 0.05 else "Active"
            rows.append({
                "WorkItemId": int(task["id"]),
                "DateSK": _date_sk(day),
                "RemainingWork": round(remaining, 2),
                "CompletedWork": round(completed, 2),
                "State": state,
                "AssignedTo": task["assignee"],
                "Title": task["title"],
                "SnapshotCount": 1,
            })

    return rows


def get_demo_capacities(selected_members=None, start_date=None, end_date=None):
    members = _selected_member_names(selected_members)
    capacities = []
    for member in members:
        days_off = []
        for start, end in DEMO_DAYS_OFF.get(member, []):
            days_off.append({
                "start": _to_azure_date(start),
                "end": _to_azure_date(end),
            })

        capacities.append({
            "teamMember": {
                "displayName": member,
                "uniqueName": _member_email(member),
            },
            "activities": [
                {
                    "name": "Development",
                    "capacityPerDay": DEMO_CAPACITY_BY_MEMBER.get(member, 5.0),
                }
            ],
            "daysOff": days_off,
        })
    return capacities


def get_demo_work_history(selected_members=None, start_date=None, end_date=None, progress_callback=None):
    start_text, end_text = get_demo_date_range(start_date, end_date)
    work_days = _work_days(_parse_br_date(start_text), _parse_br_date(end_text))
    total_days = len(work_days) or 1
    person_daily_data = defaultdict(lambda: defaultdict(lambda: {"completed": 0.0, "remaining_dec": 0.0}))
    tasks = _selected_tasks(selected_members)

    for task_index, task in enumerate(tasks):
        for day_index, day in enumerate(work_days):
            if progress_callback:
                progress_callback(0.10 + (((task_index * total_days) + day_index + 1) / (len(tasks) * total_days or 1)) * 0.85)

            previous_remaining = _task_remaining(task, max(day_index - 1, 0), total_days)
            remaining = _task_remaining(task, day_index, total_days)
            if day_index == 0:
                decrease = max(task["initial"] - remaining, 0.0)
            else:
                decrease = max(previous_remaining - remaining, 0.0)
            if decrease <= 0:
                continue

            completed = round(decrease * (0.65 + ((day_index + task_index) % 3) * 0.15), 2)
            assignee = task["assignee"]
            person_daily_data[assignee][day]["completed"] += completed
            person_daily_data[assignee][day]["remaining_dec"] += round(decrease, 2)

    print(f"Using demo work-history data for {len(tasks)} task(s).")
    return {
        person: {
            day: {
                "completed": round(values["completed"], 2),
                "remaining_dec": round(values["remaining_dec"], 2),
            }
            for day, values in days.items()
        }
        for person, days in person_daily_data.items()
    }


def get_demo_reassignments(task_ids=None, start_date=None, end_date=None, progress_callback=None):
    allowed_ids = {str(task_id) for task_id in task_ids or get_demo_task_ids()}
    start_text, end_text = get_demo_date_range(start_date, end_date)
    start = _parse_br_date(start_text)
    end = _parse_br_date(end_text)
    if start > end:
        print("Using demo reassignment data: 0 event(s).")
        return []

    events = _demo_reassignment_events(start, end)
    reassignments = []
    for index, (task_id, from_name, to_name, changed_at, changed_by) in enumerate(events, start=1):
        if progress_callback:
            progress_callback(0.10 + (index / len(events)) * 0.85)
        if task_id not in allowed_ids:
            continue
        reassignments.append({
            "task_id": task_id,
            "from": from_name,
            "to": to_name,
            "date": changed_at.strftime("%d/%m/%Y %H:%M"),
            "date_sort": changed_at,
            "changed_by": changed_by,
        })

    reassignments.sort(key=lambda item: item["date_sort"], reverse=True)
    print(f"Using demo reassignment data: {len(reassignments)} event(s).")
    return reassignments


def _parse_br_date(value):
    return datetime.strptime(value, "%d/%m/%Y").date()


def _date_sk(day):
    return int(day.strftime("%Y%m%d"))


def _to_azure_date(value):
    return _parse_br_date(value).strftime("%Y-%m-%dT00:00:00Z")


def _work_days(start, end):
    current = start
    days = []
    while current <= end:
        if current.weekday() < 5:
            days.append(current)
        current += timedelta(days=1)
    return days


def _demo_reassignment_events(start, end):
    span_days = max((end - start).days, 0)
    events = []
    for task_id, from_name, to_name, position, time_text, changed_by in DEMO_REASSIGNMENT_TEMPLATES:
        event_day = start + timedelta(days=round(span_days * position))
        hour, minute = [int(part) for part in time_text.split(":", 1)]
        changed_at = datetime(event_day.year, event_day.month, event_day.day, hour, minute)
        events.append((task_id, from_name, to_name, changed_at, changed_by))
    return events


def _normalize_name(value):
    return (value or "").strip().casefold()


def _selected_member_names(selected_members=None):
    if not selected_members:
        return list(DEMO_MEMBERS)
    selected = {_normalize_name(member) for member in selected_members}
    return [member for member in DEMO_MEMBERS if _normalize_name(member) in selected or _normalize_name(_member_email(member)) in selected]


def _selected_tasks(selected_members=None):
    members = set(_selected_member_names(selected_members))
    return [task for task in DEMO_TASKS if task["assignee"] in members]


def _scope_for_day(task, day_index):
    scope_day = task.get("scope_day")
    if scope_day is None or day_index < scope_day:
        return 0.0
    return task.get("scope_add", 0.0)


def _task_remaining(task, day_index, total_days):
    scope = _scope_for_day(task, day_index)
    effective_initial = task["initial"] + scope
    remaining = effective_initial - (task["burn"] * day_index)
    if day_index >= total_days - 1:
        remaining = min(remaining, task.get("final_remaining", 0.0))
    return max(remaining, 0.0)


def _member_email(member):
    return member.lower().replace(" ", ".") + "@example.test"
