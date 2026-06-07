import os
import sys
import threading
import tkinter as tk
from tkinter import messagebox

import customtkinter as ctk
from PIL import Image, ImageTk

from config import load_config, load_members_cache, save_config, save_members_cache
from devops_api import (
    get_members_from_tasks,
    get_sprint_dates,
    get_tasks,
    get_work_history,
)
from plotting import generate_all_output
from reassignment import get_reassignments

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


class ImageViewerWindow(ctk.CTkToplevel):
    """Full-featured image viewer with scroll-zoom and drag-pan."""

    def __init__(self, master, image_path):
        super().__init__(master)
        self.title("Sprint Health — Combined Graph Viewer")
        self.geometry("1200x800")
        self.minsize(600, 400)

        self.image_path = image_path
        self.pil_image = Image.open(image_path)
        self.zoom_level = 1.0
        self.min_zoom = 0.1
        self.max_zoom = 5.0

        # Pan state
        self._drag_start_x = 0
        self._drag_start_y = 0

        # --- Toolbar ---
        toolbar = ctk.CTkFrame(self, height=40, corner_radius=0)
        toolbar.pack(fill="x", padx=0, pady=0)

        self.zoom_label = ctk.CTkLabel(toolbar, text="Zoom: 100%", font=ctk.CTkFont(size=13, weight="bold"))
        self.zoom_label.pack(side="left", padx=15)

        ctk.CTkButton(toolbar, text="Fit Window", width=100, command=self.fit_to_window,
                       fg_color="#444", hover_color="#555").pack(side="left", padx=5)
        ctk.CTkButton(toolbar, text="100%", width=60, command=self.zoom_100,
                       fg_color="#444", hover_color="#555").pack(side="left", padx=5)
        ctk.CTkButton(toolbar, text="Zoom +", width=70, command=lambda: self._zoom_step(1.25),
                       fg_color="#444", hover_color="#555").pack(side="left", padx=5)
        ctk.CTkButton(toolbar, text="Zoom −", width=70, command=lambda: self._zoom_step(0.8),
                       fg_color="#444", hover_color="#555").pack(side="left", padx=5)

        img_info = f"{self.pil_image.width}×{self.pil_image.height}px"
        ctk.CTkLabel(toolbar, text=img_info, font=ctk.CTkFont(size=11),
                      text_color="#888").pack(side="right", padx=15)

        # --- Canvas ---
        canvas_frame = ctk.CTkFrame(self, fg_color="transparent")
        canvas_frame.pack(fill="both", expand=True)

        self.canvas = tk.Canvas(canvas_frame, bg="#1a1a1a", highlightthickness=0)
        self.canvas.pack(fill="both", expand=True)

        # Scrollbars
        self.h_scroll = tk.Scrollbar(canvas_frame, orient="horizontal", command=self.canvas.xview)
        self.v_scroll = tk.Scrollbar(canvas_frame, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(xscrollcommand=self.h_scroll.set, yscrollcommand=self.v_scroll.set)

        # Bind events
        self.canvas.bind("<MouseWheel>", self._on_mousewheel)           # Windows scroll
        self.canvas.bind("<Control-MouseWheel>", self._on_ctrl_scroll)  # Ctrl+scroll zoom
        self.canvas.bind("<ButtonPress-1>", self._on_drag_start)
        self.canvas.bind("<B1-Motion>", self._on_drag_motion)
        self.canvas.bind("<Configure>", self._on_canvas_resize)

        # Initial display
        self._tk_image = None
        self.after(100, self.fit_to_window)

    def _render_image(self, fast=False):
        """Render the image at the current zoom level."""
        w = max(1, int(self.pil_image.width * self.zoom_level))
        h = max(1, int(self.pil_image.height * self.zoom_level))

        resample_method = Image.NEAREST if fast else Image.LANCZOS
        resized = self.pil_image.resize((w, h), resample_method)
        self._tk_image = ImageTk.PhotoImage(resized)

        self.canvas.delete("all")
        self.canvas.create_image(0, 0, anchor="nw", image=self._tk_image)
        self.canvas.configure(scrollregion=(0, 0, w, h))

        pct = int(self.zoom_level * 100)
        self.zoom_label.configure(text=f"Zoom: {pct}%")

    def fit_to_window(self):
        """Fit the image to the current canvas size."""
        self.canvas.update_idletasks()
        cw = self.canvas.winfo_width()
        ch = self.canvas.winfo_height()
        if cw <= 1 or ch <= 1:
            return

        zoom_x = cw / self.pil_image.width
        zoom_y = ch / self.pil_image.height
        self.zoom_level = min(zoom_x, zoom_y)
        self._render_image()

    def zoom_100(self):
        """Reset zoom to 100%."""
        self.zoom_level = 1.0
        self._render_image()

    def _zoom_step(self, factor):
        """Apply a zoom factor."""
        new_zoom = self.zoom_level * factor
        new_zoom = max(self.min_zoom, min(self.max_zoom, new_zoom))
        self.zoom_level = new_zoom

        if hasattr(self, '_fast_job') and self._fast_job:
            self.after_cancel(self._fast_job)
        self._fast_job = self.after(15, lambda: self._render_image(fast=True))

        if hasattr(self, '_zoom_job') and self._zoom_job:
            self.after_cancel(self._zoom_job)
        self._zoom_job = self.after(400, lambda: self._render_image(fast=False))

    def _on_mousewheel(self, event):
        """Scroll vertically without Ctrl, zoom with Ctrl."""
        self.canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

    def _on_ctrl_scroll(self, event):
        """Zoom in/out with Ctrl+Scroll."""
        if event.delta > 0:
            self._zoom_step(1.15)
        else:
            self._zoom_step(1 / 1.15)

    def _on_drag_start(self, event):
        """Start panning."""
        self.canvas.scan_mark(event.x, event.y)

    def _on_drag_motion(self, event):
        """Pan while dragging."""
        self.canvas.scan_dragto(event.x, event.y, gain=1)

    def _on_canvas_resize(self, event):
        """Re-render on canvas resize if in fit mode."""
        pass  # User controls zoom manually


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
        self.url_entry = self._create_input("Server URL", config.get("url", ""))
        self.area_entry = self._create_input("Area Path", config.get("area", r""))
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
        self.tab_sprint.grid_rowconfigure(2, weight=1)

        # Member Selection Area
        ctk.CTkLabel(self.tab_sprint, text="TEAM MEMBERS SELECTION", font=ctk.CTkFont(size=16, weight="bold")).grid(row=0, column=0, sticky="w", pady=(0, 10))

        self.select_all_var = ctk.BooleanVar(value=False)
        self.select_all_cb = ctk.CTkCheckBox(self.tab_sprint, text="Select All", variable=self.select_all_var, command=self._toggle_all_members, font=ctk.CTkFont(size=13, weight="bold"))
        self.select_all_cb.grid(row=1, column=0, sticky="w", pady=(0, 5), padx=5)

        self.member_frame = ctk.CTkScrollableFrame(self.tab_sprint, height=400, label_text="Select members to include...")
        self.member_frame.grid(row=2, column=0, sticky="nsew")

        self.sync_btn = ctk.CTkButton(self.tab_sprint, text="↻ SYNC TEAM FROM DEVOPS", command=self.sync_members, fg_color="#444", hover_color="#555")
        self.sync_btn.grid(row=3, column=0, sticky="ew", pady=10)

        # --- Tab 2: Reassignments ---
        self.tab_reassign = self.tabview.add("Reassignments")
        self.tab_reassign.grid_columnconfigure(0, weight=1)
        self.tab_reassign.grid_rowconfigure(1, weight=1)

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
        header_frame = ctk.CTkFrame(self.tab_reassign, fg_color="#2b2b2b", corner_radius=8, height=36)
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
        self.tab_reassign.grid_rowconfigure(2, weight=1)
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
                self.after(0, lambda err=e: messagebox.showerror("Error", str(err)))
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
                combined_path = generate_all_output(data)
                if combined_path:
                    self.after(0, lambda: self._open_image_viewer(combined_path))
            else:
                print("No tasks found.")
                self.update_progress(1.0)
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

    # ===================== Reassignment Tab =====================

    def start_reassignment_thread(self):
        url, area, sprint, token = self.url_entry.get(), self.area_entry.get(), self.sprint_entry.get(), self.token_entry.get()
        start_date, end_date = self.start_date_entry.get(), self.end_date_entry.get()

        if not token: return messagebox.showwarning("Error", "Missing PAT Token")

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
        # Clear existing rows
        for child in self.reassign_table.winfo_children():
            child.destroy()

        if not reassignments:
            ctk.CTkLabel(self.reassign_table, text="No reassignments found in the selected period.",
                          font=ctk.CTkFont(size=13), text_color="#888").grid(row=0, column=0, columnspan=5, pady=20)
            self.reassign_count_label.configure(text="0 reassignments found")
            return

        self.reassign_count_label.configure(text=f"{len(reassignments)} reassignment(s) found")

        # Alternating row colors for readability
        row_colors = ["#1e1e1e", "#252525"]

        for i, r in enumerate(reassignments):
            bg_color = row_colors[i % 2]
            row_frame = ctk.CTkFrame(self.reassign_table, fg_color=bg_color, corner_radius=4, height=36)
            row_frame.grid(row=i, column=0, sticky="ew", padx=0, pady=1)
            row_frame.grid_propagate(False)

            values = [str(r['task_id']), r['from'], r['to'], r['date'], r['changed_by']]
            colors = ["#aaa", "#e67e22", "#2ecc71", "#3498db", "#9b59b6"]

            for col, (val, color) in enumerate(zip(values, colors)):
                lbl = ctk.CTkLabel(row_frame, text=val, font=ctk.CTkFont(size=11),
                                   text_color=color, anchor="center")
                lbl.place(relx=self.rel_x[col], rely=0.5, relwidth=self.rel_w[col], anchor="w")

        print(f"Displayed {len(reassignments)} reassignment(s) in table.")
