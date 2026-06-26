import queue
import re
import threading
import time
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

import mido
import serial
import serial.tools.list_ports
from midi_analyzer import analyze_midi_file, build_single_motor_plan, build_three_motor_plan, format_analysis
from stepper_pitch_profiles import (
    CUSTOM_PROFILE_PREFIX,
    DAVID_SCHOLTEN_PROFILE,
    STANDARD_PROFILE,
    built_in_profile_values,
    note_to_step_frequency,
    profile_names,
    profile_values,
    safe_profile_name,
    save_custom_profile,
)


BAUD_RATE = 115200
MOTOR_COLORS = ["#3b82f6", "#ef4444", "#22c55e", "#f59e0b"]
VISUAL_SECONDS = 12.0


class MidiStepperGui(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("XIAO MIDI Stepper Player")
        self.geometry("960x720")
        self.minsize(820, 620)

        self.log_queue = queue.Queue()
        self.stop_event = threading.Event()
        self.pause_event = threading.Event()
        self.worker = None
        self.visual_notes = []
        self.visual_duration = 0.0
        self.playback_time = 0.0
        self.seek_time = 0.0
        self.seek_request = None
        self.seek_lock = threading.Lock()
        self.channel_vars = {}
        self.allowed_channels = None
        self.muted_notes = set()
        self.note_assignments = {}
        self.min_note = tk.StringVar(value="0")
        self.max_note = tk.StringVar(value="127")
        self.visual_window_seconds = tk.DoubleVar(value=12.0)
        self.analyzer_vertical_drag_start_y = None
        self.analyzer_window_seconds = tk.DoubleVar(value=24.0)
        self.analyzer_view_start = tk.DoubleVar(value=0.0)
        self.analyzer_lane_zoom = tk.DoubleVar(value=1.0)
        self.analyzer_drag_start_x = None
        self.analyzer_drag_start_view = 0.0
        self.analyzer_notes = []
        self.analyzer_duration = 0.0
        self.analyzer_note_items = {}
        self.analyzer_lane_items = {}
        self.analyzer_view_mode = tk.StringVar(value="Motor routing")
        self.channel_summary = tk.StringVar(value="Channels: none")
        self.assignment_target = tk.StringVar(value="Motor 0")
        self.assignment_summary = tk.StringVar(value="Assignments: none")
        self.custom_profile_name = tk.StringVar(value="My Stepper Profile")
        self.pitch_table_rows = []
        self.pitch_table_values = built_in_profile_values(STANDARD_PROFILE)
        self.show_status_log = tk.BooleanVar(value=True)

        self.com_port = tk.StringVar()
        self.midi_file = tk.StringVar()
        self.single_stepper = tk.BooleanVar(value=True)
        self.auto_single_motor = tk.BooleanVar(value=False)
        self.auto_three_motor = tk.BooleanVar(value=False)
        self.source_channel = tk.StringVar(value="3")
        self.transpose = tk.StringVar(value="0")
        self.loudness_motors = tk.StringVar(value="1")
        self.pitch_profile = tk.StringVar(value=STANDARD_PROFILE)
        self.option_summary = tk.StringVar()
        for option_var in (self.source_channel, self.transpose, self.loudness_motors, self.pitch_profile):
            option_var.trace_add("write", lambda *_args: self._update_option_summary())

        self._configure_style()
        self._build_ui()
        self.refresh_ports()
        self.after(100, self._drain_log_queue)

    def _configure_style(self):
        self.configure(background="#0f172a")
        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure(".", background="#0f172a", foreground="#e5e7eb", fieldbackground="#020617")
        style.configure("TFrame", background="#0f172a")
        style.configure("TLabelframe", background="#0f172a", foreground="#e5e7eb", bordercolor="#1e293b", relief=tk.FLAT)
        style.configure("TLabelframe.Label", background="#0f172a", foreground="#93c5fd", font=("Segoe UI", 9, "bold"))
        style.configure("TLabel", background="#0f172a", foreground="#e5e7eb")
        style.configure("TButton", background="#1e293b", foreground="#f8fafc", bordercolor="#334155", focusthickness=1, padding=(10, 5))
        style.map("TButton", background=[("active", "#334155"), ("pressed", "#172033")])
        style.configure("TCheckbutton", background="#0f172a", foreground="#e5e7eb")
        style.map("TCheckbutton", background=[("active", "#0f172a")])
        style.configure("TNotebook", background="#0f172a", borderwidth=0)
        style.configure("TNotebook.Tab", background="#1e293b", foreground="#cbd5e1", padding=(14, 6))
        style.map("TNotebook.Tab", background=[("selected", "#2563eb")], foreground=[("selected", "#ffffff")])
        style.configure("TCombobox", fieldbackground="#020617", background="#1e293b", foreground="#f8fafc", arrowcolor="#f8fafc")
        style.map(
            "TCombobox",
            fieldbackground=[("readonly", "#020617"), ("!disabled", "#020617")],
            foreground=[("readonly", "#f8fafc"), ("!disabled", "#f8fafc")],
            selectbackground=[("readonly", "#020617"), ("!disabled", "#020617")],
            selectforeground=[("readonly", "#f8fafc"), ("!disabled", "#f8fafc")],
        )
        self.option_add("*TCombobox*Listbox.background", "#020617")
        self.option_add("*TCombobox*Listbox.foreground", "#f8fafc")
        self.option_add("*TCombobox*Listbox.selectBackground", "#2563eb")
        self.option_add("*TCombobox*Listbox.selectForeground", "#ffffff")
        style.configure("TEntry", fieldbackground="#020617", foreground="#f8fafc", insertcolor="#f8fafc")
        style.configure("Treeview", background="#111827", fieldbackground="#111827", foreground="#e5e7eb", rowheight=24)
        style.configure("Treeview.Heading", background="#1e293b", foreground="#e5e7eb")

    def _build_ui(self):
        self._build_menu()

        outer = ttk.Frame(self, padding=10)
        outer.pack(fill=tk.BOTH, expand=True)

        summary_row = ttk.Frame(outer)
        summary_row.pack(fill=tk.X)
        ttk.Label(summary_row, textvariable=self.option_summary).pack(side=tk.LEFT, fill=tk.X, expand=True)
        ttk.Button(summary_row, text="Playback Settings", command=self.open_playback_settings).pack(side=tk.RIGHT)

        actions = ttk.Frame(outer)
        actions.pack(fill=tk.X, pady=(8, 0))
        self.play_button = ttk.Button(actions, text="Play", command=self.play)
        self.play_button.pack(side=tk.LEFT)
        self.pause_button = ttk.Button(actions, text="Pause", command=self.toggle_pause, state=tk.DISABLED)
        self.pause_button.pack(side=tk.LEFT, padx=(8, 0))
        self.stop_button = ttk.Button(actions, text="Stop", command=self.stop, state=tk.DISABLED)
        self.stop_button.pack(side=tk.LEFT, padx=(8, 0))
        ttk.Button(actions, text="Analyze MIDI", command=self.analyze_midi).pack(side=tk.LEFT, padx=(8, 0))
        ttk.Button(actions, text="Arrange Filters", command=self.show_analyzer_tab).pack(side=tk.LEFT, padx=(8, 0))
        ttk.Button(actions, text="Clear Log", command=self.clear_log).pack(side=tk.RIGHT)

        self.notebook = ttk.Notebook(outer)
        self.notebook.pack(fill=tk.BOTH, expand=True, pady=(8, 0))

        player_tab = ttk.Frame(self.notebook, padding=8)
        analyzer_tab = ttk.Frame(self.notebook, padding=8)
        pitch_tab = ttk.Frame(self.notebook, padding=8)
        self.notebook.add(player_tab, text="Player")
        self.notebook.add(analyzer_tab, text="Analyzer / Filters")
        self.notebook.add(pitch_tab, text="Pitch Mapping")
        self.analyzer_tab = analyzer_tab
        self.pitch_tab = pitch_tab

        player_pane = self._make_vertical_pane(player_tab)
        player_pane.pack(fill=tk.BOTH, expand=True)

        visual_frame = ttk.LabelFrame(player_pane, text="Note Visualizer", padding=8)
        zoom_frame = ttk.Frame(visual_frame)
        zoom_frame.pack(fill=tk.X, pady=(0, 6))
        ttk.Label(zoom_frame, text="Timeline zoom").pack(side=tk.LEFT)
        ttk.Scale(
            zoom_frame,
            from_=4,
            to=60,
            orient=tk.HORIZONTAL,
            variable=self.visual_window_seconds,
            command=lambda _value: self._draw_visualizer(),
        ).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(8, 8))
        ttk.Label(zoom_frame, text="seconds visible").pack(side=tk.LEFT)
        self.visual_canvas = tk.Canvas(visual_frame, height=220, background="#111827", highlightthickness=0)
        self.visual_canvas.pack(fill=tk.BOTH, expand=True)
        self.visual_canvas.bind("<Configure>", lambda _event: self._draw_visualizer())
        self.visual_canvas.bind("<Button-1>", self._seek_from_canvas_event)
        self.visual_canvas.bind("<B1-Motion>", self._seek_from_canvas_event)

        log_frame = ttk.LabelFrame(player_pane, text="Status", padding=8)
        self.player_pane = player_pane
        self.log_frame = log_frame
        self.log = tk.Text(log_frame, height=9, wrap=tk.WORD, state=tk.DISABLED)
        self.log.configure(background="#020617", foreground="#e5e7eb", insertbackground="#f8fafc", relief=tk.FLAT)
        self.log.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar = ttk.Scrollbar(log_frame, command=self.log.yview)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.log.configure(yscrollcommand=scrollbar.set)
        player_pane.add(visual_frame, stretch="always", minsize=220)
        player_pane.add(log_frame, stretch="always", minsize=90)
        self.after(100, lambda: self._set_initial_sash(player_pane, 0.76))

        self._build_analyzer_tab(analyzer_tab)
        self._build_pitch_mapping_tab(pitch_tab)
        self._sync_option_state()

    def _make_vertical_pane(self, parent):
        return tk.PanedWindow(
            parent,
            orient=tk.VERTICAL,
            sashwidth=10,
            sashrelief=tk.RAISED,
            showhandle=True,
            handlesize=18,
            handlepad=8,
            bg="#6b7280",
            bd=0,
            opaqueresize=True,
        )

    def _set_initial_sash(self, pane, ratio):
        try:
            height = pane.winfo_height()
            if height > 100:
                pane.sash_place(0, 0, int(height * ratio))
        except tk.TclError:
            pass

    def reset_layout(self):
        if hasattr(self, "player_pane"):
            self.show_status_log.set(True)
            self.toggle_status_log()
            self.after(50, lambda: self._set_initial_sash(self.player_pane, 0.76))
        if hasattr(self, "analyzer_canvas"):
            self.analyzer_window_seconds.set(24.0)
            self.analyzer_lane_zoom.set(1.0)
            self.analyzer_view_start.set(0.0)
            self.draw_analyzer_preview()

    def toggle_status_log(self):
        if not hasattr(self, "player_pane") or not hasattr(self, "log_frame"):
            return
        panes = list(self.player_pane.panes())
        log_path = str(self.log_frame)
        if self.show_status_log.get():
            if log_path not in panes:
                self.player_pane.add(self.log_frame, stretch="always", minsize=90)
        else:
            if log_path in panes:
                self.player_pane.forget(self.log_frame)

    def _build_menu(self):
        menu_bar = tk.Menu(self)
        self.configure(menu=menu_bar)

        file_menu = tk.Menu(menu_bar, tearoff=False)
        file_menu.add_command(label="Import MIDI File...", command=self.browse_file)
        file_menu.add_separator()
        file_menu.add_command(label="Exit", command=self.destroy)
        menu_bar.add_cascade(label="File", menu=file_menu)

        self.connection_menu = tk.Menu(menu_bar, tearoff=False)
        self.connection_menu.add_command(label="Refresh Serial Ports", command=self.refresh_ports)
        self.connection_menu.add_separator()
        self.connection_menu.add_command(label="No serial ports found", state=tk.DISABLED)
        menu_bar.add_cascade(label="Connection", menu=self.connection_menu)

        playback_menu = tk.Menu(menu_bar, tearoff=False)
        playback_menu.add_command(label="Play", command=self.play)
        playback_menu.add_command(label="Pause / Resume", command=self.toggle_pause)
        playback_menu.add_command(label="Stop", command=self.stop)
        playback_menu.add_separator()
        playback_menu.add_command(label="Analyze MIDI", command=self.analyze_midi)
        playback_menu.add_command(label="Arrange Filters", command=self.show_analyzer_tab)
        menu_bar.add_cascade(label="Playback", menu=playback_menu)

        options_menu = tk.Menu(menu_bar, tearoff=False)
        options_menu.add_checkbutton(
            label="Single Stepper Mode",
            variable=self.single_stepper,
            command=self._sync_option_state,
        )
        options_menu.add_checkbutton(
            label="Auto-Simplify for 1 Motor",
            variable=self.auto_single_motor,
            command=self._sync_option_state,
        )
        options_menu.add_checkbutton(
            label="Auto-Arrange for 3 Motors",
            variable=self.auto_three_motor,
            command=self._sync_option_state,
        )
        options_menu.add_separator()
        options_menu.add_command(label="Playback Settings...", command=self.open_playback_settings)
        menu_bar.add_cascade(label="Options", menu=options_menu)

        view_menu = tk.Menu(menu_bar, tearoff=False)
        view_menu.add_command(label="Show Player", command=lambda: self.notebook.select(0))
        view_menu.add_command(label="Show Analyzer / Filters", command=self.show_analyzer_tab)
        view_menu.add_command(label="Show Pitch Mapping", command=lambda: self.notebook.select(self.pitch_tab))
        view_menu.add_separator()
        view_menu.add_checkbutton(label="Show Status Log", variable=self.show_status_log, command=self.toggle_status_log)
        view_menu.add_command(label="Reset Layout", command=self.reset_layout)
        view_menu.add_command(label="Clear Log", command=self.clear_log)
        menu_bar.add_cascade(label="View", menu=view_menu)

    def open_playback_settings(self):
        window = tk.Toplevel(self)
        window.title("Playback Settings")
        window.resizable(False, False)
        window.transient(self)
        window.grab_set()

        frame = ttk.Frame(window, padding=14)
        frame.pack(fill=tk.BOTH, expand=True)
        frame.columnconfigure(1, weight=1)

        ttk.Checkbutton(
            frame,
            text="Single stepper mode (send to motor 0)",
            variable=self.single_stepper,
            command=self._sync_option_state,
        ).grid(row=0, column=0, columnspan=3, sticky="w")
        ttk.Checkbutton(
            frame,
            text="Auto-simplify for 1 motor",
            variable=self.auto_single_motor,
            command=self._sync_option_state,
        ).grid(row=1, column=0, columnspan=3, sticky="w", pady=(8, 0))
        ttk.Checkbutton(
            frame,
            text="Auto-arrange for 3 motors",
            variable=self.auto_three_motor,
            command=self._sync_option_state,
        ).grid(row=2, column=0, columnspan=3, sticky="w", pady=(8, 0))

        ttk.Label(frame, text="Source MIDI channel").grid(row=3, column=0, sticky="w", pady=(12, 4))
        ttk.Entry(frame, textvariable=self.source_channel, width=10).grid(row=3, column=1, sticky="w", pady=(12, 4))
        ttk.Label(frame, text="1-16, blank = all").grid(row=3, column=2, sticky="w", padx=(8, 0), pady=(12, 4))

        ttk.Label(frame, text="Transpose").grid(row=4, column=0, sticky="w", pady=4)
        ttk.Entry(frame, textvariable=self.transpose, width=10).grid(row=4, column=1, sticky="w", pady=4)
        ttk.Label(frame, text="semitones, e.g. 12 or -12").grid(row=4, column=2, sticky="w", padx=(8, 0), pady=4)

        ttk.Label(frame, text="Loudness motors").grid(row=5, column=0, sticky="w", pady=4)
        self.loudness_entry = ttk.Entry(frame, textvariable=self.loudness_motors, width=10)
        self.loudness_entry.grid(row=5, column=1, sticky="w", pady=4)
        ttk.Label(frame, text="use 2-3 only when multiple motors are connected").grid(
            row=5, column=2, sticky="w", padx=(8, 0), pady=4
        )

        ttk.Label(frame, text="Pitch profile").grid(row=6, column=0, sticky="w", pady=4)
        self.pitch_profile_combo = ttk.Combobox(
            frame,
            textvariable=self.pitch_profile,
            values=profile_names(),
            width=28,
            state="readonly",
        )
        self.pitch_profile_combo.grid(row=6, column=1, columnspan=2, sticky="w", pady=4)

        buttons = ttk.Frame(frame)
        buttons.grid(row=7, column=0, columnspan=3, sticky="e", pady=(14, 0))
        ttk.Button(buttons, text="Close", command=window.destroy).pack(side=tk.RIGHT)
        self._sync_option_state()

    def _build_analyzer_tab(self, parent):
        parent.columnconfigure(0, weight=1)
        parent.rowconfigure(0, weight=1)

        analyzer_pane = self._make_vertical_pane(parent)
        analyzer_pane.grid(row=0, column=0, sticky="nsew")

        top_panel = ttk.Frame(analyzer_pane)
        top_panel.columnconfigure(0, weight=1)
        preview_panel = ttk.Frame(analyzer_pane)
        preview_panel.rowconfigure(0, weight=1)
        preview_panel.columnconfigure(0, weight=1)

        summary = ttk.LabelFrame(top_panel, text="Analysis", padding=8)
        summary.grid(row=0, column=0, sticky="ew")
        self.analyzer_summary = ttk.Label(summary, text="Choose a MIDI file, then click Analyze MIDI or Arrange Filters.", justify=tk.LEFT)
        self.analyzer_summary.pack(anchor="w")

        controls = ttk.LabelFrame(top_panel, text="Visual Edits", padding=8)
        controls.grid(row=1, column=0, sticky="ew", pady=(8, 0))
        controls.columnconfigure(0, weight=1)

        self.channel_vars = {}
        self.channel_menu_indices = {}
        channel_button = ttk.Menubutton(controls, text="Channels")
        self.channel_menu = tk.Menu(channel_button, tearoff=False)
        channel_button["menu"] = self.channel_menu
        for channel in range(1, 17):
            var = tk.BooleanVar(value=False)
            self.channel_vars[channel] = var
            index = self.channel_menu.index("end")
            index = 0 if index is None else index + 1
            self.channel_menu.add_checkbutton(
                label=f"Ch {channel}",
                variable=var,
                command=self._filters_changed,
            )
            self.channel_menu_indices[channel] = index

        ttk.Label(
            controls,
            textvariable=self.channel_summary,
        ).grid(row=0, column=0, sticky="w")

        preview_frame = ttk.LabelFrame(
            preview_panel,
            text=(
                "Visual Note Filter - left-click notes to mute/unmute, "
                "Shift+left-click assigns to selected motor, right/middle drag pans, Ctrl+middle drag scrolls vertically"
            ),
            padding=8,
        )
        preview_frame.grid(row=0, column=0, sticky="nsew")
        preview_frame.rowconfigure(1, weight=1)
        preview_frame.columnconfigure(0, weight=1)
        analyzer_nav = ttk.Frame(preview_frame)
        analyzer_nav.grid(row=0, column=0, sticky="ew", pady=(0, 6))
        analyzer_nav.columnconfigure(1, weight=1)
        analyzer_nav.columnconfigure(4, weight=1)
        ttk.Label(analyzer_nav, text="Pitch view").grid(row=0, column=0, sticky="w")
        ttk.Label(analyzer_nav, text="Assign notes to").grid(row=0, column=2, sticky="e", padx=(8, 4))
        ttk.Combobox(
            analyzer_nav,
            textvariable=self.assignment_target,
            values=("Motor 0", "Motor 1", "Motor 2"),
            width=8,
            state="readonly",
        ).grid(row=0, column=3, sticky="w")
        ttk.Label(analyzer_nav, textvariable=self.assignment_summary).grid(row=0, column=4, sticky="w", padx=(10, 4))
        ttk.Button(analyzer_nav, text="Clear Assignments", command=self.clear_note_assignments).grid(
            row=0, column=5, sticky="e", padx=(8, 0)
        )
        self.analyzer_view_mode.trace_add("write", lambda *_args: self.draw_analyzer_preview())
        ttk.Label(analyzer_nav, text="Zoom").grid(row=1, column=0, sticky="w", pady=(6, 0))
        ttk.Scale(
            analyzer_nav,
            from_=4,
            to=120,
            orient=tk.HORIZONTAL,
            variable=self.analyzer_window_seconds,
            command=lambda _value: self.draw_analyzer_preview(),
        ).grid(row=1, column=1, sticky="ew", padx=(8, 16), pady=(6, 0))
        ttk.Label(analyzer_nav, text="Position").grid(row=1, column=2, sticky="w", pady=(6, 0))
        self.analyzer_scroll = ttk.Scale(
            analyzer_nav,
            from_=0,
            to=1,
            orient=tk.HORIZONTAL,
            variable=self.analyzer_view_start,
            command=lambda _value: self.draw_analyzer_preview(),
        )
        self.analyzer_scroll.grid(row=1, column=4, sticky="ew", padx=(8, 0), pady=(6, 0))
        ttk.Label(analyzer_nav, text="Lane height").grid(row=2, column=0, sticky="w", pady=(6, 0))
        ttk.Scale(
            analyzer_nav,
            from_=1.0,
            to=4.0,
            orient=tk.HORIZONTAL,
            variable=self.analyzer_lane_zoom,
            command=lambda _value: self.draw_analyzer_preview(),
        ).grid(row=2, column=1, columnspan=4, sticky="ew", padx=(8, 0), pady=(6, 0))

        analyzer_canvas_frame = ttk.Frame(preview_frame)
        analyzer_canvas_frame.grid(row=1, column=0, sticky="nsew")
        analyzer_canvas_frame.rowconfigure(0, weight=1)
        analyzer_canvas_frame.columnconfigure(0, weight=1)
        self.analyzer_canvas = tk.Canvas(
            analyzer_canvas_frame,
            height=440,
            background="#111827",
            highlightthickness=0,
        )
        self.analyzer_canvas.grid(row=0, column=0, sticky="nsew")
        self.analyzer_y_scroll = ttk.Scrollbar(
            analyzer_canvas_frame,
            orient=tk.VERTICAL,
            command=self.analyzer_canvas.yview,
        )
        self.analyzer_y_scroll.grid(row=0, column=1, sticky="ns")
        self.analyzer_canvas.configure(yscrollcommand=self.analyzer_y_scroll.set)
        self.analyzer_canvas.bind("<Configure>", lambda _event: self.draw_analyzer_preview())
        self.analyzer_canvas.bind("<Button-1>", self._analyzer_canvas_click)
        self.analyzer_canvas.bind("<MouseWheel>", self._analyzer_mousewheel)
        self.analyzer_canvas.bind("<Control-Button-2>", self._analyzer_vertical_pan_start)
        self.analyzer_canvas.bind("<Control-B2-Motion>", self._analyzer_vertical_pan_drag)
        self.analyzer_canvas.bind("<Button-2>", self._analyzer_pan_start)
        self.analyzer_canvas.bind("<B2-Motion>", self._analyzer_pan_drag)
        self.analyzer_canvas.bind("<Button-3>", self._analyzer_pan_start)
        self.analyzer_canvas.bind("<B3-Motion>", self._analyzer_pan_drag)

        actions = ttk.Frame(top_panel)
        actions.grid(row=2, column=0, sticky="ew", pady=(6, 0))
        ttk.Button(actions, text="Refresh Preview", command=self._filters_changed).pack(side=tk.LEFT)
        ttk.Button(actions, text="Clear Muted Notes", command=self.clear_muted_notes).pack(side=tk.LEFT, padx=(8, 0))
        ttk.Button(actions, text="Apply Filters", command=self.apply_arrangement_filters).pack(side=tk.RIGHT)
        analyzer_pane.add(top_panel, stretch="never", minsize=95)
        analyzer_pane.add(preview_panel, stretch="always", minsize=280)
        self.after(100, lambda: self._set_initial_sash(analyzer_pane, 0.25))

    def _build_pitch_mapping_tab(self, parent):
        parent.columnconfigure(0, weight=1)
        parent.rowconfigure(1, weight=1)

        controls = ttk.LabelFrame(parent, text="Custom Pitch Profile", padding=8)
        controls.grid(row=0, column=0, sticky="ew")
        controls.columnconfigure(5, weight=1)

        ttk.Label(controls, text="Profile name").grid(row=0, column=0, sticky="w")
        ttk.Entry(controls, textvariable=self.custom_profile_name, width=28).grid(row=0, column=1, sticky="w", padx=(6, 12))
        ttk.Label(controls, text="Start from").grid(row=0, column=2, sticky="w")
        self.pitch_source_profile = tk.StringVar(value=STANDARD_PROFILE)
        ttk.Combobox(
            controls,
            textvariable=self.pitch_source_profile,
            values=(STANDARD_PROFILE, DAVID_SCHOLTEN_PROFILE),
            width=28,
            state="readonly",
        ).grid(row=0, column=3, sticky="w", padx=(6, 8))
        ttk.Button(controls, text="Load Source", command=self.load_pitch_source_profile).grid(row=0, column=4, sticky="w")

        ttk.Button(controls, text="Save Custom Profile", command=self.save_pitch_mapping_profile).grid(
            row=1, column=0, columnspan=2, sticky="w", pady=(8, 0)
        )
        ttk.Button(controls, text="Reload Saved Profiles", command=self.refresh_pitch_profile_choices).grid(
            row=1, column=2, columnspan=2, sticky="w", pady=(8, 0)
        )
        ttk.Button(controls, text="Use This Profile", command=self.use_current_pitch_mapping).grid(
            row=1, column=4, sticky="w", pady=(8, 0)
        )
        ttk.Label(
            controls,
            text="Edit frequency values in Hz. Pulse us updates on save/load as 1,000,000 / Hz.",
        ).grid(row=1, column=5, sticky="w", padx=(12, 0), pady=(8, 0))

        table_frame = ttk.LabelFrame(parent, text="MIDI Note Pitch Table", padding=8)
        table_frame.grid(row=1, column=0, sticky="nsew", pady=(8, 0))
        table_frame.rowconfigure(0, weight=1)
        table_frame.columnconfigure(0, weight=1)

        columns = ("note", "name", "frequency", "pulse")
        self.pitch_tree = ttk.Treeview(table_frame, columns=columns, show="headings", selectmode="browse")
        self.pitch_tree.heading("note", text="MIDI")
        self.pitch_tree.heading("name", text="Note")
        self.pitch_tree.heading("frequency", text="Frequency Hz")
        self.pitch_tree.heading("pulse", text="Pulse us")
        self.pitch_tree.column("note", width=70, anchor="e", stretch=False)
        self.pitch_tree.column("name", width=90, anchor="w", stretch=False)
        self.pitch_tree.column("frequency", width=140, anchor="e")
        self.pitch_tree.column("pulse", width=140, anchor="e")
        self.pitch_tree.grid(row=0, column=0, sticky="nsew")
        pitch_scroll = ttk.Scrollbar(table_frame, orient=tk.VERTICAL, command=self.pitch_tree.yview)
        pitch_scroll.grid(row=0, column=1, sticky="ns")
        self.pitch_tree.configure(yscrollcommand=pitch_scroll.set)
        self.pitch_tree.bind("<Double-1>", self.edit_selected_pitch_value)

        self.populate_pitch_table(self.pitch_table_values)

    def midi_note_name(self, note):
        names = ("C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B")
        octave = note // 12 - 1
        return f"{names[note % 12]}{octave}"

    def populate_pitch_table(self, values):
        self.pitch_table_values = [float(value) for value in values]
        if not hasattr(self, "pitch_tree"):
            return
        self.pitch_tree.delete(*self.pitch_tree.get_children())
        for note, frequency in enumerate(self.pitch_table_values):
            pulse = 1_000_000.0 / frequency if frequency > 0 else 0.0
            self.pitch_tree.insert(
                "",
                "end",
                iid=str(note),
                values=(note, self.midi_note_name(note), f"{frequency:.6f}", f"{pulse:.3f}"),
            )

    def load_pitch_source_profile(self):
        values = profile_values(self.pitch_source_profile.get())
        self.populate_pitch_table(values)
        self._log(f"Loaded pitch source profile: {self.pitch_source_profile.get()}.")

    def edit_selected_pitch_value(self, _event=None):
        selection = self.pitch_tree.selection()
        if not selection:
            return
        note = int(selection[0])
        window = tk.Toplevel(self)
        window.title(f"Edit MIDI Note {note} {self.midi_note_name(note)}")
        window.resizable(False, False)
        window.transient(self)
        window.grab_set()

        value = tk.StringVar(value=f"{self.pitch_table_values[note]:.6f}")
        frame = ttk.Frame(window, padding=14)
        frame.pack(fill=tk.BOTH, expand=True)
        ttk.Label(frame, text=f"MIDI {note} {self.midi_note_name(note)} frequency Hz").grid(row=0, column=0, sticky="w")
        entry = ttk.Entry(frame, textvariable=value, width=18)
        entry.grid(row=1, column=0, sticky="w", pady=(6, 0))
        entry.focus_set()

        def apply_value():
            try:
                frequency = float(value.get().strip())
            except ValueError:
                messagebox.showerror("Invalid Frequency", "Frequency must be a number.")
                return
            if frequency <= 0:
                messagebox.showerror("Invalid Frequency", "Frequency must be greater than zero.")
                return
            self.pitch_table_values[note] = frequency
            pulse = 1_000_000.0 / frequency
            self.pitch_tree.item(
                str(note),
                values=(note, self.midi_note_name(note), f"{frequency:.6f}", f"{pulse:.3f}"),
            )
            window.destroy()

        buttons = ttk.Frame(frame)
        buttons.grid(row=2, column=0, sticky="e", pady=(12, 0))
        ttk.Button(buttons, text="Apply", command=apply_value).pack(side=tk.RIGHT)
        ttk.Button(buttons, text="Cancel", command=window.destroy).pack(side=tk.RIGHT, padx=(0, 8))
        window.bind("<Return>", lambda _event: apply_value())

    def save_pitch_mapping_profile(self):
        try:
            name = save_custom_profile(self.custom_profile_name.get(), self.pitch_table_values)
        except ValueError as exc:
            messagebox.showerror("Save Failed", str(exc))
            return
        profile = f"{CUSTOM_PROFILE_PREFIX}{name}"
        self.custom_profile_name.set(name)
        self.refresh_pitch_profile_choices()
        self.pitch_profile.set(profile)
        self._log(f"Saved custom pitch profile: {name}.")

    def use_current_pitch_mapping(self):
        name = safe_profile_name(self.custom_profile_name.get())
        profile = f"{CUSTOM_PROFILE_PREFIX}{name}"
        if profile not in profile_names():
            self.save_pitch_mapping_profile()
        else:
            self.pitch_profile.set(profile)
            self._log(f"Selected pitch profile: {profile}.")

    def refresh_pitch_profile_choices(self):
        names = profile_names()
        if hasattr(self, "pitch_profile_combo") and self.pitch_profile_combo.winfo_exists():
            self.pitch_profile_combo.configure(values=names)
        current = self.pitch_profile.get()
        if current not in names:
            self.pitch_profile.set(STANDARD_PROFILE)

    def _sync_option_state(self):
        if self.auto_single_motor.get():
            self.single_stepper.set(False)
            self.auto_three_motor.set(False)
        if self.auto_three_motor.get():
            self.single_stepper.set(False)
            self.auto_single_motor.set(False)
        state = (
            tk.DISABLED
            if self.single_stepper.get() or self.auto_single_motor.get() or self.auto_three_motor.get()
            else tk.NORMAL
        )
        if hasattr(self, "loudness_entry") and self.loudness_entry.winfo_exists():
            self.loudness_entry.configure(state=state)
        if self.single_stepper.get() or self.auto_single_motor.get() or self.auto_three_motor.get():
            self.loudness_motors.set("1")
        self._update_option_summary()

    def _update_option_summary(self):
        if self.auto_single_motor.get():
            mode = "Auto-simplify 1 motor"
        elif self.auto_three_motor.get():
            mode = "Auto-arrange 3 motors"
        elif self.single_stepper.get():
            mode = "Single stepper"
        else:
            mode = "Manual channel/loudness"
        channel = self.source_channel.get().strip() or "all"
        transpose = self.transpose.get().strip() or "0"
        loudness = self.loudness_motors.get().strip() or "1"
        profile = self.pitch_profile.get().replace(" equal temperament", "")
        self.option_summary.set(
            f"Mode: {mode}   Source channel: {channel}   Transpose: {transpose}   "
            f"Loudness motors: {loudness}   Pitch: {profile}"
        )

    def refresh_ports(self):
        ports = [port.device for port in serial.tools.list_ports.comports()]
        if ports and self.com_port.get() not in ports:
            self.com_port.set(ports[0])
        if hasattr(self, "connection_menu"):
            self.connection_menu.delete(0, tk.END)
            self.connection_menu.add_command(label="Refresh Serial Ports", command=self.refresh_ports)
            self.connection_menu.add_separator()
            if ports:
                for port in ports:
                    self.connection_menu.add_radiobutton(label=port, variable=self.com_port, value=port)
            else:
                self.connection_menu.add_command(label="No serial ports found", state=tk.DISABLED)
        self._log(f"Serial ports: {', '.join(ports) if ports else 'none found'}")

    def browse_file(self):
        path = filedialog.askopenfilename(
            title="Choose MIDI file",
            filetypes=[("MIDI files", "*.mid *.midi"), ("All files", "*.*")],
        )
        if path:
            self.midi_file.set(path)
            self.seek_time = 0.0
            self.playback_time = 0.0
            self.visual_notes = []
            self.visual_duration = 0.0
            self.analyzer_notes = []
            self.analyzer_duration = 0.0
            self.analyzer_view_start.set(0.0)
            with self.seek_lock:
                self.seek_request = None
            self._draw_visualizer()
            self.draw_analyzer_preview()

    def play(self):
        if self.worker and self.worker.is_alive():
            return

        config = self._read_config()
        if config is None:
            return

        self.stop_event.clear()
        self.pause_event.clear()
        self.pause_button.configure(text="Pause")
        self.play_button.configure(state=tk.DISABLED)
        self.pause_button.configure(state=tk.NORMAL)
        self.stop_button.configure(state=tk.NORMAL)
        self.worker = threading.Thread(target=self._play_worker, args=(config,), daemon=True)
        self.worker.start()

    def toggle_pause(self):
        if not self.worker or not self.worker.is_alive():
            return
        if self.pause_event.is_set():
            self.pause_event.clear()
            self.pause_button.configure(text="Pause")
            self._log("Playback resumed.")
        else:
            self.pause_event.set()
            self.pause_button.configure(text="Resume")
            self._log("Playback paused.")

    def stop(self):
        self.stop_event.set()
        self.pause_event.clear()
        self.pause_button.configure(text="Pause")
        self._log("Stop requested. Waiting for current MIDI event to finish...")

    def analyze_midi(self):
        midi_path = Path(self.midi_file.get().strip().strip('"'))
        if not midi_path.is_file():
            messagebox.showerror("Missing MIDI File", "Choose a valid .mid file.")
            return

        try:
            analysis = analyze_midi_file(midi_path)
        except Exception as exc:
            messagebox.showerror("Analyze Failed", f"Could not analyze MIDI file:\n{exc}")
            return

        self._log(format_analysis(analysis))
        if analysis["recommended_channel"] is not None:
            self.source_channel.set(str(analysis["recommended_channel"]))
        self.load_analyzer_data(select_tab=False)

    def show_analyzer_tab(self):
        if self.load_analyzer_data(select_tab=True):
            self.notebook.select(self.analyzer_tab)

    def load_analyzer_data(self, select_tab=False):
        midi_path = Path(self.midi_file.get().strip().strip('"'))
        if not midi_path.is_file():
            messagebox.showerror("Missing MIDI File", "Choose a valid .mid file first.")
            return False

        try:
            analysis = analyze_midi_file(midi_path)
            self.analyzer_notes, self.analyzer_duration = self._collect_midi_preview_notes(midi_path)
            self.analyzer_view_start.set(0.0)
        except Exception as exc:
            messagebox.showerror("Analyze Failed", f"Could not analyze MIDI file:\n{exc}")
            return False

        self.current_analysis = analysis
        self.analyzer_summary.configure(
            text=(
                f"{analysis['path'].name}\n"
                f"Length: {analysis['length']:.2f}s   Tracks: {analysis['tracks']}   "
                f"Unique notes: {len({note['note'] for note in self.analyzer_notes})}\n"
                f"Muted notes: {len(self.muted_notes)}   "
                f"Assigned notes: {len(self.note_assignments)}"
            )
        )

        note_counts = analysis["note_counts"]
        for channel, var in self.channel_vars.items():
            default_enabled = note_counts.get(channel, 0) > 0
            if self.allowed_channels is not None:
                default_enabled = channel in self.allowed_channels
            var.set(default_enabled)
            label = f"Ch {channel}"
            if note_counts.get(channel, 0):
                label += f" ({note_counts[channel]})"
            if hasattr(self, "channel_menu") and channel in self.channel_menu_indices:
                self.channel_menu.entryconfigure(self.channel_menu_indices[channel], label=label)

        self._filters_changed()
        if select_tab:
            self.notebook.select(self.analyzer_tab)
        return True

    def select_recommended_channel(self):
        analysis = getattr(self, "current_analysis", None)
        if not analysis:
            if not self.load_analyzer_data(select_tab=True):
                return
            analysis = self.current_analysis
        recommended = analysis["recommended_channel"]
        for channel, var in self.channel_vars.items():
            var.set(channel == recommended)
        self._filters_changed()

    def select_melodic_channels(self):
        analysis = getattr(self, "current_analysis", None)
        if not analysis:
            if not self.load_analyzer_data(select_tab=True):
                return
            analysis = self.current_analysis
        note_counts = analysis["note_counts"]
        for channel, var in self.channel_vars.items():
            var.set(channel in note_counts)
        self._filters_changed()

    def clear_muted_notes(self):
        self.muted_notes.clear()
        self._filters_changed()
        self._log("Muted notes cleared.")

    def _filters_changed(self):
        self._update_channel_summary()
        self._update_assignment_summary()
        self.draw_analyzer_preview()

    def _update_channel_summary(self):
        enabled = [channel for channel, var in self.channel_vars.items() if var.get()]
        if not enabled:
            text = "Loaded notes: none"
        elif len(enabled) == 16:
            text = "Loaded notes: all MIDI parts"
        elif len(enabled) <= 5:
            text = f"Loaded notes: {len(enabled)} MIDI part(s)"
        else:
            text = f"Loaded notes: {len(enabled)} MIDI parts"
        if hasattr(self, "channel_summary"):
            self.channel_summary.set(text)

    def _update_assignment_summary(self):
        count = len(self.note_assignments)
        text = "Assignments: none" if count == 0 else f"Assignments: {count}"
        if hasattr(self, "assignment_summary"):
            self.assignment_summary.set(text)

    def _selected_assignment_motor(self):
        match = re.search(r"(\d+)", self.assignment_target.get())
        if not match:
            return 0
        return max(0, min(2, int(match.group(1))))

    def clear_note_assignments(self):
        self.note_assignments.clear()
        self._filters_changed()
        self._log("Note assignments cleared.")

    def apply_arrangement_filters(self):
        try:
            min_note = int(self.min_note.get().strip() or "0")
            max_note = int(self.max_note.get().strip() or "127")
        except ValueError:
            messagebox.showerror("Invalid Note Range", "Min and max MIDI notes must be whole numbers.")
            return
        if min_note < 0 or max_note > 127 or min_note > max_note:
            messagebox.showerror("Invalid Note Range", "Use a MIDI note range from 0 to 127.")
            return

        allowed = {channel for channel, var in self.channel_vars.items() if var.get()}
        if not allowed:
            messagebox.showerror("No Channels Selected", "Select at least one MIDI channel.")
            return
        self.allowed_channels = allowed
        self.seek_time = 0.0
        self.playback_time = 0.0
        with self.seek_lock:
            self.seek_request = None
        self.rebuild_main_visualizer_preview()
        self.notebook.select(0)
        self._log(
            "Arrangement filters applied: "
            f"channels {', '.join(str(c) for c in sorted(allowed))}, "
            f"notes {min_note}-{max_note}, muted note pairs {len(self.muted_notes)}, "
            f"assigned note pairs {len(self.note_assignments)}."
        )

    def _collect_midi_preview_notes(self, midi_path):
        midi_file = mido.MidiFile(midi_path)
        elapsed = 0.0
        active = {}
        notes = []
        for msg in midi_file:
            elapsed += msg.time
            if not hasattr(msg, "channel") or msg.type not in ("note_on", "note_off"):
                continue
            channel = msg.channel + 1
            key = (channel, msg.note)
            if msg.type == "note_on" and msg.velocity > 0:
                if key in active:
                    start = active[key]
                    notes.append({"start": start, "end": elapsed, "channel": channel, "note": msg.note})
                active[key] = elapsed
            elif key in active:
                start = active.pop(key)
                notes.append({"start": start, "end": elapsed, "channel": channel, "note": msg.note})
        for (channel, note), start in active.items():
            notes.append({"start": start, "end": max(start + 0.05, elapsed), "channel": channel, "note": note})
        return notes, elapsed

    def _current_filter_values(self):
        try:
            min_note = int(self.min_note.get().strip() or "0")
            max_note = int(self.max_note.get().strip() or "127")
        except ValueError:
            min_note, max_note = 0, 127
        return max(0, min_note), min(127, max_note)

    def _midi_note_name(self, note):
        names = ("C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B")
        return f"{names[note % 12]}{note // 12 - 1}"

    def _pitch_scale_label(self, note):
        transposed = note
        try:
            transposed += int(self.transpose.get().strip() or "0")
        except ValueError:
            pass
        try:
            frequency = note_to_step_frequency(transposed, self.pitch_profile.get())
        except Exception:
            frequency = 0.0
        if frequency > 0:
            return f"{self._midi_note_name(note)} {frequency:.1f}Hz"
        return self._midi_note_name(note)

    def draw_analyzer_preview(self):
        if not hasattr(self, "analyzer_canvas"):
            return
        canvas = self.analyzer_canvas
        canvas.delete("all")
        self.analyzer_note_items = {}
        self.analyzer_lane_items = {}

        width = max(canvas.winfo_width(), 1)
        viewport_height = max(canvas.winfo_height(), 1)
        left_pad = 122
        right_pad = 10
        top_pad = 10
        bottom_pad = 22
        plot_width = max(width - left_pad - right_pad, 1)
        base_plot_height = max(viewport_height - top_pad - bottom_pad, 1)
        lane_zoom = max(1.0, min(float(self.analyzer_lane_zoom.get()), 4.0))
        plot_height = max(base_plot_height * lane_zoom, 1)
        content_height = max(viewport_height, int(top_pad + plot_height + bottom_pad))
        lane_height = plot_height / 16
        min_allowed_note, max_allowed_note = self._current_filter_values()

        canvas.configure(scrollregion=(0, 0, width, content_height))
        canvas.create_rectangle(0, 0, width, content_height, fill="#111827", outline="")
        if self.analyzer_duration <= 0:
            canvas.create_text(
                width / 2,
                viewport_height / 2,
                text="Choose a MIDI file and click Analyze MIDI.",
                fill="#d1d5db",
                font=("Segoe UI", 11),
            )
            return

        visible_seconds = max(1.0, min(float(self.analyzer_window_seconds.get()), max(self.analyzer_duration, 1.0)))
        max_start = max(0.0, self.analyzer_duration - visible_seconds)
        view_start = max(0.0, min(float(self.analyzer_view_start.get()), max_start))
        view_end = view_start + visible_seconds
        if hasattr(self, "analyzer_scroll"):
            self.analyzer_scroll.configure(to=max_start if max_start > 0 else 1)
            if abs(float(self.analyzer_view_start.get()) - view_start) > 0.001:
                self.analyzer_view_start.set(view_start)

        if self.analyzer_view_mode.get() == "Motor routing":
            self._draw_motor_routing_preview(
                canvas,
                width,
                content_height,
                left_pad,
                right_pad,
                top_pad,
                bottom_pad,
                plot_width,
                plot_height,
                view_start,
                view_end,
                visible_seconds,
                min_allowed_note,
                max_allowed_note,
            )
            return

        visible_notes_by_channel = {}
        for note in self.analyzer_notes:
            if note["end"] < view_start or note["start"] > view_end:
                continue
            visible_notes_by_channel.setdefault(note["channel"], set()).add(note["note"])
        pitch_rows_by_channel = {
            channel: {note_value: index for index, note_value in enumerate(sorted(note_values, reverse=True))}
            for channel, note_values in visible_notes_by_channel.items()
        }
        separate_pitch_rows = visible_seconds <= 30

        for channel in range(1, 17):
            y0 = top_pad + (channel - 1) * lane_height
            y1 = top_pad + channel * lane_height
            enabled = self.channel_vars.get(channel, tk.BooleanVar(value=False)).get()
            fill = "#172033" if enabled else "#151515"
            outline = "#4b5563" if enabled else "#2f2f2f"
            canvas.create_rectangle(left_pad, y0, width - right_pad, y1, fill=fill, outline=outline)
            label_color = "#f9fafb" if enabled else "#6b7280"
            canvas.create_text(8, (y0 + y1) / 2, anchor="w", text=f"Ch {channel}", fill=label_color, font=("Segoe UI", 8))
            if separate_pitch_rows and channel in pitch_rows_by_channel:
                row_count = max(1, len(pitch_rows_by_channel[channel]))
                row_height = lane_height / row_count
                if row_height >= 7:
                    for note_value, row_index in pitch_rows_by_channel[channel].items():
                        row_y = y0 + row_index * row_height
                        canvas.create_line(left_pad, row_y, width - right_pad, row_y, fill="#243244")
                        if row_height >= 11:
                            canvas.create_text(
                                left_pad + 3,
                                row_y + row_height / 2,
                                anchor="w",
                                text=str(note_value),
                                fill="#9ca3af",
                                font=("Segoe UI", 7),
                            )

        grid_step = 1
        if visible_seconds > 20:
            grid_step = 5
        if visible_seconds > 60:
            grid_step = 10
        first_second = int(view_start // grid_step * grid_step)
        for second in range(first_second, int(view_end) + grid_step, grid_step):
            x = left_pad + (second - view_start) / visible_seconds * plot_width
            canvas.create_line(x, top_pad, x, content_height - bottom_pad, fill="#374151")
            canvas.create_text(
                x + 2,
                content_height - 10,
                anchor="w",
                text=f"{second}s",
                fill="#9ca3af",
                font=("Segoe UI", 8),
            )

        for note in self.analyzer_notes:
            if note["end"] < view_start or note["start"] > view_end:
                continue
            channel = note["channel"]
            y0 = top_pad + (channel - 1) * lane_height
            if separate_pitch_rows and channel in pitch_rows_by_channel:
                rows = pitch_rows_by_channel[channel]
                row_count = max(1, len(rows))
                row_height = lane_height / row_count
                row_index = rows.get(note["note"], 0)
                y = y0 + row_index * row_height + row_height / 2
                bar_half_height = max(2, min(5, row_height / 2 - 1))
            else:
                pitch_ratio = max(0, min(1, (note["note"] - 24) / 72))
                y = y0 + lane_height - 3 - pitch_ratio * max(lane_height - 6, 1)
                bar_half_height = 4
            x0 = left_pad + (note["start"] - view_start) / visible_seconds * plot_width
            x1 = left_pad + (note["end"] - view_start) / visible_seconds * plot_width
            if x1 - x0 < 2:
                x1 = x0 + 2

            channel_enabled = self.channel_vars.get(channel, tk.BooleanVar(value=False)).get()
            range_enabled = min_allowed_note <= note["note"] <= max_allowed_note
            key = (channel, note["note"])
            muted = key in self.muted_notes
            assigned_motor = self.note_assignments.get(key)
            if muted:
                color = "#7f1d1d"
            elif assigned_motor is not None:
                color = MOTOR_COLORS[assigned_motor % len(MOTOR_COLORS)]
            elif channel_enabled and range_enabled:
                color = "#38bdf8"
            else:
                color = "#4b5563"
            outline = "#f9fafb" if assigned_motor is not None else ""
            item = canvas.create_rectangle(
                x0,
                y - bar_half_height,
                x1,
                y + bar_half_height,
                fill=color,
                outline=outline,
            )
            self.analyzer_note_items[item] = key

        canvas.create_text(
            width - 8,
            canvas.canvasy(0) + 8,
            anchor="ne",
            text=(
                f"{view_start:.2f}s - {min(view_end, self.analyzer_duration):.2f}s   "
                "Zoom in to separate notes by pitch rows"
            ),
            fill="#d1d5db",
            font=("Segoe UI", 8),
        )

    def _preview_note_motor(self, note, min_allowed_note, max_allowed_note):
        channel = note["channel"]
        midi_note = note["note"]
        key = (channel, midi_note)
        if key in self.muted_notes:
            return None
        if not (min_allowed_note <= midi_note <= max_allowed_note):
            return None
        if not self.channel_vars.get(channel, tk.BooleanVar(value=False)).get():
            return None
        assigned_motor = self.note_assignments.get(key)
        if assigned_motor is not None:
            return assigned_motor
        source_text = self.source_channel.get().strip()
        if source_text and not self.auto_single_motor.get() and not self.auto_three_motor.get():
            try:
                source_channel = int(source_text)
            except ValueError:
                source_channel = None
            if source_channel is not None:
                if channel == source_channel:
                    return 0
                return None
        if self.single_stepper.get() or self.auto_single_motor.get():
            return 0
        enabled_channels = [ch for ch, var in self.channel_vars.items() if var.get()]
        if self.auto_three_motor.get() or len(enabled_channels) > 0:
            first_three = sorted(enabled_channels)[:3]
            if channel in first_three:
                return first_three.index(channel)
        if 1 <= channel <= 3:
            return channel - 1
        return None

    def _draw_motor_routing_preview(
        self,
        canvas,
        width,
        content_height,
        left_pad,
        right_pad,
        top_pad,
        bottom_pad,
        plot_width,
        plot_height,
        view_start,
        view_end,
        visible_seconds,
        min_allowed_note,
        max_allowed_note,
    ):
        lane_names = ("Motor 0", "Motor 1", "Motor 2", "Muted / filtered")
        lane_notes = {lane: set() for lane in range(len(lane_names))}
        visible_notes = []

        for note in self.analyzer_notes:
            if note["end"] < view_start or note["start"] > view_end:
                continue
            motor = self._preview_note_motor(note, min_allowed_note, max_allowed_note)
            lane = motor if motor is not None else 3
            lane_notes[lane].add(note["note"])
            visible_notes.append((note, lane, motor))

        pitch_rows = {
            lane: {note_value: index for index, note_value in enumerate(sorted(note_values, reverse=True))}
            for lane, note_values in lane_notes.items()
        }
        lane_zoom = max(1.0, min(float(self.analyzer_lane_zoom.get()), 4.0))
        row_unit = 16 * lane_zoom
        lane_heights = {}
        for lane in range(len(lane_names)):
            row_count = max(1, len(pitch_rows[lane]))
            if lane == 3 and not pitch_rows[lane]:
                lane_heights[lane] = 28
            else:
                lane_heights[lane] = max(34, min(260, 24 + row_count * row_unit))

        lane_tops = {}
        y_cursor = top_pad
        for lane in range(len(lane_names)):
            lane_tops[lane] = y_cursor
            y_cursor += lane_heights[lane]
        lane_bottom = y_cursor
        dynamic_content_height = max(canvas.winfo_height(), int(lane_bottom + bottom_pad))
        canvas.configure(scrollregion=(0, 0, width, dynamic_content_height))
        canvas.create_rectangle(0, 0, width, dynamic_content_height, fill="#111827", outline="")

        for lane, name in enumerate(lane_names):
            y0 = lane_tops[lane]
            y1 = y0 + lane_heights[lane]
            fill = "#172033" if lane < 3 else "#18181b"
            outline = MOTOR_COLORS[lane] if lane < 3 else "#52525b"
            canvas.create_rectangle(left_pad, y0, width - right_pad, y1, fill=fill, outline=outline, width=2)
            label_color = MOTOR_COLORS[lane] if lane < 3 else "#a1a1aa"
            canvas.create_text(8, y0 + 9, anchor="w", text=name, fill=label_color, font=("Segoe UI", 9, "bold"))
            if pitch_rows[lane]:
                row_count = max(1, len(pitch_rows[lane]))
                row_height = lane_heights[lane] / row_count
                for note_value, row_index in pitch_rows[lane].items():
                    row_y = y0 + row_index * row_height
                    center_y = row_y + row_height / 2
                    canvas.create_line(left_pad, row_y, width - right_pad, row_y, fill="#243244")
                    if row_height >= 9:
                        canvas.create_text(
                            left_pad - 8,
                            center_y,
                            anchor="e",
                            text=self._pitch_scale_label(note_value),
                            fill="#cbd5e1",
                            font=("Segoe UI", 7),
                        )

        grid_step = 1
        if visible_seconds > 20:
            grid_step = 5
        if visible_seconds > 60:
            grid_step = 10
        first_second = int(view_start // grid_step * grid_step)
        for second in range(first_second, int(view_end) + grid_step, grid_step):
            x = left_pad + (second - view_start) / visible_seconds * plot_width
            canvas.create_line(x, top_pad, x, lane_bottom, fill="#374151")
            canvas.create_text(x + 2, lane_bottom + 10, anchor="w", text=f"{second}s", fill="#9ca3af", font=("Segoe UI", 8))

        for note, lane, motor in visible_notes:
            y0 = lane_tops[lane]
            if pitch_rows[lane]:
                rows = pitch_rows[lane]
                row_count = max(1, len(rows))
                row_height = lane_heights[lane] / row_count
                row_index = rows.get(note["note"], 0)
                y = y0 + row_index * row_height + row_height / 2
                bar_half_height = max(3, min(8, row_height / 2 - 1))
            else:
                y = y0 + lane_heights[lane] / 2
                bar_half_height = 4

            x0 = left_pad + (note["start"] - view_start) / visible_seconds * plot_width
            x1 = left_pad + (note["end"] - view_start) / visible_seconds * plot_width
            if x1 - x0 < 3:
                x1 = x0 + 3

            key = (note["channel"], note["note"])
            assigned = key in self.note_assignments
            muted = key in self.muted_notes
            if muted:
                color = "#991b1b"
            elif motor is None:
                color = "#52525b"
            else:
                color = MOTOR_COLORS[motor % len(MOTOR_COLORS)]
            outline = "#f9fafb" if assigned else ""
            item = canvas.create_rectangle(x0, y - bar_half_height, x1, y + bar_half_height, fill=color, outline=outline)
            self.analyzer_note_items[item] = key
            if x1 - x0 >= 34 and bar_half_height >= 4:
                text_item = canvas.create_text(
                    x0 + 3,
                    y,
                    anchor="w",
                    text=self._midi_note_name(note["note"]),
                    fill="#f9fafb",
                    font=("Segoe UI", 7),
                )
                self.analyzer_note_items[text_item] = key

        canvas.create_text(
            width - 8,
            canvas.canvasy(0) + 8,
            anchor="ne",
            text=f"{view_start:.2f}s - {min(view_end, self.analyzer_duration):.2f}s   Motor routing by pitch",
            fill="#d1d5db",
            font=("Segoe UI", 8),
        )

    def _analyzer_canvas_click(self, event):
        canvas = self.analyzer_canvas
        key = self._analyzer_note_key_at_event(event)
        if key is not None:
            if event.state & 0x0001:
                motor = self._selected_assignment_motor()
                if self.note_assignments.get(key) == motor:
                    del self.note_assignments[key]
                    self._log(f"Cleared assignment for channel {key[0]} note {key[1]}.")
                else:
                    self.note_assignments[key] = motor
                    self._log(f"Assigned channel {key[0]} note {key[1]} to motor {motor}.")
                self._filters_changed()
                return "break"
            if key in self.muted_notes:
                self.muted_notes.remove(key)
                self._log(f"Unmuted channel {key[0]} note {key[1]}.")
            else:
                self.muted_notes.add(key)
                self._log(f"Muted channel {key[0]} note {key[1]}.")
            self._filters_changed()
            return "break"

        canvas_y = canvas.canvasy(event.y)

        if self.analyzer_view_mode.get() == "Motor routing":
            return "break"

        viewport_height = max(canvas.winfo_height(), 1)
        top_pad = 10
        bottom_pad = 22
        base_plot_height = max(viewport_height - top_pad - bottom_pad, 1)
        lane_zoom = max(1.0, min(float(self.analyzer_lane_zoom.get()), 4.0))
        plot_height = max(base_plot_height * lane_zoom, 1)
        lane_height = plot_height / 16
        channel = int((canvas_y - top_pad) / lane_height) + 1
        if 1 <= channel <= 16 and channel in self.channel_vars:
            self.channel_vars[channel].set(not self.channel_vars[channel].get())
            self._filters_changed()
        return "break"

    def _analyzer_note_key_at_event(self, event):
        canvas = self.analyzer_canvas
        canvas_x = canvas.canvasx(event.x)
        canvas_y = canvas.canvasy(event.y)
        for radius in (5, 9, 14):
            clicked_items = canvas.find_overlapping(
                canvas_x - radius,
                canvas_y - radius,
                canvas_x + radius,
                canvas_y + radius,
            )
            for item in reversed(clicked_items):
                key = self.analyzer_note_items.get(item)
                if key is not None:
                    return key
        return None

    def _analyzer_mousewheel(self, event):
        if self.analyzer_duration <= 0:
            return
        old_visible = max(1.0, float(self.analyzer_window_seconds.get()))
        zoom_factor = 0.85 if event.delta > 0 else 1.18
        new_visible = max(1.0, min(120.0, old_visible * zoom_factor))

        canvas = self.analyzer_canvas
        width = max(canvas.winfo_width(), 1)
        left_pad = 78
        right_pad = 10
        plot_width = max(width - left_pad - right_pad, 1)
        pointer_ratio = max(0.0, min(1.0, (event.x - left_pad) / plot_width))
        old_start = float(self.analyzer_view_start.get())
        time_under_pointer = old_start + pointer_ratio * old_visible
        new_start = time_under_pointer - pointer_ratio * new_visible
        max_start = max(0.0, self.analyzer_duration - new_visible)
        new_start = max(0.0, min(new_start, max_start))

        self.analyzer_window_seconds.set(new_visible)
        self.analyzer_view_start.set(new_start)
        self.draw_analyzer_preview()

    def _analyzer_pan_start(self, event):
        if event.state & 0x0004:
            return self._analyzer_vertical_pan_start(event)
        self.analyzer_drag_start_x = event.x
        self.analyzer_drag_start_view = float(self.analyzer_view_start.get())
        return "break"

    def _analyzer_pan_drag(self, event):
        if event.state & 0x0004:
            return self._analyzer_vertical_pan_drag(event)
        if self.analyzer_duration <= 0 or self.analyzer_drag_start_x is None:
            return "break"
        canvas = self.analyzer_canvas
        width = max(canvas.winfo_width(), 1)
        left_pad = 78
        right_pad = 10
        plot_width = max(width - left_pad - right_pad, 1)
        visible_seconds = max(1.0, float(self.analyzer_window_seconds.get()))
        delta_pixels = event.x - self.analyzer_drag_start_x
        delta_seconds = -delta_pixels / plot_width * visible_seconds
        max_start = max(0.0, self.analyzer_duration - visible_seconds)
        new_start = max(0.0, min(self.analyzer_drag_start_view + delta_seconds, max_start))
        self.analyzer_view_start.set(new_start)
        self.draw_analyzer_preview()
        return "break"

    def _analyzer_vertical_pan_start(self, event):
        self.analyzer_vertical_drag_start_y = event.y
        self.analyzer_canvas.scan_mark(event.x, event.y)
        return "break"

    def _analyzer_vertical_pan_drag(self, event):
        self.analyzer_canvas.scan_dragto(event.x, event.y, gain=1)
        return "break"

    def _read_preview_config(self):
        midi_path = Path(self.midi_file.get().strip().strip('"'))
        if not midi_path.is_file():
            return None
        try:
            transpose = int(self.transpose.get().strip() or "0")
            min_note = int(self.min_note.get().strip() or "0")
            max_note = int(self.max_note.get().strip() or "127")
        except ValueError:
            return None
        if min_note < 0 or max_note > 127 or min_note > max_note:
            return None

        source_channel = None
        source_text = self.source_channel.get().strip()
        if source_text:
            try:
                source_channel = int(source_text)
            except ValueError:
                source_channel = None

        auto_single_motor = self.auto_single_motor.get()
        auto_three_motor = self.auto_three_motor.get()
        if auto_single_motor or auto_three_motor:
            motor = None
            source_channel = None
            loudness_motors = 1
        elif self.single_stepper.get():
            motor = 0
            loudness_motors = 1
        else:
            motor = None
            try:
                loudness_motors = int(self.loudness_motors.get().strip() or "1")
            except ValueError:
                loudness_motors = 1

        return {
            "midi_path": midi_path,
            "motor": motor,
            "auto_single_motor": auto_single_motor,
            "auto_three_motor": auto_three_motor,
            "source_channel": source_channel,
            "transpose": transpose,
            "pitch_profile": self.pitch_profile.get(),
            "loudness_motors": max(1, min(3, loudness_motors)),
            "allowed_channels": self.allowed_channels,
            "min_note": min_note,
            "max_note": max_note,
            "muted_notes": set(self.muted_notes),
            "note_assignments": dict(self.note_assignments),
        }

    def rebuild_main_visualizer_preview(self):
        config = self._read_preview_config()
        if config is None:
            return

        midi_file = mido.MidiFile(config["midi_path"])
        motor_channels = 3
        source_index = None
        if config["source_channel"] is not None:
            source_index = config["source_channel"] - 1

        if config["auto_single_motor"]:
            target_motors = [0]
            single_motor_plan = build_single_motor_plan(
                config["midi_path"],
                config["allowed_channels"],
                config["min_note"],
                config["max_note"],
            )
            three_motor_plan = None
        elif config["auto_three_motor"]:
            target_motors = None
            single_motor_plan = None
            three_motor_plan = build_three_motor_plan(
                config["midi_path"],
                3,
                config["allowed_channels"],
                config["min_note"],
                config["max_note"],
            )
        elif config["motor"] is not None:
            target_motors = [config["motor"]]
            single_motor_plan = None
            three_motor_plan = None
        elif config["loudness_motors"] > 1:
            target_motors = list(range(config["loudness_motors"]))
            single_motor_plan = None
            three_motor_plan = None
        else:
            target_motors = None
            single_motor_plan = None
            three_motor_plan = None

        _events, visual_notes, duration = self._prepare_playback_events(
            midi_file,
            motor_channels,
            config,
            source_index,
            target_motors,
            single_motor_plan,
            three_motor_plan,
        )
        self.visual_notes = visual_notes
        self.visual_duration = duration
        self.playback_time = 0.0
        self.seek_time = 0.0
        with self.seek_lock:
            self.seek_request = None
        self._draw_visualizer()

    def open_analyzer_window(self):
        midi_path = Path(self.midi_file.get().strip().strip('"'))
        if not midi_path.is_file():
            messagebox.showerror("Missing MIDI File", "Choose a valid .mid file first.")
            return

        try:
            analysis = analyze_midi_file(midi_path)
        except Exception as exc:
            messagebox.showerror("Analyze Failed", f"Could not analyze MIDI file:\n{exc}")
            return

        window = tk.Toplevel(self)
        window.title("MIDI Analyzer and Arrangement Filters")
        window.geometry("900x720")
        window.minsize(760, 620)
        window.transient(self)

        outer = ttk.Frame(window, padding=14)
        outer.pack(fill=tk.BOTH, expand=True)

        summary = ttk.LabelFrame(outer, text="Analysis", padding=10)
        summary.pack(fill=tk.X)
        ttk.Label(
            summary,
            text=(
                f"{analysis['path'].name}\n"
                f"Length: {analysis['length']:.2f}s   Tracks: {analysis['tracks']}   "
                f"Recommended channel: {analysis['recommended_channel'] or 'n/a'}"
            ),
            justify=tk.LEFT,
        ).pack(anchor="w")

        channels = ttk.LabelFrame(outer, text="Channels to Allow", padding=10)
        channels.pack(fill=tk.X, pady=(12, 0))
        self.channel_vars = {}
        channel_widgets = []
        note_counts = analysis["note_counts"]
        for channel in range(1, 17):
            count = note_counts.get(channel, 0)
            default_enabled = count > 0
            if self.allowed_channels is not None:
                default_enabled = channel in self.allowed_channels
            var = tk.BooleanVar(value=default_enabled)
            self.channel_vars[channel] = var
            row = (channel - 1) // 4
            col = (channel - 1) % 4
            label = f"Ch {channel}"
            if count:
                label += f" ({count})"
            check = ttk.Checkbutton(channels, text=label, variable=var)
            check.grid(row=row, column=col, sticky="w", padx=8, pady=3)
            channel_widgets.append(check)

        filters = ttk.LabelFrame(outer, text="Note Filters", padding=10)
        filters.pack(fill=tk.X, pady=(12, 0))
        ttk.Label(filters, text="Min MIDI note").grid(row=0, column=0, sticky="w")
        ttk.Entry(filters, textvariable=self.min_note, width=8).grid(row=0, column=1, sticky="w", padx=(8, 16))
        ttk.Label(filters, text="Max MIDI note").grid(row=0, column=2, sticky="w")
        ttk.Entry(filters, textvariable=self.max_note, width=8).grid(row=0, column=3, sticky="w", padx=(8, 0))

        plan_frame = ttk.LabelFrame(outer, text="Visual Channel / Note Filter Preview", padding=10)
        plan_frame.pack(fill=tk.BOTH, expand=True, pady=(12, 0))
        preview_canvas = tk.Canvas(plan_frame, height=280, background="#111827", highlightthickness=0)
        preview_canvas.pack(fill=tk.BOTH, expand=True)
        preview_notes, preview_duration = self._collect_midi_preview_notes(midi_path)

        def current_note_range():
            try:
                low = int(self.min_note.get().strip() or "0")
                high = int(self.max_note.get().strip() or "127")
            except ValueError:
                low, high = 0, 127
            return max(0, low), min(127, high)

        def draw_preview():
            preview_canvas.delete("all")
            width = max(preview_canvas.winfo_width(), 1)
            height = max(preview_canvas.winfo_height(), 1)
            left_pad = 72
            right_pad = 10
            top_pad = 12
            bottom_pad = 20
            plot_width = max(width - left_pad - right_pad, 1)
            plot_height = max(height - top_pad - bottom_pad, 1)
            lane_height = plot_height / 16
            min_allowed_note, max_allowed_note = current_note_range()

            preview_canvas.create_rectangle(0, 0, width, height, fill="#111827", outline="")
            for channel in range(1, 17):
                y0 = top_pad + (channel - 1) * lane_height
                y1 = top_pad + channel * lane_height
                enabled = self.channel_vars[channel].get()
                fill = "#172033" if enabled else "#151515"
                outline = "#4b5563" if enabled else "#2f2f2f"
                preview_canvas.create_rectangle(left_pad, y0, width - right_pad, y1, fill=fill, outline=outline)
                label_color = "#f9fafb" if enabled else "#6b7280"
                preview_canvas.create_text(
                    8,
                    (y0 + y1) / 2,
                    anchor="w",
                    text=f"Ch {channel}",
                    fill=label_color,
                    font=("Segoe UI", 8),
                )

            for note in preview_notes:
                if preview_duration <= 0:
                    continue
                channel = note["channel"]
                y0 = top_pad + (channel - 1) * lane_height
                pitch_ratio = max(0, min(1, (note["note"] - 24) / 72))
                y = y0 + lane_height - 3 - pitch_ratio * max(lane_height - 6, 1)
                x0 = left_pad + note["start"] / preview_duration * plot_width
                x1 = left_pad + note["end"] / preview_duration * plot_width
                if x1 - x0 < 2:
                    x1 = x0 + 2
                channel_enabled = self.channel_vars[channel].get()
                note_enabled = min_allowed_note <= note["note"] <= max_allowed_note
                if channel_enabled and note_enabled:
                    color = "#38bdf8" if channel != 10 else "#f97316"
                else:
                    color = "#4b5563"
                preview_canvas.create_rectangle(x0, y - 2, x1, y + 2, fill=color, outline="")

            for second in range(0, int(preview_duration) + 1, 10):
                x = left_pad + second / max(preview_duration, 1) * plot_width
                preview_canvas.create_line(x, top_pad, x, height - bottom_pad, fill="#374151")
                preview_canvas.create_text(x + 2, height - 10, anchor="w", text=f"{second}s", fill="#9ca3af", font=("Segoe UI", 8))

        def preview_click(event):
            height = max(preview_canvas.winfo_height(), 1)
            top_pad = 12
            bottom_pad = 20
            plot_height = max(height - top_pad - bottom_pad, 1)
            lane_height = plot_height / 16
            channel = int((event.y - top_pad) / lane_height) + 1
            if 1 <= channel <= 16:
                self.channel_vars[channel].set(not self.channel_vars[channel].get())
                draw_preview()

        for check in channel_widgets:
            check.configure(command=draw_preview)
        preview_canvas.bind("<Configure>", lambda _event: draw_preview())
        preview_canvas.bind("<Button-1>", preview_click)

        actions = ttk.Frame(outer)
        actions.pack(fill=tk.X, pady=(12, 0))

        def select_recommended():
            recommended = analysis["recommended_channel"]
            for channel, var in self.channel_vars.items():
                var.set(channel == recommended)
            draw_preview()

        def select_melodic():
            for channel, var in self.channel_vars.items():
                var.set(channel in note_counts and channel != 10)
            draw_preview()

        def apply_filters():
            try:
                min_note = int(self.min_note.get().strip() or "0")
                max_note = int(self.max_note.get().strip() or "127")
            except ValueError:
                messagebox.showerror("Invalid Note Range", "Min and max MIDI notes must be whole numbers.")
                return
            if min_note < 0 or max_note > 127 or min_note > max_note:
                messagebox.showerror("Invalid Note Range", "Use a MIDI note range from 0 to 127.")
                return

            allowed = {channel for channel, var in self.channel_vars.items() if var.get()}
            if not allowed:
                messagebox.showerror("No Channels Selected", "Select at least one MIDI channel.")
                return
            self.allowed_channels = allowed
            self.seek_time = 0.0
            self.playback_time = 0.0
            with self.seek_lock:
                self.seek_request = None
            self.rebuild_main_visualizer_preview()
            self._log(
                "Arrangement filters applied: "
                f"channels {', '.join(str(c) for c in sorted(allowed))}, notes {min_note}-{max_note}."
            )
            window.destroy()

        ttk.Button(actions, text="Best 1-Motor Channel", command=select_recommended).pack(side=tk.LEFT)
        ttk.Button(actions, text="All Melodic Channels", command=select_melodic).pack(side=tk.LEFT, padx=(8, 0))
        ttk.Button(actions, text="Refresh Preview", command=draw_preview).pack(side=tk.LEFT, padx=(8, 0))
        ttk.Button(actions, text="Apply", command=apply_filters).pack(side=tk.RIGHT)
        ttk.Button(actions, text="Cancel", command=window.destroy).pack(side=tk.RIGHT, padx=(0, 8))

    def clear_log(self):
        self.log.configure(state=tk.NORMAL)
        self.log.delete("1.0", tk.END)
        self.log.configure(state=tk.DISABLED)

    def _read_config(self):
        com_port = self.com_port.get().strip()
        midi_path = Path(self.midi_file.get().strip().strip('"'))

        if not com_port:
            messagebox.showerror("Missing COM Port", "Choose the XIAO COM port.")
            return None
        if not midi_path.is_file():
            messagebox.showerror("Missing MIDI File", "Choose a valid .mid file.")
            return None

        try:
            transpose = int(self.transpose.get().strip() or "0")
        except ValueError:
            messagebox.showerror("Invalid Transpose", "Transpose must be a whole number.")
            return None
        try:
            min_note = int(self.min_note.get().strip() or "0")
            max_note = int(self.max_note.get().strip() or "127")
        except ValueError:
            messagebox.showerror("Invalid Note Range", "Min and max MIDI notes must be whole numbers.")
            return None
        if min_note < 0 or max_note > 127 or min_note > max_note:
            messagebox.showerror("Invalid Note Range", "Use a MIDI note range from 0 to 127.")
            return None

        source_channel = None
        source_text = self.source_channel.get().strip()
        if source_text:
            try:
                source_channel = int(source_text)
            except ValueError:
                messagebox.showerror("Invalid Channel", "Source MIDI channel must be 1-16 or blank.")
                return None
            if source_channel < 1 or source_channel > 16:
                messagebox.showerror("Invalid Channel", "Source MIDI channel must be 1-16.")
                return None

        auto_single_motor = self.auto_single_motor.get()
        auto_three_motor = self.auto_three_motor.get()
        if auto_single_motor:
            motor = None
            loudness_motors = 1
            source_channel = None
        elif auto_three_motor:
            motor = None
            loudness_motors = 1
            source_channel = None
        elif self.single_stepper.get():
            motor = 0
            loudness_motors = 1
        else:
            motor = None
            try:
                loudness_motors = int(self.loudness_motors.get().strip() or "1")
            except ValueError:
                messagebox.showerror("Invalid Loudness", "Loudness motors must be a whole number.")
                return None

        return {
            "com_port": com_port,
            "midi_path": midi_path,
            "motor": motor,
            "auto_single_motor": auto_single_motor,
            "auto_three_motor": auto_three_motor,
            "source_channel": source_channel,
            "transpose": transpose,
            "pitch_profile": self.pitch_profile.get(),
            "loudness_motors": loudness_motors,
            "allowed_channels": self.allowed_channels,
            "min_note": min_note,
            "max_note": max_note,
            "muted_notes": set(self.muted_notes),
            "note_assignments": dict(self.note_assignments),
        }

    def _play_worker(self, config):
        try:
            self._play_midi(config)
        finally:
            self.log_queue.put(("done", None))

    def _route_message(
        self,
        msg,
        motor_channels,
        source_index,
        target_motors,
        single_motor_plan,
        three_motor_plan,
        allowed_channels,
        min_note,
        max_note,
        muted_notes,
        note_assignments,
    ):
        if not hasattr(msg, "channel"):
            return None
        if hasattr(msg, "note") and not (min_note <= msg.note <= max_note):
            return None
        if hasattr(msg, "note") and (msg.channel + 1, msg.note) in muted_notes:
            return None
        if allowed_channels is not None and msg.channel + 1 not in allowed_channels:
            return None
        if hasattr(msg, "note"):
            assigned_motor = note_assignments.get((msg.channel + 1, msg.note))
            if assigned_motor is not None:
                if assigned_motor < motor_channels:
                    return [assigned_motor]
                return None
        if source_index is not None and msg.channel != source_index:
            return None

        if single_motor_plan is not None:
            if single_motor_plan["mode"] != "channel":
                return None
            if msg.channel + 1 != single_motor_plan["source_channel"]:
                return None
            return [0]

        if three_motor_plan is not None:
            channel = msg.channel + 1
            if three_motor_plan["mode"] == "channels":
                if channel not in three_motor_plan["channel_to_motor"]:
                    return None
                return [three_motor_plan["channel_to_motor"][channel]]
            if three_motor_plan["mode"] == "pitch_bands":
                low_threshold, high_threshold = three_motor_plan["pitch_thresholds"]
                if msg.note <= low_threshold:
                    return [0]
                if msg.note <= high_threshold:
                    return [1]
                return [2]
            return None

        if target_motors is not None:
            return target_motors
        if msg.channel < motor_channels:
            return [msg.channel]
        return None

    def _prepare_playback_events(
        self,
        midi_file,
        motor_channels,
        config,
        source_index,
        target_motors,
        single_motor_plan,
        three_motor_plan,
    ):
        elapsed = 0.0
        timed_events = []
        visual_notes = []
        active_visual = {}
        active_by_motor = [None] * motor_channels

        for msg in midi_file:
            elapsed += msg.time
            if not hasattr(msg, "channel") or msg.type not in ("note_on", "note_off"):
                continue

            motors = self._route_message(
                msg,
                motor_channels,
                source_index,
                target_motors,
                single_motor_plan,
                three_motor_plan,
                config["allowed_channels"],
                config["min_note"],
                config["max_note"],
                config["muted_notes"],
                config["note_assignments"],
            )
            if not motors:
                continue

            is_note_on = msg.type == "note_on" and msg.velocity > 0
            is_note_off = msg.type == "note_off" or (msg.type == "note_on" and msg.velocity == 0)
            if is_note_on:
                frequency = note_to_step_frequency(msg.note + config["transpose"], config["pitch_profile"])
                timed_events.append(
                    {
                        "time": elapsed,
                        "kind": "note_on",
                        "motors": motors,
                        "channel": msg.channel,
                        "note": msg.note,
                        "frequency": frequency,
                    }
                )
                for motor in motors:
                    if active_by_motor[motor] is not None:
                        old_key = active_by_motor[motor]
                        old_start, old_note = active_visual.pop(old_key, (elapsed, msg.note))
                        visual_notes.append(
                            {
                                "start": old_start,
                                "end": elapsed,
                                "motor": motor,
                                "note": old_note + config["transpose"],
                            }
                        )
                    key = (motor, msg.channel, msg.note)
                    active_visual[key] = (elapsed, msg.note)
                    active_by_motor[motor] = key
            elif is_note_off:
                timed_events.append(
                    {
                        "time": elapsed,
                        "kind": "note_off",
                        "motors": motors,
                        "channel": msg.channel,
                        "note": msg.note,
                    }
                )
                for motor in motors:
                    key = (motor, msg.channel, msg.note)
                    if key in active_visual:
                        start, note = active_visual.pop(key)
                        visual_notes.append(
                            {
                                "start": start,
                                "end": elapsed,
                                "motor": motor,
                                "note": note + config["transpose"],
                            }
                        )
                        if active_by_motor[motor] == key:
                            active_by_motor[motor] = None

        for key, (start, note) in active_visual.items():
            motor, _channel, _note = key
            visual_notes.append(
                {
                    "start": start,
                    "end": max(start + 0.05, elapsed),
                    "motor": motor,
                    "note": note + config["transpose"],
                }
            )

        return timed_events, visual_notes, elapsed

    def _draw_visualizer(self):
        canvas = self.visual_canvas
        canvas.delete("all")
        width = max(canvas.winfo_width(), 1)
        height = max(canvas.winfo_height(), 1)
        left_pad = 74
        right_pad = 10
        top_pad = 18
        bottom_pad = 22
        plot_width = max(width - left_pad - right_pad, 1)
        plot_height = max(height - top_pad - bottom_pad, 1)
        play_x = left_pad + plot_width * 0.25
        visible_seconds = max(4.0, float(self.visual_window_seconds.get()))
        seconds_per_pixel = visible_seconds / plot_width
        viewport_start = self.playback_time - (play_x - left_pad) * seconds_per_pixel
        viewport_end = viewport_start + visible_seconds

        canvas.create_rectangle(0, 0, width, height, fill="#111827", outline="")
        for second in range(int(viewport_start) - 1, int(viewport_end) + 2):
            x = left_pad + (second - viewport_start) / visible_seconds * plot_width
            color = "#374151" if second % 5 else "#4b5563"
            canvas.create_line(x, top_pad, x, height - bottom_pad, fill=color)
            if second >= 0:
                canvas.create_text(x + 3, height - 10, anchor="w", text=f"{second}s", fill="#9ca3af", font=("Segoe UI", 8))

        lane_count = 3
        lane_height = plot_height / lane_count
        for motor in range(lane_count):
            y0 = top_pad + motor * lane_height
            y1 = top_pad + (motor + 1) * lane_height
            canvas.create_rectangle(left_pad, y0, width - right_pad, y1, outline="#374151")
            canvas.create_text(8, (y0 + y1) / 2, anchor="w", text=f"Motor {motor}", fill="#d1d5db", font=("Segoe UI", 9))

        for note in self.visual_notes:
            if note["end"] < viewport_start or note["start"] > viewport_end:
                continue
            motor = min(max(note["motor"], 0), lane_count - 1)
            lane_top = top_pad + motor * lane_height
            pitch = max(24, min(96, note["note"]))
            pitch_ratio = (pitch - 24) / 72
            note_y = lane_top + lane_height - 8 - pitch_ratio * max(lane_height - 16, 1)
            x0 = left_pad + (note["start"] - viewport_start) / visible_seconds * plot_width
            x1 = left_pad + (note["end"] - viewport_start) / visible_seconds * plot_width
            if x1 - x0 < 3:
                x1 = x0 + 3
            color = MOTOR_COLORS[motor % len(MOTOR_COLORS)]
            canvas.create_rectangle(x0, note_y - 4, x1, note_y + 4, fill=color, outline="")

        canvas.create_line(play_x, top_pad, play_x, height - bottom_pad, fill="#f9fafb", width=2)
        canvas.create_text(
            play_x + 6,
            top_pad + 4,
            anchor="nw",
            text=f"{self.playback_time:.2f}s / {self.visual_duration:.2f}s",
            fill="#f9fafb",
            font=("Segoe UI", 9, "bold"),
        )

    def _seek_from_canvas_event(self, event):
        if self.visual_duration <= 0:
            return "break"
        canvas = self.visual_canvas
        width = max(canvas.winfo_width(), 1)
        left_pad = 74
        right_pad = 10
        plot_width = max(width - left_pad - right_pad, 1)
        play_x = left_pad + plot_width * 0.25
        visible_seconds = max(4.0, float(self.visual_window_seconds.get()))
        seconds_per_pixel = visible_seconds / plot_width
        viewport_start = self.playback_time - (play_x - left_pad) * seconds_per_pixel
        clicked_time = viewport_start + (event.x - left_pad) / plot_width * visible_seconds
        clicked_time = max(0.0, min(self.visual_duration, clicked_time))
        self.seek_time = clicked_time
        self.playback_time = clicked_time
        self._draw_visualizer()
        with self.seek_lock:
            self.seek_request = clicked_time
        self._log(f"Seek requested: {clicked_time:.2f}s")
        return "break"

    def _play_midi(self, config):
        midi_path = config["midi_path"]
        try:
            midi_file = mido.MidiFile(midi_path)
        except Exception as exc:
            self._log(f"Failed to load MIDI file: {exc}")
            return

        try:
            ser = serial.Serial(config["com_port"], BAUD_RATE, timeout=1)
        except serial.SerialException as exc:
            self._log("Serial connection failed. Check the COM port and close any serial monitor.")
            self._log(f"Serial error: {exc}")
            return

        motor_channels = 0
        try:
            self._log(f"Connecting to {config['com_port']}...")
            time.sleep(3)
            start_time = time.time()
            while motor_channels == 0 and time.time() - start_time < 5 and not self.stop_event.is_set():
                line = ser.readline().decode(errors="ignore")
                channel_match = re.search(r"motors: (\d+)", line)
                if channel_match is not None:
                    motor_channels = int(channel_match.group(1))
                    ser.write(b"ack\n")
                    self._log(f"Connected to firmware with {motor_channels} motors.")

            if motor_channels == 0:
                self._log("Failed to connect to the XIAO firmware.")
                return

            if config["motor"] is not None and config["motor"] >= motor_channels:
                self._log(f"Motor 0 is not available. Firmware reports {motor_channels} motors.")
                return
            if config["auto_three_motor"] and motor_channels < 3:
                self._log("Auto-arrange for 3 motors needs firmware reporting at least 3 motors.")
                return
            if config["loudness_motors"] < 1 or config["loudness_motors"] > motor_channels:
                self._log(f"Loudness motors must be 1-{motor_channels}.")
                return

            source_index = None
            if config["source_channel"] is not None:
                source_index = config["source_channel"] - 1

            if config["auto_single_motor"]:
                target_motors = [0]
                single_motor_plan = build_single_motor_plan(
                    midi_path,
                    config["allowed_channels"],
                    config["min_note"],
                    config["max_note"],
                )
                three_motor_plan = None
            elif config["auto_three_motor"]:
                target_motors = None
                single_motor_plan = None
                three_motor_plan = build_three_motor_plan(
                    midi_path,
                    min(3, motor_channels),
                    config["allowed_channels"],
                    config["min_note"],
                    config["max_note"],
                )
            elif config["motor"] is not None:
                target_motors = [config["motor"]]
                single_motor_plan = None
                three_motor_plan = None
            elif config["loudness_motors"] > 1:
                target_motors = list(range(config["loudness_motors"]))
                single_motor_plan = None
                three_motor_plan = None
            else:
                target_motors = None
                single_motor_plan = None
                three_motor_plan = None

            timed_events, visual_notes, duration = self._prepare_playback_events(
                midi_file,
                motor_channels,
                config,
                source_index,
                target_motors,
                single_motor_plan,
                three_motor_plan,
            )
            self.log_queue.put(("visual", {"notes": visual_notes, "duration": duration}))

            active_notes = [None] * motor_channels
            motors_enabled = False

            def disable_if_idle():
                nonlocal motors_enabled
                if motors_enabled and all(note is None for note in active_notes):
                    ser.write(b"d\n")
                    motors_enabled = False

            self._log(f"Playing {midi_path.name}")
            if source_index is not None:
                self._log(f"Filtering to MIDI channel {config['source_channel']}.")
            if config["transpose"]:
                self._log(f"Transpose: {config['transpose']:+d} semitones.")
            self._log(f"Pitch profile: {config['pitch_profile']}.")
            if target_motors is not None and len(target_motors) > 1:
                self._log(f"Loudness mode on motors: {', '.join(str(m) for m in target_motors)}")
            if single_motor_plan is not None:
                if single_motor_plan["mode"] == "channel":
                    self._log(
                        "Auto 1-motor simplifier: "
                        f"channel {single_motor_plan['source_channel']} -> motor 0."
                    )
                else:
                    self._log("Auto 1-motor simplifier found no playable melodic note data.")
            if three_motor_plan is not None:
                if three_motor_plan["mode"] == "channels":
                    mapping = ", ".join(
                        f"channel {channel}->motor {motor}"
                        for channel, motor in three_motor_plan["channel_to_motor"].items()
                    )
                    self._log(f"Auto 3-motor arrangement: {mapping}.")
                elif three_motor_plan["mode"] == "pitch_bands":
                    low_threshold, high_threshold = three_motor_plan["pitch_thresholds"]
                    self._log(
                        "Auto 3-motor arrangement: "
                        f"low <= {low_threshold}, mid <= {high_threshold}, high above."
                    )
                else:
                    self._log("Auto 3-motor arrangement found no playable melodic note data.")

            with self.seek_lock:
                start_at = min(max(self.seek_time, 0.0), duration)
                self.seek_request = None
            event_index = 0
            while event_index < len(timed_events) and timed_events[event_index]["time"] < start_at:
                event_index += 1

            playback_start = time.monotonic() - start_at
            pause_started_at = None
            pause_disabled_outputs = False
            completed = True

            while event_index < len(timed_events):
                if self.stop_event.is_set():
                    self._log("Playback stopped.")
                    completed = False
                    break

                event = timed_events[event_index]
                while not self.stop_event.is_set():
                    with self.seek_lock:
                        requested_seek = self.seek_request
                        self.seek_request = None
                    if requested_seek is not None:
                        requested_seek = min(max(requested_seek, 0.0), duration)
                        try:
                            ser.write(b"d\n")
                        except Exception:
                            pass
                        active_notes = [None] * motor_channels
                        motors_enabled = False
                        event_index = 0
                        while event_index < len(timed_events) and timed_events[event_index]["time"] < requested_seek:
                            event_index += 1
                        playback_start = time.monotonic() - requested_seek
                        pause_started_at = None
                        pause_disabled_outputs = False
                        self.log_queue.put(("time", requested_seek))
                        if event_index >= len(timed_events):
                            break
                        event = timed_events[event_index]

                    if self.pause_event.is_set():
                        if pause_started_at is None:
                            pause_started_at = time.monotonic()
                        if not pause_disabled_outputs:
                            try:
                                ser.write(b"d\n")
                            except Exception:
                                pass
                            active_notes = [None] * motor_channels
                            motors_enabled = False
                            pause_disabled_outputs = True
                        current_time = max(0.0, pause_started_at - playback_start)
                        self.log_queue.put(("time", current_time))
                        time.sleep(0.05)
                        continue

                    if pause_started_at is not None:
                        playback_start += time.monotonic() - pause_started_at
                        pause_started_at = None
                        pause_disabled_outputs = False

                    current_time = time.monotonic() - playback_start
                    self.log_queue.put(("time", min(current_time, duration)))
                    if current_time >= event["time"]:
                        break
                    time.sleep(min(0.03, event["time"] - current_time))

                if self.stop_event.is_set():
                    self._log("Playback stopped.")
                    completed = False
                    break
                if event_index >= len(timed_events):
                    break

                if event["kind"] == "note_on":
                    for motor_index in event["motors"]:
                        if active_notes[motor_index] is not None:
                            ser.write(f"e,{motor_index}\n".encode())
                        ser.write(f's,{motor_index},{event["frequency"]}\n'.encode())
                        active_notes[motor_index] = (event["channel"], event["note"])
                    motors_enabled = True
                elif event["kind"] == "note_off":
                    for motor_index in event["motors"]:
                        if active_notes[motor_index] == (event["channel"], event["note"]):
                            ser.write(f"e,{motor_index}\n".encode())
                            active_notes[motor_index] = None
                    disable_if_idle()
                event_index += 1

            if completed and not self.stop_event.is_set():
                self.log_queue.put(("time", duration))
                self._log("Playback finished.")
        except Exception as exc:
            self._log(f"Playback failed: {exc}")
        finally:
            try:
                ser.write(b"d\n")
            except Exception:
                pass
            ser.close()
            self._log("Serial port closed.")

    def _log(self, message):
        self.log_queue.put(("log", message))

    def _drain_log_queue(self):
        while True:
            try:
                kind, value = self.log_queue.get_nowait()
            except queue.Empty:
                break
            if kind == "log":
                self.log.configure(state=tk.NORMAL)
                self.log.insert(tk.END, f"{value}\n")
                self.log.see(tk.END)
                self.log.configure(state=tk.DISABLED)
            elif kind == "visual":
                self.visual_notes = value["notes"]
                self.visual_duration = value["duration"]
                self.playback_time = 0.0
                self._draw_visualizer()
            elif kind == "time":
                self.playback_time = value
                self._draw_visualizer()
            elif kind == "done":
                self.play_button.configure(state=tk.NORMAL)
                self.pause_button.configure(state=tk.DISABLED, text="Pause")
                self.stop_button.configure(state=tk.DISABLED)
                self.pause_event.clear()
        self.after(100, self._drain_log_queue)


if __name__ == "__main__":
    MidiStepperGui().mainloop()
