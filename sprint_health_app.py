import customtkinter as ctk
import requests
import base64
import matplotlib.pyplot as plt
from tkinter import messagebox
from datetime import datetime
from collections import defaultdict
import urllib3
import sys
import json
import os
import threading

# Disable SSL Warnings
urllib3.disable_warnings()

COMPLETED_WORK_FIELD = 'Microsoft.VSTS.Scheduling.CompletedWork'
REMAINING_WORK_FIELD = 'Microsoft.VSTS.Scheduling.RemainingWork'
CONFIG_FILE = 'devops_config.json'
MEMBERS_CACHE_FILE = 'members_cache.json'

# Set UI Theme
ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")

class RedirectText:
    def __init__(self, text_widget):
        self.output = text_widget

    def write(self, string):
        self.output.insert("end", string)
        self.output.see("end")

    def flush(self):
        pass

# --- CONFIGURATION LOGIC ---
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

# --- AZURE DEVOPS LOGIC ---
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

    iteration_condition = f"'{sprint}'" if not sprint.startswith('@') else sprint
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
    
    for idx, task_id in enumerate(task_ids):
        if progress_callback: progress_callback(0.1 + (idx / total) * 0.85)
        
        if idx % 10 == 0: print(f"Processing {idx}/{total}...")
        
        # Paginate through ALL updates — the API returns max 200 per call
        updates = []
        skip = 0
        page_size = 200
        while True:
            res = requests.get(
                f"{base_url}/_apis/wit/workitems/{task_id}/updates?api-version=6.0&$top={page_size}&$skip={skip}",
                headers=headers, verify=False
            )
            if res.status_code != 200:
                print(f"  Task {task_id}: API returned status {res.status_code}, skipping.")
                break
            page = res.json().get('value', [])
            updates.extend(page)
            if len(page) < page_size:
                break  # Last page
            skip += page_size
        
        if not updates:
            continue
        
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

def plot_graphs_per_person(data):
    plt.close('all')
    if not data: return print("No data to plot.")
    
    for person, daily in data.items():
        dates = sorted(daily.keys())
        labels = [d.strftime('%d/%m') for d in dates]
        comp = [daily[d]['completed'] for d in dates]
        rem = [daily[d]['remaining_dec'] for d in dates]
        
        fig, ax = plt.subplots(figsize=(12, 6))
        x = range(len(dates))
        rects1 = ax.bar([i-0.2 for i in x], comp, 0.4, label='Comp. Added', color='#2ecc71')
        rects2 = ax.bar([i+0.2 for i in x], rem, 0.4, label='Rem. Decr.', color='#3498db')
        
        def autolabel(rects):
            for rect in rects:
                height = rect.get_height()
                if height != 0:
                    ax.annotate(f'{round(height, 2)}',
                                xy=(rect.get_x() + rect.get_width() / 2, height),
                                xytext=(0, 3 if height > 0 else -13),
                                textcoords="offset points",
                                ha='center', va='bottom' if height > 0 else 'top',
                                fontsize=9, fontweight='bold')

        autolabel(rects1)
        autolabel(rects2)

        ax.set_title(f"Sprint Health: {person}", fontsize=14, fontweight='bold')
        ax.set_xticks(x)
        ax.set_xticklabels(labels, rotation=45)
        ax.legend()
        plt.tight_layout()
        plt.grid(True, alpha=0.3)
        
        safe_name = "".join(c for c in person if c.isalnum() or c in (' ', '_')).replace(' ', '_').lower()
        plt.savefig(f"sprint_health_{safe_name}.png")
        print(f"Saved graph: sprint_health_{safe_name}.png")
        plt.show(block=False)
    plt.show()

# --- MODERN GUI ---
class DevOpsApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("DevOps Sprint Health Pro")
        self.geometry("1000x900")
        
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        # Left Sidebar for inputs
        self.sidebar = ctk.CTkFrame(self, width=350, corner_radius=0)
        self.sidebar.grid(row=0, column=0, rowspan=2, sticky="nsew", padx=0, pady=0)
        
        ctk.CTkLabel(self.sidebar, text="CONFIGURATION", font=ctk.CTkFont(size=20, weight="bold")).pack(pady=20)
        
        config = load_config()
        self.url_entry = self._create_input("Server URL", config.get("url", "https://devops.example.invalid/REDACTED"))
        self.area_entry = self._create_input("Area Path", config.get("area", r"REDACTED_PROJECT\REDACTED_TEAM"))
        self.sprint_entry = self._create_input("Sprint", config.get("sprint", "@CurrentIteration"))
        self.token_entry = self._create_input("PAT Token", config.get("token", ""), is_password=True)

        # Date Filter Area
        date_frame = ctk.CTkFrame(self.sidebar, fg_color="transparent")
        date_frame.pack(padx=20, fill="x", pady=10)
        
        self.start_date_entry = self._create_input_in_frame(date_frame, "Start Date (DD/MM/YYYY)", config.get("start_date", ""))
        self.end_date_entry = self._create_input_in_frame(date_frame, "End Date (DD/MM/YYYY)", config.get("end_date", ""))
        
        self.load_dates_btn = ctk.CTkButton(self.sidebar, text="📅 Load Sprint Dates", command=self.load_sprint_dates, fg_color="#444", hover_color="#555")
        self.load_dates_btn.pack(pady=5, padx=20, fill="x")

        self.progress_bar = ctk.CTkProgressBar(self.sidebar)
        self.progress_bar.pack(pady=(20, 5), padx=20, fill="x")
        self.progress_bar.set(0)

        self.gen_btn = ctk.CTkButton(self.sidebar, text="GENERATE GRAPHICS", command=self.start_extraction_thread, height=45, font=ctk.CTkFont(weight="bold"))
        self.gen_btn.pack(pady=10, padx=20, fill="x")

        # Right Content Area
        self.content = ctk.CTkFrame(self, corner_radius=15, fg_color="transparent")
        self.content.grid(row=0, column=1, sticky="nsew", padx=20, pady=20)
        self.content.grid_columnconfigure(0, weight=1)
        self.content.grid_rowconfigure(2, weight=1)

        # Member Selection Area
        ctk.CTkLabel(self.content, text="TEAM MEMBERS SELECTION", font=ctk.CTkFont(size=16, weight="bold")).grid(row=0, column=0, sticky="w", pady=(0, 10))
        
        self.select_all_var = ctk.BooleanVar(value=False)
        self.select_all_cb = ctk.CTkCheckBox(self.content, text="Select All", variable=self.select_all_var, command=self._toggle_all_members, font=ctk.CTkFont(size=13, weight="bold"))
        self.select_all_cb.grid(row=1, column=0, sticky="w", pady=(0, 5), padx=5)

        self.member_frame = ctk.CTkScrollableFrame(self.content, height=400, label_text="Select members to include...")
        self.member_frame.grid(row=2, column=0, sticky="nsew")
        
        self.sync_btn = ctk.CTkButton(self.content, text="↻ SYNC TEAM FROM DEVOPS", command=self.sync_members, fg_color="#444", hover_color="#555")
        self.sync_btn.grid(row=3, column=0, sticky="ew", pady=10)

        # Log Window
        ctk.CTkLabel(self.content, text="SYSTEM LOG", font=ctk.CTkFont(size=14, weight="bold")).grid(row=4, column=0, sticky="w", pady=(10, 0))
        self.log_text = ctk.CTkTextbox(self.content, height=200, font=("Consolas", 12))
        self.log_text.grid(row=5, column=0, sticky="ew", pady=(5, 0))

        sys.stdout = RedirectText(self.log_text)
        
        self.member_list = load_members_cache()
        self.selected_vars = {}
        self._populate_members()

    def _create_input(self, label, default, is_password=False):
        ctk.CTkLabel(self.sidebar, text=label).pack(padx=20, anchor="w", pady=(10, 0))
        entry = ctk.CTkEntry(self.sidebar, placeholder_text=label, show="*" if is_password else "")
        entry.insert(0, default)
        entry.pack(padx=20, fill="x", pady=(2, 10))
        return entry

    def _create_input_in_frame(self, frame, label, default):
        ctk.CTkLabel(frame, text=label, font=ctk.CTkFont(size=11)).pack(anchor="w")
        entry = ctk.CTkEntry(frame, placeholder_text=label)
        entry.insert(0, default)
        entry.pack(fill="x", pady=(2, 10))
        return entry

    def _populate_members(self):
        for child in self.member_frame.winfo_children(): child.destroy()
        self.selected_vars = {}
        for member in self.member_list:
            var = ctk.BooleanVar(value=False)
            cb = ctk.CTkCheckBox(self.member_frame, text=member, variable=var)
            cb.pack(fill="x", padx=10, pady=5)
            self.selected_vars[member] = var

    def _toggle_all_members(self):
        new_state = self.select_all_var.get()
        for var in self.selected_vars.values():
            var.set(new_state)

    def load_sprint_dates(self):
        url, area, sprint, token = self.url_entry.get(), self.area_entry.get(), self.sprint_entry.get(), self.token_entry.get()
        if not token: return messagebox.showwarning("Error", "Enter PAT")
        
        def do_load():
            s, e = get_sprint_dates(url, token, area, sprint)
            if s and e:
                self.after(0, lambda: self.start_date_entry.delete(0, "end"))
                self.after(0, lambda: self.start_date_entry.insert(0, s))
                self.after(0, lambda: self.end_date_entry.delete(0, "end"))
                self.after(0, lambda: self.end_date_entry.insert(0, e))
                print(f"Loaded dates (BR): {s} to {e}")
            else:
                print("Could not find dates for this sprint or macro.")
        
        threading.Thread(target=do_load, daemon=True).start()

    def sync_members(self):
        url, area, sprint, token = self.url_entry.get(), self.area_entry.get(), self.sprint_entry.get(), self.token_entry.get()
        if not token: return messagebox.showwarning("Error", "Enter PAT")
        self.sync_btn.configure(state="disabled", text="Syncing...")
        
        def do_sync():
            try:
                _, headers = get_tasks(url, token, area, sprint)
                self.member_list = get_members_from_tasks(url, headers, area, sprint)
                save_members_cache(self.member_list)
                self.after(0, self._populate_members)
                print(f"Synced {len(self.member_list)} members.")
            except Exception as e:
                self.after(0, lambda: messagebox.showerror("Error", str(e)))
            finally:
                self.after(0, lambda: self.sync_btn.configure(state="normal", text="↻ SYNC TEAM FROM DEVOPS"))
        
        threading.Thread(target=do_sync, daemon=True).start()

    def start_extraction_thread(self):
        selected = [m for m, v in self.selected_vars.items() if v.get()]
        url, area, sprint, token = self.url_entry.get(), self.area_entry.get(), self.sprint_entry.get(), self.token_entry.get()
        start_date, end_date = self.start_date_entry.get(), self.end_date_entry.get()
        
        if not token: return messagebox.showwarning("Error", "Missing PAT Token")
        
        save_config(url, area, sprint, token, start_date, end_date)
        self.gen_btn.configure(state="disabled", text="PROCESSING...")
        self.progress_bar.set(0)
        self.log_text.delete("1.0", "end")
        
        threading.Thread(target=self.run_extraction, args=(url, area, sprint, token, selected, start_date, end_date), daemon=True).start()

    def update_progress(self, val):
        self.after(0, lambda: self.progress_bar.set(val))

    def run_extraction(self, url, area, sprint, token, selected, start_date, end_date):
        try:
            ids, headers = get_tasks(url, token, area, sprint, filter_members=selected, progress_callback=self.update_progress)
            if ids:
                data = get_work_history(ids, url, headers, start_date=start_date, end_date=end_date, progress_callback=self.update_progress)
                self.update_progress(1.0)
                self.after(0, lambda: plot_graphs_per_person(data))
            else:
                print("No tasks found.")
                self.update_progress(1.0)
        except Exception as e:
            self.after(0, lambda: messagebox.showerror("Error", str(e)))
        finally:
            self.after(0, lambda: self.gen_btn.configure(state="normal", text="GENERATE GRAPHICS"))

if __name__ == "__main__":
    app = DevOpsApp()
    app.mainloop()
