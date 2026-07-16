import os
import sys
import threading
from tkinter import messagebox

import customtkinter as ctk

from charts.burndown import plot_burndown
from charts.time_registration import generate_all_output
from config import (
    load_combos_cache,
    load_config,
    load_members_cache,
    save_combos_cache,
    save_config,
    save_members_cache,
)
from demo_data import is_demo_url
from devops_api import (
    build_auth_headers,
    get_area_options,
    get_historical_burndown_data,
    get_historical_work_history,
    get_members_from_tasks,
    get_sprint_options,
    get_sprint_dates,
    get_tasks,
    normalize_area_path,
    normalize_iteration_path,
)
from enums import Graphic_Type
from reassignment import get_reassignments
from ui.helpers import RedirectText, build_combo_values, build_sprint_combo_values
from ui.reassignment_view import populate_reassignment_table
from ui.viewers import BurndownViewerWindow, ImageViewerWindow

# Set UI Theme
ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")


class DevOpsApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("DevOps Sprint Health Pro")
        self.geometry("1100x900")

        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        # Left Sidebar for inputs
        self.sidebar = ctk.CTkFrame(self, width=350, corner_radius=0)
        self.sidebar.grid(row=0, column=0, rowspan=2, sticky="nsew", padx=0, pady=0)

        ctk.CTkLabel(self.sidebar, text="CONFIGURATION", font=ctk.CTkFont(size=20, weight="bold")).pack(pady=20)

        config = load_config()
        combos_cache = load_combos_cache()
        self.url_entry = self._create_input("Server URL", config.get("url", ""))
        self.load_combos_btn = ctk.CTkButton(self.sidebar, text="Load Combos", command=self.load_combos, fg_color="#444", hover_color="#555")
        self.load_combos_btn.pack(pady=5, padx=20, fill="x")

        self.area_entry = self._create_combo_input("Area Path", config.get("area", r""), combos_cache.get("areas"))
        self.sprint_entry = self._create_combo_input("Sprint", config.get("sprint"), combos_cache.get("sprints"))
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

        # ===== Right Content Area with Tabs =====
        self.content = ctk.CTkFrame(self, corner_radius=15, fg_color="transparent")
        self.content.grid(row=0, column=1, sticky="nsew", padx=20, pady=20)
        self.content.grid_columnconfigure(0, weight=1)
        self.content.grid_rowconfigure(0, weight=1)

        self.tabview = ctk.CTkTabview(self.content)
        self.tabview.grid(row=0, column=0, sticky="nsew")

        # --- Tab 1: Sprint Health ---
        self.tab_sprint = self.tabview.add("Sprint Health")
        self.tab_sprint.grid_columnconfigure(0, weight=1)
        self.tab_sprint.grid_rowconfigure(4, weight=1)

        # Graphic Type
        ctk.CTkLabel(self.tab_sprint, text="GRAPHIC TYPE", font=ctk.CTkFont(size=16, weight="bold")).grid(row=0, column=0, sticky="w", pady=(0, 10))
        self.graphic_type = ctk.CTkOptionMenu(self.tab_sprint, values=[Graphic_Type.TimesRegistering.description, Graphic_Type.Burndown.description])
        self.graphic_type.set(Graphic_Type.TimesRegistering.description)
        self.graphic_type.grid(row=1, column=0, sticky="ew", pady=(0, 15), padx=5)

        # Member Selection Area
        ctk.CTkLabel(self.tab_sprint, text="TEAM MEMBERS SELECTION", font=ctk.CTkFont(size=16, weight="bold")).grid(row=2, column=0, sticky="w", pady=(5, 10))

        self.select_all_var = ctk.BooleanVar(value=False)
        self.select_all_cb = ctk.CTkCheckBox(self.tab_sprint, text="Select All", variable=self.select_all_var, command=self._toggle_all_members, font=ctk.CTkFont(size=13, weight="bold"))
        self.select_all_cb.grid(row=3, column=0, sticky="w", pady=(0, 5), padx=5)

        self.member_frame = ctk.CTkScrollableFrame(self.tab_sprint, height=400)
        self.member_frame.grid(row=4, column=0, sticky="nsew")

        self.sync_btn = ctk.CTkButton(self.tab_sprint, text="↻ SYNC TEAM FROM DEVOPS", command=self.sync_members, fg_color="#444", hover_color="#555")
        self.sync_btn.grid(row=5, column=0, sticky="ew", pady=10)

        # --- Tab 2: Reassignments ---
        self.tab_reassign = self.tabview.add("Reassignments")
        self.tab_reassign.grid_columnconfigure(0, weight=1)
        self.tab_reassign.grid_rowconfigure(2, weight=1)

        # Reassignment controls
        reassign_controls = ctk.CTkFrame(self.tab_reassign, fg_color="transparent")
        reassign_controls.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        reassign_controls.grid_columnconfigure(1, weight=1)

        self.load_reassign_btn = ctk.CTkButton(reassign_controls, text="🔄 LOAD REASSIGNMENTS",
                                                command=self.start_reassignment_thread, height=40,
                                                font=ctk.CTkFont(weight="bold"))
        self.load_reassign_btn.grid(row=0, column=0, padx=(0, 10))

        self.reassign_count_label = ctk.CTkLabel(reassign_controls, text="", font=ctk.CTkFont(size=12))
        self.reassign_count_label.grid(row=0, column=1, sticky="w")

        # Reassignment table header
        header_frame = ctk.CTkFrame(self.tab_reassign, fg_color="#2b2b2b", corner_radius=8, height=10)
        header_frame.grid(row=1, column=0, sticky="new", padx=(0, 16), pady=(0, 0))
        header_frame.grid_propagate(False)

        headers = ["Task ID", "From", "To", "Date", "Changed By"]
        header_colors = ["#e74c3c", "#e67e22", "#2ecc71", "#3498db", "#9b59b6"]

        self.rel_x = [0.0, 0.10, 0.35, 0.60, 0.75]
        self.rel_w = [0.10, 0.25, 0.25, 0.15, 0.25]

        for i, (h, c) in enumerate(zip(headers, header_colors)):
            lbl = ctk.CTkLabel(header_frame, text=h, font=ctk.CTkFont(size=12, weight="bold"),
                               text_color=c, anchor="center")
            lbl.place(relx=self.rel_x[i], rely=0.5, relwidth=self.rel_w[i], anchor="w")

        # Reassignment table body (scrollable)
        self.reassign_table = ctk.CTkScrollableFrame(self.tab_reassign, label_text="")
        self.reassign_table.grid(row=2, column=0, sticky="nsew", pady=(0, 0))
        self.reassign_table.grid_columnconfigure(0, weight=1)

        # --- Shared Log Window (below tabs) ---
        log_frame = ctk.CTkFrame(self.content, fg_color="transparent")
        log_frame.grid(row=1, column=0, sticky="ew", pady=(10, 0))
        log_frame.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(log_frame, text="SYSTEM LOG", font=ctk.CTkFont(size=14, weight="bold")).grid(row=0, column=0, sticky="w")
        self.log_text = ctk.CTkTextbox(log_frame, height=180, font=("Consolas", 12))
        self.log_text.grid(row=1, column=0, sticky="ew", pady=(5, 0))

        sys.stdout = RedirectText(self.log_text)

        self.member_list = load_members_cache()
        self.selected_vars = {}
        self._populate_members()

        # Image viewer reference
        self._image_viewer = None

    def _create_input(self, label, default, is_password=False):
        ctk.CTkLabel(self.sidebar, text=label).pack(padx=20, anchor="w", pady=(10, 0))
        entry = ctk.CTkEntry(self.sidebar, placeholder_text=label, show="*" if is_password else "")
        entry.insert(0, default)
        entry.pack(padx=20, fill="x", pady=(2, 10))
        return entry

    def _create_combo_input(self, label, default, initial_values=None):
        ctk.CTkLabel(self.sidebar, text=label).pack(padx=20, anchor="w", pady=(10, 0))
        values = self._build_combo_values(initial_values or [], default)
        combo = ctk.CTkComboBox(self.sidebar, values=values)
        combo.set(default or (values[0] if values[0] else ""))
        combo.pack(padx=20, fill="x", pady=(2, 10))
        return combo

    def _create_input_in_frame(self, frame, label, default):
        ctk.CTkLabel(frame, text=label, font=ctk.CTkFont(size=11)).pack(anchor="w")
        entry = ctk.CTkEntry(frame, placeholder_text=label)
        entry.insert(0, default)
        entry.pack(fill="x", pady=(2, 10))
        return entry

    def _build_combo_values(self, options, selected=None):
        return build_combo_values(options, selected)

    def _build_sprint_combo_values(self, sprint_options, selected=None):
        return build_sprint_combo_values(sprint_options, selected)

    def _set_area_combo_values(self, area_options, selected):
        selected = normalize_area_path(selected)
        values = self._build_combo_values(area_options, selected)
        self.area_entry.configure(values=values)
        self.area_entry.set(selected or (values[0] if values[0] else ""))

    def _set_sprint_combo_values(self, sprint_options, selected):
        selected = normalize_iteration_path(selected)
        values = self._build_sprint_combo_values(sprint_options, selected)
        self.sprint_entry.configure(values=values)
        self.sprint_entry.set(selected or values[0])

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

    def load_combos(self):
        url, area, sprint, token = self.url_entry.get(), self.area_entry.get(), self.sprint_entry.get(), self.token_entry.get()
        area = normalize_area_path(area)
        sprint = normalize_iteration_path(sprint)
        if not url: return messagebox.showwarning("Error", "Enter Server URL")
        if not token and not is_demo_url(url): return messagebox.showwarning("Error", "Enter PAT")
        self.load_combos_btn.configure(state="disabled", text="Loading Combos...")

        def do_load():
            try:
                area_options = get_area_options(url, token)
                area_to_load = area or (area_options[0] if area_options else "")
                self.after(0, lambda options=area_options, selected=area_to_load: self._set_area_combo_values(options, selected))

                if area_options:
                    print(f"Loaded {len(area_options)} area option(s).")
                else:
                    print("No area options returned.")

                sprint_options = get_sprint_options(url, token, area_to_load, force_refresh=True)
                sprint_to_load = sprint or (sprint_options[0] if sprint_options else "@CurrentIteration")
                self.after(0, lambda options=sprint_options, selected=sprint_to_load: self._set_sprint_combo_values(options, selected))
                save_combos_cache(area_options, sprint_options)

                if sprint_options:
                    print(f"Loaded {len(sprint_options)} sprint option(s).")
                else:
                    print("No sprint options returned.")

                s, e = get_sprint_dates(url, token, area_to_load, sprint_to_load)
                if s and e:
                    self.after(0, lambda: self.start_date_entry.delete(0, "end"))
                    self.after(0, lambda value=s: self.start_date_entry.insert(0, value))
                    self.after(0, lambda: self.end_date_entry.delete(0, "end"))
                    self.after(0, lambda value=e: self.end_date_entry.insert(0, value))
                    print(f"Loaded dates (BR): {s} to {e}")
                else:
                    print("Could not find dates for this sprint or macro.")
            except Exception as e:
                self.after(0, lambda err=e: messagebox.showerror("Error", str(err)))
            finally:
                self.after(0, lambda: self.load_combos_btn.configure(state="normal", text="Load Combos"))

        threading.Thread(target=do_load, daemon=True).start()

    def load_sprint_dates(self):
        url, area, sprint, token = self.url_entry.get(), self.area_entry.get(), self.sprint_entry.get(), self.token_entry.get()
        area = normalize_area_path(area)
        sprint = normalize_iteration_path(sprint)
        if not url: return messagebox.showwarning("Error", "Enter Server URL")
        if not token and not is_demo_url(url): return messagebox.showwarning("Error", "Enter PAT")
        self.load_dates_btn.configure(state="disabled", text="Loading Sprint Dates...")

        def do_load():
            try:
                s, e = get_sprint_dates(url, token, area, sprint)
                if s and e:
                    self.after(0, lambda: self.start_date_entry.delete(0, "end"))
                    self.after(0, lambda value=s: self.start_date_entry.insert(0, value))
                    self.after(0, lambda: self.end_date_entry.delete(0, "end"))
                    self.after(0, lambda value=e: self.end_date_entry.insert(0, value))
                    print(f"Loaded dates (BR): {s} to {e}")
                else:
                    print("Could not find dates for this sprint or macro.")
            except Exception as e:
                self.after(0, lambda err=e: messagebox.showerror("Error", str(err)))
            finally:
                self.after(0, lambda: self.load_dates_btn.configure(state="normal", text="📅 Load Sprint Dates"))

        threading.Thread(target=do_load, daemon=True).start()

    def sync_members(self):
        url, area, sprint, token = self.url_entry.get(), self.area_entry.get(), self.sprint_entry.get(), self.token_entry.get()
        area = normalize_area_path(area)
        sprint = normalize_iteration_path(sprint)
        if not url: return messagebox.showwarning("Error", "Enter Server URL")
        if not token and not is_demo_url(url): return messagebox.showwarning("Error", "Enter PAT")
        self.sync_btn.configure(state="disabled", text="Syncing...")

        def do_sync():
            try:
                _, headers = get_tasks(url, token, area, sprint)
                self.member_list = get_members_from_tasks(url, headers, area, sprint)
                save_members_cache(self.member_list)
                self.after(0, self._populate_members)
                print(f"Synced {len(self.member_list)} members.")
            except Exception as e:
                self.after(0, lambda err=e: messagebox.showerror("Error", str(err)))
            finally:
                self.after(0, lambda: self.sync_btn.configure(state="normal", text="↻ SYNC TEAM FROM DEVOPS"))

        threading.Thread(target=do_sync, daemon=True).start()

    def start_extraction_thread(self):
        selected = [m for m, v in self.selected_vars.items() if v.get()]
        url, area, sprint, token = self.url_entry.get(), self.area_entry.get(), self.sprint_entry.get(), self.token_entry.get()
        area = normalize_area_path(area)
        sprint = normalize_iteration_path(sprint)
        start_date, end_date = self.start_date_entry.get(), self.end_date_entry.get()
        graphic_type = self.graphic_type.get()

        if not url: return messagebox.showwarning("Error", "Enter Server URL")
        if not token and not is_demo_url(url): return messagebox.showwarning("Error", "Missing PAT Token")

        save_config(url, area, sprint, token, start_date, end_date)
        self.gen_btn.configure(state="disabled", text="PROCESSING...")
        self.progress_bar.set(0)
        self.log_text.delete("1.0", "end")

        threading.Thread(target=self.run_extraction, args=(url, area, sprint, token, selected, start_date, end_date, graphic_type), daemon=True).start()

    def update_progress(self, val):
        self.after(0, lambda: self.progress_bar.set(val))

    def run_extraction(self, url, area, sprint, token, selected, start_date, end_date, graphic_type):
        try:
            selected_graphic = Graphic_Type.from_description(graphic_type)
            headers = build_auth_headers(token)
            if selected_graphic == Graphic_Type.Burndown:
                burndown_data = get_historical_burndown_data(
                    url, headers, area, sprint,
                    selected_members=selected,
                    start_date=start_date,
                    end_date=end_date,
                    progress_callback=self.update_progress,
                )
                burndown_path = plot_burndown(burndown_data)
                self.update_progress(1.0)
                if burndown_path:
                    self.after(0, lambda data=burndown_data, path=burndown_path: self._open_burndown_viewer(data, path))
            else:
                data = get_historical_work_history(
                    url, headers, area, sprint,
                    selected_members=selected,
                    start_date=start_date,
                    end_date=end_date,
                    progress_callback=self.update_progress,
                )
                combined_path = generate_all_output(data)
                self.update_progress(1.0)
                if combined_path:
                    self.after(0, lambda path=combined_path: self._open_image_viewer(path))
        except Exception as e:
            self.after(0, lambda err=e: messagebox.showerror("Error", str(err)))
        finally:
            self.after(0, lambda: self.gen_btn.configure(state="normal", text="GENERATE GRAPHICS"))

    def _open_image_viewer(self, image_path):
        """Open the combined graph image in the zoom viewer."""
        abs_path = os.path.abspath(image_path)
        if not os.path.exists(abs_path):
            print(f"Image not found: {abs_path}")
            return

        # Close previous viewer if it exists
        if self._image_viewer is not None:
            try:
                self._image_viewer.destroy()
            except:
                pass

        self._image_viewer = ImageViewerWindow(self, abs_path)
        self._image_viewer.focus()
        print(f"Opened image viewer: {abs_path}")

    def _open_burndown_viewer(self, burndown_data, image_path):
        """Open the interactive burndown graph viewer."""
        abs_path = os.path.abspath(image_path)
        if not os.path.exists(abs_path):
            print(f"Image not found: {abs_path}")
            return

        if self._image_viewer is not None:
            try:
                self._image_viewer.destroy()
            except:
                pass

        self._image_viewer = BurndownViewerWindow(self, burndown_data, abs_path)
        self._image_viewer.focus()
        print(f"Opened interactive burndown viewer: {abs_path}")

    # ===================== Reassignment Tab =====================

    def start_reassignment_thread(self):
        url, area, sprint, token = self.url_entry.get(), self.area_entry.get(), self.sprint_entry.get(), self.token_entry.get()
        area = normalize_area_path(area)
        sprint = normalize_iteration_path(sprint)
        start_date, end_date = self.start_date_entry.get(), self.end_date_entry.get()

        if not url: return messagebox.showwarning("Error", "Enter Server URL")
        if not token and not is_demo_url(url): return messagebox.showwarning("Error", "Missing PAT Token")

        save_config(url, area, sprint, token, start_date, end_date)
        self.load_reassign_btn.configure(state="disabled", text="LOADING...")
        self.progress_bar.set(0)
        self.log_text.delete("1.0", "end")

        threading.Thread(target=self.run_reassignment_fetch, args=(url, area, sprint, token, start_date, end_date), daemon=True).start()

    def run_reassignment_fetch(self, url, area, sprint, token, start_date, end_date):
        try:
            ids, headers = get_tasks(url, token, area, sprint, progress_callback=self.update_progress)
            if ids:
                reassignments = get_reassignments(ids, url, headers, start_date=start_date, end_date=end_date, progress_callback=self.update_progress)
                self.update_progress(1.0)
                self.after(0, lambda: self._populate_reassignment_table(reassignments))
            else:
                print("No tasks found for reassignment analysis.")
                self.update_progress(1.0)
        except Exception as e:
            self.after(0, lambda err=e: messagebox.showerror("Error", str(err)))
        finally:
            self.after(0, lambda: self.load_reassign_btn.configure(state="normal", text="🔄 LOAD REASSIGNMENTS"))

    def _populate_reassignment_table(self, reassignments):
        """Populate the reassignment table with data."""
        populate_reassignment_table(
            self.reassign_table,
            self.reassign_count_label,
            reassignments,
            self.rel_x,
            self.rel_w,
        )
