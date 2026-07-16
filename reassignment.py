import base64
from datetime import datetime
import requests
import urllib3
import concurrent.futures
import requests
import urllib3

from demo_data import get_demo_reassignments, is_demo_url

urllib3.disable_warnings()


def get_reassignments(task_ids, base_url, headers, start_date=None, end_date=None, progress_callback=None):
    """Extract all AssignedTo reassignments from task update history."""
    if is_demo_url(base_url):
        return get_demo_reassignments(task_ids, start_date, end_date, progress_callback)

    reassignments = []
    total = len(task_ids)

    try:
        s_dt = datetime.strptime(start_date, "%d/%m/%Y").date() if start_date else None
        e_dt = datetime.strptime(end_date, "%d/%m/%Y").date() if end_date else None
    except:
        print("Warning: Date parsing failed. Use DD/MM/YYYY.")
        s_dt, e_dt = None, None

    print(f"Fetching reassignments for {total} tasks...")

    session = requests.Session()
    session.verify = False
    session.headers.update(headers)

    def process_task(task_id):
        # Paginate through ALL updates
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
                import time
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

        task_reassignments = []
        # Extract AssignedTo changes
        for up in updates:
            f = up.get('fields', {})
            if 'System.AssignedTo' not in f:
                continue

            assigned_change = f['System.AssignedTo']
            old_val = assigned_change.get('oldValue')
            new_val = assigned_change.get('newValue')

            # Get display names
            from_name = ""
            if old_val:
                from_name = old_val.get('displayName') if isinstance(old_val, dict) else old_val
            to_name = ""
            if new_val:
                to_name = new_val.get('displayName') if isinstance(new_val, dict) else new_val

            # Skip if no actual change
            if from_name == to_name:
                continue

            # Get change date
            d_str = (f.get('System.ChangedDate', {}).get('newValue') or
                     f.get('System.AuthorizedDate', {}).get('newValue'))
            change_date = None
            if d_str:
                try:
                    dt = datetime.fromisoformat(d_str.replace('Z', '+00:00'))
                    change_date = dt.astimezone()
                except:
                    change_date = None

            # Filter by date range
            if change_date:
                date_only = change_date.date()
                if s_dt and date_only < s_dt:
                    continue
                if e_dt and date_only > e_dt:
                    continue

            # Get who made the change
            revised_by = up.get('revisedBy', {})
            changed_by = revised_by.get('displayName', 'Unknown') if isinstance(revised_by, dict) else 'Unknown'

            task_reassignments.append({
                'task_id': task_id,
                'from': from_name or '(Unassigned)',
                'to': to_name or '(Unassigned)',
                'date': change_date.strftime('%d/%m/%Y %H:%M') if change_date else 'Unknown',
                'date_sort': change_date if change_date else datetime.min.replace(tzinfo=None),
                'changed_by': changed_by
            })
        return task_reassignments

    # Use a ThreadPoolExecutor to fetch tasks concurrently
    processed = 0
    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
        future_to_task = {executor.submit(process_task, t): t for t in task_ids}
        for future in concurrent.futures.as_completed(future_to_task):
            processed += 1
            if progress_callback: progress_callback(0.1 + (processed / total) * 0.85)
            if processed % 10 == 0: print(f"Processing reassignments {processed}/{total}...")

            try:
                result = future.result()
                reassignments.extend(result)
            except Exception as exc:
                print(f"  Task generated an exception: {exc}")

    # Sort by date, newest first
    reassignments.sort(key=lambda x: x.get('date_sort', datetime.min), reverse=True)
    print(f"Found {len(reassignments)} reassignments.")
    return reassignments
