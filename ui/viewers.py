import tkinter as tk

import customtkinter as ctk
from PIL import Image, ImageTk
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg, NavigationToolbar2Tk

from charts.burndown import (
    BURNDOWN_SERIES,
    build_burndown_figure,
    get_burndown_tooltip_data,
    nearest_burndown_index,
)


class ImageViewerWindow(ctk.CTkToplevel):
    """Full-featured image viewer with scroll-zoom and drag-pan."""

    def __init__(self, master, image_path):
        super().__init__(master)
        self.title("Sprint Health - Combined Graph Viewer")
        self.geometry("1200x800")
        self.minsize(600, 400)

        self.image_path = image_path
        self.pil_image = Image.open(image_path)
        self.zoom_level = 1.0
        self.min_zoom = 0.1
        self.max_zoom = 5.0
        self._fast_job = None
        self._zoom_job = None

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
        ctk.CTkButton(toolbar, text="Zoom -", width=70, command=lambda: self._zoom_step(0.8),
                      fg_color="#444", hover_color="#555").pack(side="left", padx=5)

        img_info = f"{self.pil_image.width}x{self.pil_image.height}px"
        ctk.CTkLabel(toolbar, text=img_info, font=ctk.CTkFont(size=11),
                     text_color="#888").pack(side="right", padx=15)

        canvas_frame = ctk.CTkFrame(self, fg_color="transparent")
        canvas_frame.pack(fill="both", expand=True)

        self.canvas = tk.Canvas(canvas_frame, bg="#1a1a1a", highlightthickness=0)
        self.canvas.pack(fill="both", expand=True)

        self.h_scroll = tk.Scrollbar(canvas_frame, orient="horizontal", command=self.canvas.xview)
        self.v_scroll = tk.Scrollbar(canvas_frame, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(xscrollcommand=self.h_scroll.set, yscrollcommand=self.v_scroll.set)

        self.canvas.bind("<MouseWheel>", self._on_mousewheel)
        self.canvas.bind("<Control-MouseWheel>", self._on_ctrl_scroll)
        self.canvas.bind("<ButtonPress-1>", self._on_drag_start)
        self.canvas.bind("<B1-Motion>", self._on_drag_motion)
        self.canvas.bind("<Configure>", self._on_canvas_resize)

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

        if self._fast_job:
            self.after_cancel(self._fast_job)
        self._fast_job = self.after(15, lambda: self._render_image(fast=True))

        if self._zoom_job:
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
        pass


class BurndownViewerWindow(ctk.CTkToplevel):
    """Interactive burndown viewer with Azure DevOps-style hover details."""

    def __init__(self, master, burndown_data, image_path=None):
        super().__init__(master)
        self.title("Sprint Health - Burndown Viewer")
        self.geometry("1200x800")
        self.minsize(700, 450)

        self.burndown_data = burndown_data
        self.image_path = image_path
        self.figure, self.ax, self.series_values = build_burndown_figure(burndown_data)
        self._last_hover_index = None

        toolbar = ctk.CTkFrame(self, height=40, corner_radius=0)
        toolbar.pack(fill="x", padx=0, pady=0)
        saved_label = image_path or "Interactive burndown"
        ctk.CTkLabel(toolbar, text=saved_label, font=ctk.CTkFont(size=11),
                     text_color="#888").pack(side="right", padx=15)

        if self.figure is None:
            ctk.CTkLabel(self, text="No burndown data to display.").pack(expand=True)
            return

        canvas_frame = tk.Frame(self, bg="#111417")
        canvas_frame.pack(fill="both", expand=True)

        self.figure_canvas = FigureCanvasTkAgg(self.figure, master=canvas_frame)
        self.figure_canvas.draw()
        self.figure_canvas.get_tk_widget().pack(side="top", fill="both", expand=True)

        toolbar_frame = tk.Frame(self, bg="#242424")
        toolbar_frame.pack(fill="x")
        self.nav_toolbar = NavigationToolbar2Tk(self.figure_canvas, toolbar_frame, pack_toolbar=False)
        self.nav_toolbar.update()
        self.nav_toolbar.pack(side="left", fill="x", expand=True)

        self._create_hover_artists()
        self.figure_canvas.mpl_connect("motion_notify_event", self._on_hover)
        self.figure_canvas.mpl_connect("axes_leave_event", self._hide_hover)
        self.figure_canvas.mpl_connect("figure_leave_event", self._hide_hover)
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    def _create_hover_artists(self):
        self.guide_line = self.ax.axvline(
            0,
            color="#d8d8d8",
            linewidth=1,
            alpha=0.85,
            visible=False,
            zorder=6,
        )
        self.markers = {}
        for key, _, color, _ in BURNDOWN_SERIES:
            marker, = self.ax.plot(
                [],
                [],
                marker='o',
                markersize=9,
                markerfacecolor=color,
                markeredgecolor="#d8d8d8",
                markeredgewidth=1.4,
                linestyle='None',
                visible=False,
                zorder=7,
            )
            self.markers[key] = marker

        self.tooltip = self.ax.annotate(
            "",
            xy=(0, 0),
            xytext=(12, 12),
            textcoords="offset points",
            fontsize=10,
            color="#e6e6e6",
            bbox={
                "boxstyle": "square,pad=0.55",
                "fc": "#151819",
                "ec": "#9c9c9c",
                "lw": 1.0,
                "alpha": 0.98,
            },
            visible=False,
            zorder=8,
        )

    def _on_hover(self, event):
        if event.inaxes != self.ax:
            self._hide_hover()
            return

        index = nearest_burndown_index(event.xdata, len(self.series_values.get('x', [])))
        if index is None:
            self._hide_hover()
            return

        tooltip_data = get_burndown_tooltip_data(self.burndown_data, index)
        values = [item['value'] for item in tooltip_data['series'] if item['value'] is not None]
        anchor_y = max(values) if values else 0

        self.guide_line.set_xdata([index, index])
        self.guide_line.set_visible(True)

        for item in tooltip_data['series']:
            marker = self.markers[item['key']]
            if item['value'] is None:
                marker.set_visible(False)
                continue
            marker.set_data([index], [item['value']])
            marker.set_visible(True)

        lines = [tooltip_data['date_label']]
        lines.extend(f"{item['label']}: {item['formatted_value']}" for item in tooltip_data['series'])
        self.tooltip.set_text("\n".join(lines))
        self.tooltip.xy = (index, anchor_y)

        width, _ = self.figure_canvas.get_width_height()
        if event.x is not None and event.x > width * 0.65:
            self.tooltip.set_position((-12, 12))
            self.tooltip.set_ha("right")
        else:
            self.tooltip.set_position((12, 12))
            self.tooltip.set_ha("left")

        self.tooltip.set_visible(True)
        self._last_hover_index = index
        self.figure_canvas.draw_idle()

    def _hide_hover(self, event=None):
        if not hasattr(self, "guide_line"):
            return
        if not self.guide_line.get_visible() and not self.tooltip.get_visible():
            return
        self.guide_line.set_visible(False)
        for marker in self.markers.values():
            marker.set_visible(False)
        self.tooltip.set_visible(False)
        self._last_hover_index = None
        self.figure_canvas.draw_idle()

    def _on_close(self):
        self.figure.clear()
        self.destroy()

