import base64
import concurrent.futures
import time
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import quote

import requests
import urllib3

from config import (
    COMPLETED_WORK_FIELD,
    REMAINING_WORK_FIELD,
    load_iterations_cache,
    save_iterations_cache,
)

# Disable SSL Warnings
urllib3.disable_warnings()


def _parse_br_date(value, label="Date"):
    if not value:
        raise ValueError(f"{label} is required. Use DD/MM/YYYY.")
    try:
        return datetime.strptime(value, "%d/%m/%Y").date()
    except ValueError as exc:
        raise ValueError(f"{label} must use DD/MM/YYYY.") from exc


def _parse_azure_datetime(value):
    if not value:
        return None
    return datetime.fromisoformat(value.replace('Z', '+00:00')).astimezone()


def _parse_azure_date(value):
    if not value:
        return None
    return datetime.strptime(value.split('T')[0], "%Y-%m-%d").date()


def _coerce_float(value, default=0.0):
    try:
        if value is None:
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _identity_name(value):
    if isinstance(value, dict):
        return value.get('displayName') or value.get('uniqueName') or ""
    return value or ""


def _normalize_name(value):
    return (value or "").strip().casefold()


def _normalize_classification_field_path(value, structure_type):
    """Convert REST classification paths to WIQL field paths."""
    path = (value or "").strip().strip('"').strip("'").lstrip("\\")
    parts = [part.strip() for part in path.split("\\") if part.strip()]
    if len(parts) >= 2 and parts[1].casefold() == structure_type.casefold():
        parts.pop(1)
    return "\\".join(parts)


def normalize_area_path(area_path):
    return _normalize_classification_field_path(area_path, "Area")


def normalize_iteration_path(iteration_path):
    clean_path = (iteration_path or "").strip()
    if clean_path.startswith('@'):
        return clean_path
    return _normalize_classification_field_path(clean_path, "Iteration")


def _wiql_quote(value):
    return "'" + (value or "").replace("'", "''") + "'"


def _date_range(start_date, end_date):
    current = start_date
    while current <= end_date:
        yield current
        current += timedelta(days=1)


def _fetch_task_updates(session, base_url, task_id):
    updates = []
    skip = 0
    page_size = 200
    while True:
        res = session.get(
            f"{base_url}/_apis/wit/workitems/{task_id}/updates?api-version=6.0&$top={page_size}&$skip={skip}"
        )
        if res.status_code == 429 or res.status_code == 503:
            retry_after = int(res.headers.get('Retry-After', 10))
            print(f"  Task {task_id}: Rate limited ({res.status_code}), retrying in {retry_after}s...")
            time.sleep(retry_after)
            res = session.get(
                f"{base_url}/_apis/wit/workitems/{task_id}/updates?api-version=6.0&$top={page_size}&$skip={skip}"
            )
            if res.status_code != 200:
                raise Exception(f"API retry failed for task {task_id} with status {res.status_code}. Stopping.")
        elif res.status_code != 200:
            print(f"  Task {task_id}: API returned status {res.status_code}, skipping.")
            break

        page = res.json().get('value', [])
        updates.extend(page)
        if len(page) < page_size:
            break
        skip += page_size
    return updates


def get_iterations(base_url, pat, area_path):
    """Fetch iterations tree from API with 1-hour cache."""
    cache = load_iterations_cache()
    if cache and 'timestamp' in cache and 'data' in cache:
        try:
            cached_time = datetime.fromisoformat(cache['timestamp'])
            if (datetime.now() - cached_time).total_seconds() < 3600:
                print("Using cached iterations (less than 1 hour old).")
                return cache['data']
        except:
            pass

    print("Fetching iterations from API...")
    b64_pat = base64.b64encode(f":{pat}".encode('utf-8')).decode('utf-8')
    headers = {'Authorization': f'Basic {b64_pat}'}
    url = f"{base_url}/_apis/wit/classificationnodes/iterations?api-version=6.0&$depth=5"
    resp = requests.get(url, headers=headers, verify=False)
    if resp.status_code == 200:
        data = resp.json()
        save_iterations_cache(data)
        return data
    else:
        print(f"Failed to fetch iterations: {resp.status_code}")
        return None


def _classification_node_paths(node, structure_type):
    options = []
    seen = set()

    def add_option(value):
        option = _normalize_classification_field_path(value, structure_type)
        key = option.casefold()

        if option and key not in seen:
            seen.add(key)
            options.append(option)

    def walk(current):
        add_option(current.get('path') or current.get('name'))
        for child in current.get('children', []):
            walk(child)

    if isinstance(node, list):
        for item in node:
            walk(item)
    elif node:
        walk(node)

    return options


def get_area_options(base_url, pat):
    """Return area paths for the area combo."""
    print("Fetching area paths from API...")
    b64_pat = base64.b64encode(f":{pat}".encode('utf-8')).decode('utf-8')
    headers = {'Authorization': f'Basic {b64_pat}'}
    url = f"{base_url}/_apis/wit/classificationnodes/areas?api-version=6.0&$depth=10"
    resp = requests.get(url, headers=headers, verify=False)
    if resp.status_code == 200:
        return _classification_node_paths(resp.json(), "Area")

    print(f"Failed to fetch areas: {resp.status_code}")
    return []


def get_sprint_options(base_url, pat, area_path):
    """Return date-bearing iteration paths for the sprint combo."""
    options = []
    seen = set()

    def add_option(value):
        option = normalize_iteration_path(value)
        key = option.casefold()
        if option and key not in seen:
            seen.add(key)
            options.append(option)

    def walk(node):
        attributes = node.get('attributes') or {}
        if attributes.get('startDate') and attributes.get('finishDate'):
            add_option(node.get('path') or node.get('name'))

        for child in node.get('children', []):
            walk(child)

    def walk_many(nodes):
        if isinstance(nodes, list):
            for node in nodes:
                walk(node)
        elif nodes:
            walk(nodes)

    b64_pat = base64.b64encode(f":{pat}".encode('utf-8')).decode('utf-8')
    headers = {'Authorization': f'Basic {b64_pat}'}
    try:
        team_iterations, _, _ = _get_team_iterations(base_url, headers, area_path)
        walk_many(team_iterations)
        if options:
            return options
    except Exception as ex:
        print(f"Team sprint lookup failed: {ex}. Falling back to project iterations.")

    iterations = get_iterations(base_url, pat, area_path)
    walk_many(iterations)
    return options


def get_sprint_dates(base_url, pat, area_path, sprint_name):
    print(f"Fetching dates for sprint: {sprint_name}...")
    b64_pat = base64.b64encode(f":{pat}".encode('utf-8')).decode('utf-8')
    headers = {'Authorization': f'Basic {b64_pat}'}
    clean_sprint = normalize_iteration_path(sprint_name)

    def format_dates(attr):
        s = (attr or {}).get('startDate', '').split('T')[0]
        e = (attr or {}).get('finishDate', '').split('T')[0]
        if not s or not e:
            return None, None
        s_br = datetime.strptime(s, "%Y-%m-%d").strftime("%d/%m/%Y")
        e_br = datetime.strptime(e, "%Y-%m-%d").strftime("%d/%m/%Y")
        return s_br, e_br

    def macro_team_name():
        if '(' in clean_sprint and ')' in clean_sprint:
            inner = clean_sprint.split('(', 1)[1].rsplit(')', 1)[0].strip().strip("'\"")
            if inner:
                return inner.split('\\')[-1]
        return area_path.split('\\')[-1].strip() if area_path else ""

    # Handle macros like @CurrentIteration
    if clean_sprint.startswith('@'):
        team_name = macro_team_name()
        clean_base = base_url.rstrip('/')
        candidates = []
        if team_name:
            candidates.append((team_name, f"{clean_base}/{quote(team_name, safe='')}"))
        candidates.append(("default team", clean_base))

        for label, team_base_url in candidates:
            try:
                resp = requests.get(
                    f"{team_base_url}/_apis/work/teamsettings/iterations",
                    headers=headers,
                    params={'$timeframe': 'current', 'api-version': '6.0'},
                    verify=False,
                )
                if resp.status_code == 200:
                    iters = _response_values(resp.json())
                    if iters:
                        s_br, e_br = format_dates(iters[0].get('attributes', {}))
                        if s_br and e_br:
                            print(f"Loaded current iteration dates from {label}: {s_br} to {e_br}")
                            return s_br, e_br
                    print(f"No current iteration dates returned for {label}.")
                else:
                    print(f"Current iteration lookup for {label} returned {resp.status_code}.")
            except Exception as ex:
                print(f"Current iteration lookup for {label} failed: {ex}")

    # Literal search fallback
    url = f"{base_url}/_apis/wit/classificationnodes/iterations?api-version=6.0&$depth=5"
    try:
        response = requests.get(url, headers=headers, verify=False)
        if response.status_code != 200: return None, None

        def find_node(node, target):
            clean_target = target.split("'")[-2] if "'" in target else target
            clean_target = normalize_iteration_path(clean_target)
            path = node.get('path', '')
            field_path = normalize_iteration_path(path)
            name = node.get('name', '')
            attr = node.get('attributes')

            if clean_target.startswith('@'):
                today = datetime.now().date()
                if attr and 'startDate' in attr and 'finishDate' in attr:
                    s = datetime.strptime(attr['startDate'].split('T')[0], "%Y-%m-%d").date()
                    e = datetime.strptime(attr['finishDate'].split('T')[0], "%Y-%m-%d").date()
                    if s <= today <= e:
                        return format_dates(attr)

            if clean_target and (
                clean_target.lower() in path.lower()
                or clean_target.lower() in field_path.lower()
                or clean_target.lower() == name.lower()
            ):
                attr = node.get('attributes')
                if attr and 'startDate' in attr and 'finishDate' in attr:
                    return format_dates(attr)
            for child in node.get('children', []):
                res = find_node(child, target)
                if res and res[0] and res[1]:
                    return res
            return None

        result = find_node(response.json(), clean_sprint)
        return result if result else (None, None)
    except: return None, None


def get_tasks(base_url, pat, area_path, sprint, filter_members=None, progress_callback=None):
    if progress_callback: progress_callback(0.05)
    print(f"Querying Tasks for {sprint}...")
    wiql_url = f"{base_url}/_apis/wit/wiql?api-version=6.0"
    b64_pat = base64.b64encode(f":{pat}".encode('utf-8')).decode('utf-8')
    headers = {'Authorization': f'Basic {b64_pat}', 'Content-Type': 'application/json'}
    wiql_area_path = normalize_area_path(area_path)
    wiql_sprint = normalize_iteration_path(sprint)

    # Resolve @CurrentIteration macro to a literal iteration path if possible
    if wiql_sprint.startswith('@'):
        try:
            iterations_tree = get_iterations(base_url, pat, area_path)
            if iterations_tree:
                today = datetime.now().date()

                def find_current_iteration(node):
                    attr = node.get('attributes', {})
                    if 'startDate' in attr and 'finishDate' in attr:
                        s = datetime.strptime(attr['startDate'].split('T')[0], "%Y-%m-%d").date()
                        e = datetime.strptime(attr['finishDate'].split('T')[0], "%Y-%m-%d").date()
                        if s <= today <= e:
                            return node.get('path')
                    for child in node.get('children', []):
                        result = find_current_iteration(child)
                        if result:
                            return result
                    return None

                # resolved_path = find_current_iteration(iterations_tree)
                # if resolved_path:
                #     resolved_path = resolved_path.lstrip('\\')
                #     print(f"Resolved {sprint} to iteration path: {resolved_path}")
                #     iteration_condition = f"'{resolved_path}'"
                # else:
                #     print(f"Could not resolve current iteration from tree, using macro as-is.")
                iteration_condition = wiql_sprint
            else:
                iteration_condition = wiql_sprint
        except Exception as ex:
            print(f"Error resolving iteration: {ex}. Using macro as-is.")
            iteration_condition = wiql_sprint
    else:
        iteration_condition = _wiql_quote(wiql_sprint)
    member_condition = ""
    if filter_members:
        names_str = ", ".join([_wiql_quote(name) for name in filter_members])
        member_condition = f"AND [System.AssignedTo] IN ({names_str})"

    if wiql_area_path != (area_path or "").strip().lstrip("\\"):
        print(f"Normalized area path for WIQL: {wiql_area_path}")
    if wiql_sprint != (sprint or "").strip().lstrip("\\"):
        print(f"Normalized sprint path for WIQL: {wiql_sprint}")

    wiql_query = {"query": f"SELECT [System.Id] FROM WorkItems WHERE [System.WorkItemType] = 'Task' AND [System.AreaPath] UNDER {_wiql_quote(wiql_area_path)} AND [System.IterationPath] = {iteration_condition} {member_condition}"}

    print(f"WIQL Query: {wiql_query['query']}")
    response = requests.post(wiql_url, headers=headers, json=wiql_query, verify=False)
    if response.status_code != 200: raise Exception(f"API Error: {response.text}")

    task_ids = [str(item['id']) for item in response.json().get('workItems', [])]
    print(f"Found {len(task_ids)} tasks: {task_ids}")
    if progress_callback: progress_callback(0.1)
    return task_ids, headers


def get_members_from_tasks(base_url, headers, area_path, sprint):
    wiql_area_path = normalize_area_path(area_path)
    wiql_sprint = normalize_iteration_path(sprint)
    iteration_condition = _wiql_quote(wiql_sprint) if not wiql_sprint.startswith('@') else wiql_sprint
    wiql_query = {"query": f"SELECT [System.Id] FROM WorkItems WHERE [System.WorkItemType] = 'Task' AND [System.AreaPath] UNDER {_wiql_quote(wiql_area_path)} AND [System.IterationPath] = {iteration_condition}"}

    response = requests.post(f"{base_url}/_apis/wit/wiql?api-version=6.0", headers=headers, json=wiql_query, verify=False)
    if response.status_code != 200: return []

    task_ids = [str(item['id']) for item in response.json().get('workItems', [])]
    members = set()
    for i in range(0, len(task_ids), 200):
        batch = task_ids[i:i+200]
        ids_str = ",".join(batch)
        resp = requests.get(f"{base_url}/_apis/wit/workitems?ids={ids_str}&fields=System.AssignedTo&api-version=6.0", headers=headers, verify=False)
        if resp.status_code == 200:
            for item in resp.json().get('value', []):
                val = item.get('fields', {}).get('System.AssignedTo')
                if val: members.add(val.get('displayName') if isinstance(val, dict) else val)
    return sorted(list(members))


def get_current_work_items(task_ids, base_url, headers):
    """Fetch current work item fields used by the burndown calculation."""
    fields = [
        REMAINING_WORK_FIELD,
        COMPLETED_WORK_FIELD,
        'System.AssignedTo',
        'System.CreatedDate',
        'System.State',
        'System.Title',
    ]
    items = {}
    for i in range(0, len(task_ids), 200):
        batch = task_ids[i:i + 200]
        response = requests.get(
            f"{base_url}/_apis/wit/workitems",
            headers=headers,
            params={
                'ids': ",".join(batch),
                'fields': ",".join(fields),
                'api-version': '6.0',
            },
            verify=False,
        )
        if response.status_code != 200:
            raise Exception(f"Failed to fetch current work items: {response.text}")

        for item in response.json().get('value', []):
            work_fields = item.get('fields', {})
            assigned_to = work_fields.get('System.AssignedTo')
            items[str(item.get('id'))] = {
                'remaining': work_fields.get(REMAINING_WORK_FIELD),
                'completed': work_fields.get(COMPLETED_WORK_FIELD),
                'assigned_to': _identity_name(assigned_to),
                'created_date': work_fields.get('System.CreatedDate'),
                'state': work_fields.get('System.State', ''),
                'title': work_fields.get('System.Title', ''),
            }
    return items


def _team_url_candidates(base_url, area_path):
    clean_base = base_url.rstrip('/')
    team_name = area_path.split('\\')[-1].strip() if area_path else ""
    candidates = []
    if team_name:
        candidates.append((team_name, f"{clean_base}/{quote(team_name, safe='')}"))
    candidates.append(("", clean_base))
    return candidates


def _response_values(payload):
    return payload.get('value') or payload.get('values') or []


def _get_team_iterations(base_url, headers, area_path, timeframe=None):
    params = {'api-version': '6.0'}
    if timeframe:
        params['$timeframe'] = timeframe

    errors = []
    for team_name, team_base_url in _team_url_candidates(base_url, area_path):
        response = requests.get(
            f"{team_base_url}/_apis/work/teamsettings/iterations",
            headers=headers,
            params=params,
            verify=False,
        )
        if response.status_code == 200:
            iterations = _response_values(response.json())
            if iterations:
                return iterations, team_name, team_base_url
            errors.append(f"{team_name or 'default team'} returned no iterations")
        else:
            errors.append(f"{team_name or 'default team'} returned {response.status_code}")

    raise Exception("Could not resolve team iterations. " + "; ".join(errors))


def _iso_date(value):
    return _parse_azure_date(value)


def resolve_team_iteration(base_url, headers, area_path, sprint, start_date=None, end_date=None):
    """Resolve the team settings iteration used by Azure capacity APIs."""
    clean_sprint = normalize_iteration_path(sprint)
    if clean_sprint.startswith('@'):
        iterations, team_name, team_base_url = _get_team_iterations(
            base_url, headers, area_path, timeframe='current'
        )
        iteration = iterations[0]
        print(f"Resolved {clean_sprint} to team iteration: {iteration.get('name')} ({iteration.get('id')})")
        return {**iteration, 'team_name': team_name, 'team_base_url': team_base_url}

    iterations, team_name, team_base_url = _get_team_iterations(base_url, headers, area_path)
    target = clean_sprint.strip().strip("'").strip('\\').casefold()
    s_dt = _parse_br_date(start_date, "Start Date") if start_date else None
    e_dt = _parse_br_date(end_date, "End Date") if end_date else None

    for iteration in iterations:
        name = (iteration.get('name') or "").strip().casefold()
        path = normalize_iteration_path(iteration.get('path')).casefold()
        if target in (name, path) or path.endswith(f"\\{target}") or target.endswith(f"\\{path}"):
            print(f"Resolved sprint to team iteration: {iteration.get('name')} ({iteration.get('id')})")
            return {**iteration, 'team_name': team_name, 'team_base_url': team_base_url}

    if s_dt and e_dt:
        for iteration in iterations:
            attr = iteration.get('attributes', {})
            iter_start = _iso_date(attr.get('startDate'))
            iter_end = _iso_date(attr.get('finishDate'))
            if iter_start == s_dt and iter_end == e_dt:
                print(f"Resolved sprint by dates to team iteration: {iteration.get('name')} ({iteration.get('id')})")
                return {**iteration, 'team_name': team_name, 'team_base_url': team_base_url}

    raise Exception(f"Could not resolve team iteration for sprint '{clean_sprint}'.")


def get_team_capacities(base_url, headers, area_path, sprint, selected_members=None, start_date=None, end_date=None):
    iteration = resolve_team_iteration(base_url, headers, area_path, sprint, start_date, end_date)
    response = requests.get(
        f"{iteration['team_base_url']}/_apis/work/teamsettings/iterations/{iteration['id']}/capacities",
        headers=headers,
        params={'api-version': '6.0'},
        verify=False,
    )
    if response.status_code != 200:
        raise Exception(f"Failed to fetch team capacities: {response.text}")

    capacities = _response_values(response.json())
    if not capacities:
        raise Exception("No capacity records were found for this team iteration.")

    if selected_members:
        selected = {_normalize_name(member) for member in selected_members}

        def capacity_matches(capacity):
            identity = capacity.get('teamMember', {})
            names = {
                _normalize_name(identity.get('displayName')),
                _normalize_name(identity.get('uniqueName')),
            }
            return bool(selected.intersection(names))

        capacities = [capacity for capacity in capacities if capacity_matches(capacity)]
        if not capacities:
            raise Exception("No capacity records were found for the selected squad members.")

    member_names = [_identity_name(capacity.get('teamMember', {})) for capacity in capacities]
    print(f"Loaded capacity for {len(capacities)} member(s): {member_names}")
    return capacities


def _is_day_off(day, days_off):
    for day_off in days_off or []:
        start = _parse_azure_date(day_off.get('start'))
        end = _parse_azure_date(day_off.get('end'))
        if not start or not end:
            continue
        if start <= day <= end:
            return True
    return False


def build_burndown_data(task_updates, current_items, capacities, start_date, end_date, as_of_date=None):
    """Build burndown series from fetched task histories and capacity records."""
    s_dt = _parse_br_date(start_date, "Start Date")
    e_dt = _parse_br_date(end_date, "End Date")
    if s_dt > e_dt:
        raise ValueError("Start Date must be before or equal to End Date.")

    dates = [day for day in _date_range(s_dt, e_dt) if day.weekday() < 5]
    if not dates:
        raise ValueError("The selected burndown period has no working days.")

    daily_actual = defaultdict(float)
    items_not_estimated = 0
    completed_states = {'closed', 'completed', 'done', 'resolved'}
    completed_items = 0

    for task_id, updates in task_updates.items():
        current = current_items.get(str(task_id), {})
        state = _normalize_name(current.get('state'))
        if state in completed_states:
            completed_items += 1

        created_at = _parse_azure_datetime(current.get('created_date'))
        created_date = created_at.date() if created_at else None

        remaining_changes = []
        for update in updates:
            fields = update.get('fields', {})
            if REMAINING_WORK_FIELD not in fields:
                continue
            changed_date = (
                fields.get('System.ChangedDate', {}).get('newValue') or
                fields.get('System.AuthorizedDate', {}).get('newValue')
            )
            changed_at = _parse_azure_datetime(changed_date)
            if not changed_at:
                continue

            remaining_field = fields[REMAINING_WORK_FIELD]
            old_value = _coerce_float(remaining_field.get('oldValue'), 0.0)
            new_value = _coerce_float(remaining_field.get('newValue'), 0.0)
            remaining_changes.append({
                'datetime': changed_at,
                'date': changed_at.date(),
                'old': old_value,
                'new': new_value,
            })

        remaining_changes.sort(key=lambda change: change['datetime'])

        if current.get('remaining') is None and not remaining_changes:
            items_not_estimated += 1

        if remaining_changes:
            running_remaining = remaining_changes[0]['old']
        else:
            running_remaining = _coerce_float(current.get('remaining'), 0.0)

        change_idx = 0
        for day in dates:
            if created_date and day < created_date:
                continue
            while change_idx < len(remaining_changes) and remaining_changes[change_idx]['date'] <= day:
                running_remaining = remaining_changes[change_idx]['new']
                change_idx += 1
            daily_actual[day] += running_remaining

    daily_capacity = defaultdict(float)
    capacity_members = []
    for capacity in capacities:
        identity = capacity.get('teamMember', {})
        capacity_members.append(_identity_name(identity))
        capacity_per_day = sum(_coerce_float(activity.get('capacityPerDay'), 0.0)
                               for activity in capacity.get('activities', []))
        for day in dates:
            if not _is_day_off(day, capacity.get('daysOff', [])):
                daily_capacity[day] += capacity_per_day

    total_capacity = sum(daily_capacity[day] for day in dates)
    remaining_capacity = []
    capacity_left = total_capacity
    for day in dates:
        capacity_left -= daily_capacity[day]
        remaining_capacity.append(round(max(capacity_left, 0.0), 2))
    if remaining_capacity:
        remaining_capacity[-1] = 0.0

    if as_of_date is None:
        cutoff_date = min(datetime.now().date(), e_dt)
    elif hasattr(as_of_date, 'date'):
        cutoff_date = min(as_of_date.date(), e_dt)
    elif isinstance(as_of_date, str):
        cutoff_date = min(_parse_br_date(as_of_date, "As Of Date"), e_dt)
    else:
        cutoff_date = min(as_of_date, e_dt)

    full_actual_remaining = [round(daily_actual[day], 2) for day in dates]
    actual_remaining = [
        value if day <= cutoff_date else None
        for day, value in zip(dates, full_actual_remaining)
    ]
    elapsed_actual = [value for value in actual_remaining if value is not None]

    start_remaining = full_actual_remaining[0] if full_actual_remaining else 0.0
    remaining_work = elapsed_actual[-1] if elapsed_actual else 0.0
    total_scope_increase = remaining_work - start_remaining
    completed_percent = (completed_items / len(current_items) * 100) if current_items else 0.0
    average_burndown = max(start_remaining - remaining_work, 0.0) / len(dates)

    ideal_trend = [
        round(max(start_remaining * (1 - ((idx + 1) / len(dates))), 0.0), 2)
        for idx in range(len(dates))
    ]

    return {
        'dates': dates,
        'actual_remaining': actual_remaining,
        'full_actual_remaining': full_actual_remaining,
        'remaining_capacity': remaining_capacity,
        'ideal_trend': ideal_trend,
        'daily_capacity': [round(daily_capacity[day], 2) for day in dates],
        'capacity_members': capacity_members,
        'summary': {
            'start_date': s_dt,
            'end_date': e_dt,
            'completed_percent': round(completed_percent, 2),
            'average_burndown': round(average_burndown, 2),
            'items_not_estimated': items_not_estimated,
            'remaining_work': round(remaining_work, 2),
            'total_scope_increase': round(total_scope_increase, 2),
            'total_capacity': round(total_capacity, 2),
            'actual_through_date': dates[len(elapsed_actual) - 1] if elapsed_actual else None,
        },
    }


def get_burndown_data(task_ids, base_url, headers, area_path, sprint, selected_members=None,
                      start_date=None, end_date=None, progress_callback=None):
    """Fetch Azure DevOps data and build a burndown payload for plotting."""
    _parse_br_date(start_date, "Start Date")
    _parse_br_date(end_date, "End Date")

    if progress_callback:
        progress_callback(0.15)
    current_items = get_current_work_items(task_ids, base_url, headers)

    if progress_callback:
        progress_callback(0.25)
    capacities = get_team_capacities(
        base_url, headers, area_path, sprint,
        selected_members=selected_members,
        start_date=start_date,
        end_date=end_date,
    )

    print(f"Fetching burndown history for {len(task_ids)} task(s)...")
    session = requests.Session()
    session.verify = False
    session.headers.update(headers)

    task_updates = {}
    total = len(task_ids)
    processed = 0
    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
        future_to_task = {executor.submit(_fetch_task_updates, session, base_url, task_id): task_id
                          for task_id in task_ids}
        for future in concurrent.futures.as_completed(future_to_task):
            processed += 1
            if progress_callback:
                progress_callback(0.25 + (processed / total) * 0.65)
            task_id = future_to_task[future]
            try:
                task_updates[task_id] = future.result()
            except Exception as exc:
                print(f"  Task {task_id} generated an exception: {exc}")
                task_updates[task_id] = []

    if progress_callback:
        progress_callback(0.95)
    return build_burndown_data(task_updates, current_items, capacities, start_date, end_date)


def get_work_history(task_ids, base_url, headers, start_date=None, end_date=None, progress_callback=None):
    person_daily_data = defaultdict(lambda: defaultdict(lambda: {'completed': 0.0, 'remaining_dec': 0.0}))
    worker_text_logs = defaultdict(list)
    total = len(task_ids)

    try:
        s_dt = datetime.strptime(start_date, "%d/%m/%Y").date() if start_date else None
        e_dt = datetime.strptime(end_date, "%d/%m/%Y").date() if end_date else None
    except:
        print("Warning: Date parsing failed. Use DD/MM/YYYY.")
        s_dt, e_dt = None, None

    print(f"Calculating work for {total} tasks in period {start_date} to {end_date}...")

    session = requests.Session()
    session.verify = False
    session.headers.update(headers)

    def process_task(task_id):
        # Paginate through ALL updates — the API returns max 200 per call
        updates = []
        skip = 0
        page_size = 200
        while True:
            res = session.get(
                f"{base_url}/_apis/wit/workitems/{task_id}/updates?api-version=6.0&$top={page_size}&$skip={skip}"
            )
            if res.status_code == 429 or res.status_code == 503:
                retry_after = int(res.headers.get('Retry-After', 10))
                print(f"  Task {task_id}: Rate limited ({res.status_code}), retrying in {retry_after}s...")
                time.sleep(retry_after)
                res = session.get(
                    f"{base_url}/_apis/wit/workitems/{task_id}/updates?api-version=6.0&$top={page_size}&$skip={skip}"
                )
                if res.status_code != 200:
                    raise Exception(f"API retry failed for task {task_id} with status {res.status_code}. Stopping.")
            elif res.status_code != 200:
                print(f"  Task {task_id}: API returned status {res.status_code}, skipping.")
                break
            page = res.json().get('value', [])
            updates.extend(page)
            if len(page) < page_size:
                break  # Last page
            skip += page_size

        if not updates:
            return task_id, []

        if len(updates) > page_size:
            print(f"  Task {task_id}: Fetched {len(updates)} updates (paginated)")

        # Track assignee as it evolves through each update (chronological order)
        # so each field change is attributed to the person assigned at that point in time
        running_assignee = "Unassigned"
        task_changes = []
        for up in updates:
            f = up.get('fields', {})

            # Update assignee tracking BEFORE processing field changes
            # so the assignee is correct for changes made in this same update
            if 'System.AssignedTo' in f:
                val = f['System.AssignedTo'].get('newValue')
                if val:
                    running_assignee = (val.get('displayName') if isinstance(val, dict) else val) or running_assignee

            if COMPLETED_WORK_FIELD in f or REMAINING_WORK_FIELD in f:
                d_str = f.get('System.ChangedDate', {}).get('newValue') or f.get('System.AuthorizedDate', {}).get('newValue')
                if d_str:
                    dt = datetime.fromisoformat(d_str.replace('Z', '+00:00'))
                    local_dt = dt.astimezone()
                    date_k = local_dt.date()

                    if s_dt and date_k < s_dt: continue
                    if e_dt and date_k > e_dt: continue

                    change = {'datetime': local_dt, 'date': date_k, 'assignee': running_assignee}
                    if COMPLETED_WORK_FIELD in f:
                        change['comp_old'] = f[COMPLETED_WORK_FIELD].get('oldValue', 0) or 0
                        change['comp_new'] = f[COMPLETED_WORK_FIELD].get('newValue', 0) or 0
                    if REMAINING_WORK_FIELD in f:
                        change['rem_old'] = f[REMAINING_WORK_FIELD].get('oldValue', 0) or 0
                        change['rem_new'] = f[REMAINING_WORK_FIELD].get('newValue', 0) or 0
                    task_changes.append(change)

        if not task_changes:
            print(f"  Task {task_id}: No work field changes in date range.")
        return task_id, task_changes

    # Use a ThreadPoolExecutor to fetch tasks concurrently
    processed = 0
    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
        future_to_task = {executor.submit(process_task, t): t for t in task_ids}
        for future in concurrent.futures.as_completed(future_to_task):
            processed += 1
            if progress_callback: progress_callback(0.1 + (processed / total) * 0.85)
            if processed % 10 == 0: print(f"Processing {processed}/{total}...")

            try:
                task_id, task_changes = future.result()
            except Exception as exc:
                print(f"  Task generated an exception: {exc}")
                continue

            if not task_changes:
                continue

            task_changes.sort(key=lambda x: x['datetime'])

            for ch in task_changes:
                date_k = ch['date']
                assignee = ch['assignee']
                if 'comp_old' in ch:
                    diff = ch['comp_new'] - ch['comp_old']
                    if diff != 0:
                        person_daily_data[assignee][date_k]['completed'] += diff
                        worker_text_logs[assignee].append(f"[{date_k}] Task {task_id} (COMPLETED) | {ch['comp_old']} -> {ch['comp_new']} = {round(diff, 2)} hours")
                        print(f"  Task {task_id}: {assignee} | Completed {ch['comp_old']} -> {ch['comp_new']} ({round(diff, 2)}h) on {date_k}")
                if 'rem_old' in ch:
                    decr = ch['rem_old'] - ch['rem_new']
                    if decr != 0:
                        person_daily_data[assignee][date_k]['remaining_dec'] += decr
                        worker_text_logs[assignee].append(f"[{date_k}] Task {task_id} (REMAINING) | {ch['rem_old']} -> {ch['rem_new']} = Decrease of {round(decr, 2)} hours")
                        print(f"  Task {task_id}: {assignee} | Remaining {ch['rem_old']} -> {ch['rem_new']} (decr {round(decr, 2)}h) on {date_k}")

    # Save worker text logs
    print("Saving worker text logs...")

    path_logs = "logs/txt"
    Path(path_logs).mkdir(parents=True, exist_ok=True)

    for person, logs in worker_text_logs.items():
        safe_name = "".join(c for c in person if c.isalnum() or c in (' ', '_')).replace(' ', '_').lower()
        filename = f"{path_logs}/log_{safe_name}.txt"
        logs.sort()
        try:
            with open(filename, 'w', encoding='utf-8') as f:
                f.write(f"--- Sprint Alterations Log: {person} ---\n")
                f.write(f"Generated on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
                for log_line in logs: f.write(log_line + "\n")
            print(f"Created log: {filename}")
        except Exception as e:
            print(f"Failed to write log for {person}: {e}")

    cleaned = defaultdict(dict)
    for p, days in person_daily_data.items():
        for d, m in days.items():
            if m['completed'] != 0 or m['remaining_dec'] != 0: cleaned[p][d] = m
    return cleaned
