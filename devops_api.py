import base64
import time
from collections import defaultdict
from datetime import datetime

import requests
import urllib3

import concurrent.futures

from config import (
    COMPLETED_WORK_FIELD,
    REMAINING_WORK_FIELD,
    load_iterations_cache,
    save_iterations_cache,
)

# Disable SSL Warnings
urllib3.disable_warnings()


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


def get_sprint_dates(base_url, pat, area_path, sprint_name):
    print(f"Fetching dates for sprint: {sprint_name}...")
    b64_pat = base64.b64encode(f":{pat}".encode('utf-8')).decode('utf-8')
    headers = {'Authorization': f'Basic {b64_pat}'}

    # Handle macros like @CurrentIteration
    if sprint_name.startswith('@'):
        team_name = area_path.split('\\')[-1]
        url = f"{base_url}/{team_name}/_apis/work/teamsettings/iterations?$timeframe=current&api-version=6.0"
        try:
            resp = requests.get(url, headers=headers, verify=False)
            if resp.status_code == 200:
                iters = resp.json().get('value', [])
                if iters:
                    attr = iters[0].get('attributes', {})
                    s = attr.get('startDate', '').split('T')[0]
                    e = attr.get('finishDate', '').split('T')[0]
                    if s and e:
                        # Convert to BR format
                        s_br = datetime.strptime(s, "%Y-%m-%d").strftime("%d/%m/%Y")
                        e_br = datetime.strptime(e, "%Y-%m-%d").strftime("%d/%m/%Y")
                        return s_br, e_br
        except: pass

    # Literal search fallback
    url = f"{base_url}/_apis/wit/classificationnodes/iterations?api-version=6.0&$depth=5"
    try:
        response = requests.get(url, headers=headers, verify=False)
        if response.status_code != 200: return None, None

        def find_node(node, target):
            clean_target = target.split("'")[-2] if "'" in target else target
            if clean_target.lower() in node.get('path', '').lower() or clean_target.lower() == node.get('name', '').lower():
                attr = node.get('attributes')
                if attr and 'startDate' in attr and 'finishDate' in attr:
                    s = datetime.strptime(attr['startDate'].split('T')[0], "%Y-%m-%d").strftime("%d/%m/%Y")
                    e = datetime.strptime(attr['finishDate'].split('T')[0], "%Y-%m-%d").strftime("%d/%m/%Y")
                    return s, e
            for child in node.get('children', []):
                res = find_node(child, target)
                if res: return res
            return None, None

        return find_node(response.json(), sprint_name)
    except: return None, None


def get_tasks(base_url, pat, area_path, sprint, filter_members=None, progress_callback=None):
    if progress_callback: progress_callback(0.05)
    print(f"Querying Tasks for {sprint}...")
    wiql_url = f"{base_url}/_apis/wit/wiql?api-version=6.0"
    b64_pat = base64.b64encode(f":{pat}".encode('utf-8')).decode('utf-8')
    headers = {'Authorization': f'Basic {b64_pat}', 'Content-Type': 'application/json'}

    # Resolve @CurrentIteration macro to a literal iteration path if possible
    if sprint.startswith('@'):
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
                iteration_condition = sprint
            else:
                iteration_condition = sprint
        except Exception as ex:
            print(f"Error resolving iteration: {ex}. Using macro as-is.")
            iteration_condition = sprint
    else:
        iteration_condition = f"'{sprint}'"
    member_condition = ""
    if filter_members:
        names_str = ", ".join([f"'{name}'" for name in filter_members])
        member_condition = f"AND [System.AssignedTo] IN ({names_str})"

    wiql_query = {"query": f"SELECT [System.Id] FROM WorkItems WHERE [System.WorkItemType] = 'Task' AND [System.AreaPath] UNDER '{area_path}' AND [System.IterationPath] = {iteration_condition} {member_condition}"}

    print(f"WIQL Query: {wiql_query['query']}")
    response = requests.post(wiql_url, headers=headers, json=wiql_query, verify=False)
    if response.status_code != 200: raise Exception(f"API Error: {response.text}")

    task_ids = [str(item['id']) for item in response.json().get('workItems', [])]
    print(f"Found {len(task_ids)} tasks: {task_ids}")
    if progress_callback: progress_callback(0.1)
    return task_ids, headers


def get_members_from_tasks(base_url, headers, area_path, sprint):
    iteration_condition = f"'{sprint}'" if not sprint.startswith('@') else sprint
    wiql_query = {"query": f"SELECT [System.Id] FROM WorkItems WHERE [System.WorkItemType] = 'Task' AND [System.AreaPath] UNDER '{area_path}' AND [System.IterationPath] = {iteration_condition}"}

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
    for person, logs in worker_text_logs.items():
        safe_name = "".join(c for c in person if c.isalnum() or c in (' ', '_')).replace(' ', '_').lower()
        filename = f"log_{safe_name}.txt"
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
