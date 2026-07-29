"""
gui.py

Initial desktop GUI shell for VideoText.
"""

import os
from pathlib import Path
import queue
import threading
import tkinter as tk
from tkinter import filedialog, scrolledtext, ttk

from app_info import APP_COPYRIGHT, APP_NAME, APP_RELEASE, APP_STATUS
from help_content import (
    get_about_introduction,
    get_about_sections,
    get_about_text,
    get_accuracy_validation_text,
    get_how_to_use_text,
)
from batch_processing import (
    BatchProcessingRequest,
    BatchProgress,
    format_batch_summary,
    normalize_video_paths,
    process_batch,
    videos_in_folder,
)
from os_integration import open_folder
from preferences import (
    Preferences,
    SUPPORTED_EXPORT_FORMATS,
    load_preferences,
    remember_folder,
    save_preferences,
    valid_initial_directory,
)

from processing_service import (
    ProcessingMode,
    ProcessingProgress,
    ProcessingRequest,
    format_duration,
    format_processing_summary,
    process_request,
)


class VideoTextApp(ttk.Frame):
    """Top-level layout and placeholder interactions for VideoText."""

    def __init__(self, master: tk.Tk):
        super().__init__(master, padding=12)
        self.master = master
        self.preferences = load_preferences()
        self.preferences_dialog: tk.Toplevel | None = None
        self.video_path = tk.StringVar()
        self.run_mode = tk.StringVar(value="single")
        self.advanced_mode = tk.BooleanVar(value=False)
        self.advanced_start_mode = tk.StringVar(
            value=ProcessingMode.FULL_VIDEO.value,
        )
        self.advanced_source_path = tk.StringVar()
        saved_output_folder = self.preferences.default_output_folder
        self.output_folder = tk.StringVar(
            value=saved_output_folder if Path(saved_output_folder).is_dir() else ""
        )
        self.status = tk.StringVar(value="Select a video and output folder.")
        self.progress_details = tk.StringVar()
        self.progress_value = tk.IntVar(value=0)
        self.processing = False
        self.message_queue = queue.Queue()
        self.batch_paths: list[str] = []
        self.batch_controls: list[ttk.Button] = []
        # Keep the GUI's original all-formats default, then apply the saved
        # startup preference once.  Later preference saves do not alter an
        # in-progress session.
        self.format_options = {
            "markdown": tk.BooleanVar(value=True),
            "csv": tk.BooleanVar(value=True),
            "excel": tk.BooleanVar(value=True),
        }
        for name, variable in self.format_options.items():
            variable.set(name in self.preferences.default_export_formats)

        self._build_layout()
        self._build_menu()

    def _build_menu(self) -> None:
        """Add concise in-app help without changing the processing layout."""

        menu_bar = tk.Menu(self.master)
        edit_menu = tk.Menu(menu_bar, tearoff=False)
        edit_menu.add_command(label="Preferences...", command=self._show_preferences)
        menu_bar.add_cascade(label="Edit", menu=edit_menu)
        help_menu = tk.Menu(menu_bar, tearoff=False)
        help_menu.add_command(
            label="How to Use VideoText",
            command=self._show_how_to_use,
        )
        help_menu.add_command(
            label="Accuracy & Validation",
            command=self._show_accuracy_validation,
        )
        help_menu.add_command(
            label="About VideoText",
            command=self._show_about,
        )
        menu_bar.add_cascade(label="Help", menu=help_menu)
        self.master.configure(menu=menu_bar)

    def _build_layout(self) -> None:
        self.master.title("VideoText")
        self.master.minsize(650, 500)

        self.grid(sticky="nsew")
        self.master.columnconfigure(0, weight=1)
        self.master.rowconfigure(0, weight=1)
        self.columnconfigure(1, weight=1)
        self.rowconfigure(8, weight=1)

        self.video_label = ttk.Label(self, text="Video File")
        self.video_label.grid(
            row=0,
            column=0,
            sticky="w",
            padx=(0, 8),
            pady=(0, 8),
        )
        self.video_entry = ttk.Entry(self, textvariable=self.video_path)
        self.video_entry.grid(
            row=0,
            column=1,
            sticky="ew",
            pady=(0, 8),
        )
        self.video_browse_button = ttk.Button(
            self,
            text="Browse",
            command=self._browse_video,
        )
        self.video_browse_button.grid(
            row=0,
            column=2,
            padx=(8, 0),
            pady=(0, 8),
        )

        mode_frame = ttk.LabelFrame(self, text="Processing Mode", padding=6)
        mode_frame.grid(row=1, column=0, columnspan=3, sticky="ew", pady=(0, 8))
        ttk.Radiobutton(
            mode_frame,
            text="Single video",
            value="single",
            variable=self.run_mode,
            command=self._set_run_mode,
        ).grid(row=0, column=0, padx=(0, 16), sticky="w")
        ttk.Radiobutton(
            mode_frame,
            text="Batch Processing",
            value="batch",
            variable=self.run_mode,
            command=self._set_run_mode,
        ).grid(row=0, column=1, sticky="w")

        self.advanced_checkbutton = ttk.Checkbutton(
            self,
            text="Advanced Mode",
            variable=self.advanced_mode,
            command=self._toggle_advanced_mode,
        )
        self.advanced_checkbutton.grid(row=2, column=0, columnspan=3, sticky="w", pady=(0, 8))

        self.advanced_frame = ttk.LabelFrame(
            self,
            text="Advanced Mode",
            padding=8,
        )
        self.advanced_frame.columnconfigure(1, weight=1)
        ttk.Label(self.advanced_frame, text="Start from").grid(
            row=0, column=0, sticky="w", padx=(0, 8), pady=(0, 8)
        )
        modes = (
            ("Full video", ProcessingMode.FULL_VIDEO),
            ("Candidate frames cache", ProcessingMode.CANDIDATE_FRAMES),
            ("OCR results cache", ProcessingMode.OCR_RESULTS),
            ("Reading-order cache", ProcessingMode.READING_ORDER),
        )
        mode_frame = ttk.Frame(self.advanced_frame)
        mode_frame.grid(row=0, column=1, columnspan=2, sticky="w", pady=(0, 8))
        for index, (label, mode) in enumerate(modes):
            ttk.Radiobutton(
                mode_frame,
                text=label,
                value=mode.value,
                variable=self.advanced_start_mode,
            ).grid(row=0, column=index, padx=(0, 10), sticky="w")

        ttk.Label(self.advanced_frame, text="Source").grid(
            row=1, column=0, sticky="w", padx=(0, 8)
        )
        ttk.Entry(
            self.advanced_frame,
            textvariable=self.advanced_source_path,
        ).grid(row=1, column=1, sticky="ew")
        ttk.Button(
            self.advanced_frame,
            text="Browse",
            command=self._browse_advanced_source,
        ).grid(row=1, column=2, padx=(8, 0))

        self.batch_frame = ttk.LabelFrame(self, text="Batch Processing", padding=8)
        self.batch_frame.columnconfigure(0, weight=1)
        self.batch_listbox = tk.Listbox(self.batch_frame, height=6)
        self.batch_listbox.grid(row=0, column=0, columnspan=4, sticky="ew", pady=(0, 8))
        self._add_batch_button("Add Videos...", self._add_batch_videos, 1, 0)
        self._add_batch_button("Add Folder...", self._add_batch_folder, 1, 1)
        self._add_batch_button("Remove Selected", self._remove_selected_batch_video, 1, 2)
        self._add_batch_button("Clear List", self._clear_batch_list, 1, 3)

        ttk.Label(self, text="Output Folder").grid(
            row=4,
            column=0,
            sticky="w",
            padx=(0, 8),
            pady=(0, 8),
        )
        ttk.Entry(self, textvariable=self.output_folder).grid(
            row=4,
            column=1,
            sticky="ew",
            pady=(0, 8),
        )
        ttk.Button(self, text="Browse", command=self._browse_output_folder).grid(
            row=4,
            column=2,
            padx=(8, 0),
            pady=(0, 8),
        )

        formats_frame = ttk.LabelFrame(self, text="Export Formats", padding=8)
        formats_frame.grid(
            row=5,
            column=0,
            columnspan=3,
            sticky="ew",
            pady=(0, 8),
        )

        for column, (name, variable) in enumerate(self.format_options.items()):
            ttk.Checkbutton(
                formats_frame,
                text=name.title(),
                variable=variable,
            ).grid(row=0, column=column, padx=(0, 16), sticky="w")

        self.process_button = ttk.Button(
            self,
            text="Process",
            command=self._start_processing,
        )
        self.process_button.grid(
            row=6,
            column=0,
            columnspan=3,
            pady=(0, 8),
        )

        progress_frame = ttk.LabelFrame(self, text="Progress", padding=8)
        progress_frame.grid(
            row=7,
            column=0,
            columnspan=3,
            sticky="ew",
            pady=(0, 8),
        )
        progress_frame.columnconfigure(0, weight=1)

        self.progress_bar = ttk.Progressbar(
            progress_frame,
            maximum=100,
            variable=self.progress_value,
        )
        self.progress_bar.grid(row=0, column=0, sticky="ew")
        ttk.Label(progress_frame, textvariable=self.status).grid(
            row=1,
            column=0,
            sticky="w",
            pady=(6, 0),
        )
        ttk.Label(progress_frame, textvariable=self.progress_details).grid(
            row=2,
            column=0,
            sticky="w",
            pady=(2, 0),
        )

        log_frame = ttk.LabelFrame(self, text="Log", padding=8)
        log_frame.grid(
            row=8,
            column=0,
            columnspan=3,
            sticky="nsew",
        )
        log_frame.columnconfigure(0, weight=1)
        log_frame.rowconfigure(0, weight=1)

        self.log_text = tk.Text(log_frame, height=12, wrap="word")
        self.log_text.grid(row=0, column=0, sticky="nsew")
        scrollbar = ttk.Scrollbar(
            log_frame,
            orient="vertical",
            command=self.log_text.yview,
        )
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.log_text.configure(yscrollcommand=scrollbar.set, state="disabled")

    def _browse_video(self) -> None:
        path = filedialog.askopenfilename(
            title="Select Video File",
            filetypes=[
                ("Video files", "*.mp4 *.avi *.mov *.mkv"),
                ("All files", "*.*"),
            ],
            initialdir=valid_initial_directory(
                self.preferences.last_single_video_folder,
            ),
        )
        if path:
            self.video_path.set(path)
            self._remember_selected_folder("last_single_video_folder", Path(path).parent)

    def _show_preferences(self) -> None:
        """Open one editable preferences dialog without duplicating windows."""

        if self.preferences_dialog is not None and self.preferences_dialog.winfo_exists():
            self.preferences_dialog.lift()
            self.preferences_dialog.focus_set()
            return

        dialog = tk.Toplevel(self.master)
        self.preferences_dialog = dialog
        dialog.title("Preferences")
        dialog.transient(self.master)
        dialog.resizable(True, False)
        _center_dialog(dialog, self.master, preferred_width=560, preferred_height=360)
        dialog.columnconfigure(1, weight=1)

        folder_var = tk.StringVar(value=self.preferences.default_output_folder)
        format_vars = {
            name: tk.BooleanVar(value=name in self.preferences.default_export_formats)
            for name in SUPPORTED_EXPORT_FORMATS
        }
        remember_var = tk.BooleanVar(value=self.preferences.remember_last_folders)
        open_folder_var = tk.BooleanVar(
            value=self.preferences.open_output_folder_after_completion,
        )
        validation_message = tk.StringVar()

        ttk.Label(dialog, text="Default output folder").grid(
            row=0, column=0, sticky="w", padx=12, pady=(12, 6),
        )
        ttk.Entry(dialog, textvariable=folder_var).grid(
            row=0, column=1, sticky="ew", pady=(12, 6),
        )

        def browse_default_folder() -> None:
            folder = filedialog.askdirectory(
                title="Select Default Output Folder",
                initialdir=valid_initial_directory(folder_var.get()),
            )
            if folder:
                folder_var.set(folder)

        ttk.Button(dialog, text="Browse...", command=browse_default_folder).grid(
            row=0, column=2, padx=(8, 12), pady=(12, 6),
        )

        formats_frame = ttk.LabelFrame(dialog, text="Default export formats", padding=8)
        formats_frame.grid(row=1, column=0, columnspan=3, sticky="ew", padx=12, pady=6)
        for column, name in enumerate(SUPPORTED_EXPORT_FORMATS):
            ttk.Checkbutton(
                formats_frame,
                text=name.title(),
                variable=format_vars[name],
            ).grid(row=0, column=column, padx=(0, 16), sticky="w")

        ttk.Checkbutton(
            dialog,
            text="Remember last-used folders",
            variable=remember_var,
        ).grid(row=2, column=0, columnspan=3, sticky="w", padx=12, pady=6)
        ttk.Checkbutton(
            dialog,
            text="Open output folder after successful completion",
            variable=open_folder_var,
        ).grid(row=3, column=0, columnspan=3, sticky="w", padx=12, pady=6)
        ttk.Label(dialog, textvariable=validation_message, foreground="firebrick").grid(
            row=4, column=0, columnspan=3, sticky="w", padx=12, pady=(0, 6),
        )

        button_frame = ttk.Frame(dialog)
        button_frame.grid(row=5, column=0, columnspan=3, sticky="e", padx=12, pady=(0, 12))

        def close_dialog() -> None:
            self.preferences_dialog = None
            dialog.destroy()

        def restore_defaults() -> None:
            defaults = Preferences()
            folder_var.set(defaults.default_output_folder)
            for name, variable in format_vars.items():
                variable.set(name in defaults.default_export_formats)
            remember_var.set(defaults.remember_last_folders)
            open_folder_var.set(defaults.open_output_folder_after_completion)
            validation_message.set("")

        def save_dialog() -> None:
            selected_formats = [
                name for name, variable in format_vars.items() if variable.get()
            ]
            default_folder = folder_var.get().strip()
            if not selected_formats:
                validation_message.set("Select at least one default export format.")
                return
            if default_folder and not Path(default_folder).is_dir():
                validation_message.set("Default output folder must be an existing directory.")
                return

            self.preferences.default_output_folder = default_folder
            self.preferences.default_export_formats = selected_formats
            self.preferences.remember_last_folders = remember_var.get()
            self.preferences.open_output_folder_after_completion = open_folder_var.get()
            save_preferences(self.preferences)
            close_dialog()

        ttk.Button(button_frame, text="Restore Defaults", command=restore_defaults).grid(
            row=0, column=0, padx=(0, 8),
        )
        ttk.Button(button_frame, text="Cancel", command=close_dialog).grid(
            row=0, column=1, padx=(0, 8),
        )
        save_button = ttk.Button(button_frame, text="Save", command=save_dialog)
        save_button.grid(row=0, column=2)
        dialog.protocol("WM_DELETE_WINDOW", close_dialog)
        dialog.bind("<Escape>", lambda _event: close_dialog())
        save_button.focus_set()

    def _remember_selected_folder(self, field_name: str, folder: Path) -> None:
        """Persist a valid dialog folder only when the preference enables it."""

        remember_folder(self.preferences, field_name, folder)

    def _add_batch_button(self, text: str, command, row: int, column: int) -> None:
        button = ttk.Button(self.batch_frame, text=text, command=command)
        button.grid(row=row, column=column, padx=(0, 8), sticky="w")
        self.batch_controls.append(button)

    def _set_run_mode(self) -> None:
        """Show either the single-video controls or the sequential batch queue."""

        if self.run_mode.get() == "batch":
            self.video_label.grid_remove()
            self.video_entry.grid_remove()
            self.video_browse_button.grid_remove()
            self.advanced_checkbutton.grid_remove()
            self.advanced_frame.grid_remove()
            self.batch_frame.grid(
                row=3,
                column=0,
                columnspan=3,
                sticky="ew",
                pady=(0, 8),
            )
        else:
            self.batch_frame.grid_remove()
            self.video_label.grid()
            self.video_entry.grid()
            self.video_browse_button.grid()
            self.advanced_checkbutton.grid()
            if self.advanced_mode.get():
                self.advanced_frame.grid(
                    row=3,
                    column=0,
                    columnspan=3,
                    sticky="ew",
                    pady=(0, 8),
                )

    def _add_batch_videos(self) -> None:
        paths = filedialog.askopenfilenames(
            title="Select Video Files",
            filetypes=[
                ("Video files", "*.mp4 *.avi *.mov *.mkv"),
                ("All files", "*.*"),
            ],
            initialdir=valid_initial_directory(
                self.preferences.last_batch_video_folder,
            ),
        )
        if paths:
            self._add_batch_paths(list(paths))
            self._remember_selected_folder("last_batch_video_folder", Path(paths[0]).parent)

    def _add_batch_folder(self) -> None:
        folder = filedialog.askdirectory(
            title="Select Video Folder",
            initialdir=valid_initial_directory(self.preferences.last_batch_folder),
        )
        if not folder:
            return

        try:
            self._add_batch_paths(videos_in_folder(folder))
            self._remember_selected_folder("last_batch_folder", Path(folder))
        except ValueError as error:
            self._set_status(str(error))

    def _add_batch_paths(self, paths: list[str]) -> None:
        self.batch_paths = normalize_video_paths(self.batch_paths + paths)
        self._refresh_batch_list()

    def _remove_selected_batch_video(self) -> None:
        selected = self.batch_listbox.curselection()
        if not selected:
            return

        del self.batch_paths[selected[0]]
        self._refresh_batch_list()

    def _clear_batch_list(self) -> None:
        self.batch_paths.clear()
        self._refresh_batch_list()

    def _refresh_batch_list(self) -> None:
        self.batch_listbox.delete(0, "end")
        for path in self.batch_paths:
            self.batch_listbox.insert("end", Path(path).name)

    def _set_batch_controls_state(self, state: str) -> None:
        for control in getattr(self, "batch_controls", []):
            control.configure(state=state)

    def _show_how_to_use(self) -> None:
        self._show_help_dialog(
            "How to Use VideoText",
            get_how_to_use_text(),
            formatted_guide=True,
        )

    def _show_about(self) -> None:
        self._show_help_dialog(
            f"About {APP_NAME}",
            get_about_text(),
            formatted_about=True,
        )

    def _show_accuracy_validation(self) -> None:
        self._show_help_dialog(
            "Accuracy & Validation",
            get_accuracy_validation_text(),
            formatted_accuracy=True,
        )

    def _show_help_dialog(
        self,
        title: str,
        content: str,
        formatted_guide: bool = False,
        formatted_about: bool = False,
        formatted_accuracy: bool = False,
    ) -> None:
        """Display selectable, scrollable in-app help in a custom window."""

        dialog = tk.Toplevel(self.master)
        dialog.title(title)
        dialog.transient(self.master)
        dialog.resizable(True, True)
        _center_dialog(dialog, self.master, preferred_width=760, preferred_height=600)
        dialog.columnconfigure(0, weight=1)
        dialog.rowconfigure(0, weight=1)

        help_text = scrolledtext.ScrolledText(
            dialog,
            wrap="word",
            padx=12,
            pady=12,
        )
        help_text.grid(row=0, column=0, sticky="nsew", padx=12, pady=(12, 6))
        if formatted_guide:
            _insert_formatted_user_guide(help_text, content)
        elif formatted_accuracy:
            _insert_formatted_accuracy_validation(help_text, content)
        elif formatted_about:
            _insert_formatted_about(help_text, get_about_sections())
        else:
            help_text.insert("1.0", content)
        help_text.configure(state="disabled")

        button_frame = ttk.Frame(dialog)
        button_frame.grid(row=1, column=0, sticky="e", padx=12, pady=(0, 12))

        def close_dialog() -> None:
            dialog.destroy()

        close_button = ttk.Button(button_frame, text="Close", command=close_dialog)
        close_button.grid(row=0, column=0)
        dialog.protocol("WM_DELETE_WINDOW", close_dialog)
        dialog.bind("<Escape>", lambda _event: close_dialog())
        close_button.focus_set()

    def _browse_output_folder(self) -> None:
        initial_directory = valid_initial_directory(
            self.preferences.last_output_folder,
        ) or valid_initial_directory(self.preferences.default_output_folder)
        path = filedialog.askdirectory(
            title="Select Output Folder",
            initialdir=initial_directory,
        )
        if path:
            self.output_folder.set(path)
            self._remember_selected_folder("last_output_folder", Path(path))

    def _toggle_advanced_mode(self) -> None:
        """Show resume controls only when a user explicitly enables them."""

        if self.advanced_mode.get():
            self.video_label.grid_remove()
            self.video_entry.grid_remove()
            self.video_browse_button.grid_remove()
            self.advanced_source_path.set(self.video_path.get())
            self.advanced_frame.grid(
                row=3,
                column=0,
                columnspan=3,
                sticky="ew",
                pady=(0, 8),
            )
        else:
            self.advanced_frame.grid_remove()
            self.video_label.grid()
            self.video_entry.grid()
            self.video_browse_button.grid()

    def _browse_advanced_source(self) -> None:
        """Select a video for full mode, or a checkpoint file/run folder."""

        mode = ProcessingMode(self.advanced_start_mode.get())
        if mode is ProcessingMode.FULL_VIDEO:
            path = filedialog.askopenfilename(
                title="Select Video File",
                filetypes=[
                    ("Video files", "*.mp4 *.avi *.mov *.mkv"),
                    ("All files", "*.*"),
                ],
                initialdir=valid_initial_directory(
                    self.preferences.last_single_video_folder,
                ),
            )
        else:
            path = filedialog.askopenfilename(
                title="Select Checkpoint File (or cancel to choose a run folder)",
                filetypes=[("Checkpoint files", "*.pkl"), ("All files", "*.*")],
                initialdir=valid_initial_directory(
                    self.preferences.last_checkpoint_folder,
                ),
            )
            if not path:
                path = filedialog.askdirectory(title="Select Prior Run Folder")

        if path:
            self.advanced_source_path.set(path)
            folder = Path(path) if Path(path).is_dir() else Path(path).parent
            preference_field = (
                "last_single_video_folder"
                if mode is ProcessingMode.FULL_VIDEO
                else "last_checkpoint_folder"
            )
            self._remember_selected_folder(preference_field, folder)

    def _start_processing(self) -> None:
        if self.processing:
            return

        if self.run_mode.get() == "batch":
            self._start_batch_processing()
            return

        mode = (
            ProcessingMode(self.advanced_start_mode.get())
            if self.advanced_mode.get()
            else ProcessingMode.FULL_VIDEO
        )
        source_path = (
            self.advanced_source_path.get()
            if self.advanced_mode.get()
            else self.video_path.get()
        )
        source = Path(source_path)
        output_folder = Path(self.output_folder.get())

        if mode is ProcessingMode.FULL_VIDEO and (
            not source_path or not source.is_file()
        ):
            self._set_status("Select a valid video file.")
            return

        if mode is not ProcessingMode.FULL_VIDEO and (
            not source_path or not source.exists()
        ):
            self._set_status("Select a valid checkpoint file or prior run folder.")
            return

        if not self.output_folder.get() or not output_folder.is_dir():
            self._set_status("Select a valid output folder.")
            return

        if not os.access(output_folder, os.W_OK):
            self._set_status("Select a writable output folder.")
            return

        selected_formats = [
            name
            for name, variable in self.format_options.items()
            if variable.get()
        ]

        if not selected_formats:
            self._set_status("Select at least one export format.")
            return

        self.processing = True
        self.process_button.configure(state="disabled")
        self._reset_progress()
        self._append_log(f"Processing mode: {mode.value}")
        self._append_log(f"Source selected: {source}")
        self._append_log(f"Output folder selected: {output_folder}")
        self._append_log(
            "Selected formats: "
            + (", ".join(selected_formats) if selected_formats else "none")
        )

        worker = threading.Thread(
            target=self._run_processing_worker,
            args=(
                ProcessingRequest(
                    mode=mode,
                    source_path=str(source),
                    output_directory=output_folder,
                    formats=selected_formats,
                    progress_callback=self._queue_progress,
                ),
            ),
            daemon=True,
        )
        worker.start()
        self.after(100, self._poll_worker_messages)

    def _start_batch_processing(self) -> None:
        """Start a shared sequential full-video batch from the visible queue."""

        output_folder = Path(self.output_folder.get())
        if not self.batch_paths:
            self._set_status("Add at least one video to the batch queue.")
            return
        if not self.output_folder.get() or not output_folder.is_dir():
            self._set_status("Select a valid output folder.")
            return
        if not os.access(output_folder, os.W_OK):
            self._set_status("Select a writable output folder.")
            return

        selected_formats = [
            name
            for name, variable in self.format_options.items()
            if variable.get()
        ]
        if not selected_formats:
            self._set_status("Select at least one export format.")
            return

        self.processing = True
        self.process_button.configure(state="disabled")
        self._set_batch_controls_state("disabled")
        self._reset_progress()
        self._append_log(f"Batch videos selected: {len(self.batch_paths)}")
        self._append_log(f"Output folder selected: {output_folder}")
        self._append_log("Selected formats: " + ", ".join(selected_formats))

        worker = threading.Thread(
            target=self._run_batch_worker,
            args=(BatchProcessingRequest(
                source_paths=list(self.batch_paths),
                output_directory=output_folder,
                formats=selected_formats,
                progress_callback=self._queue_batch_progress,
            ),),
            daemon=True,
        )
        worker.start()
        self.after(100, self._poll_worker_messages)

    def _run_processing_worker(
        self,
        request: ProcessingRequest,
    ) -> None:
        """Run the pipeline without interacting with Tkinter widgets."""

        try:
            result = process_request(request)
            self.message_queue.put(("complete", result))

        except PermissionError as error:
            self.message_queue.put(("error", str(error)))

        except Exception as error:
            self.message_queue.put(
                ("error", f"{type(error).__name__}: {error}")
            )

    def _run_batch_worker(self, request: BatchProcessingRequest) -> None:
        """Run the shared batch service without interacting with Tkinter."""

        try:
            self.message_queue.put(("batch_complete", process_batch(request)))
        except Exception as error:
            self.message_queue.put(
                ("error", f"{type(error).__name__}: {error}")
            )

    def _queue_progress(self, progress: ProcessingProgress) -> None:
        """Receive worker status without touching Tkinter widgets."""

        self.message_queue.put(("progress", progress))

    def _queue_batch_progress(self, progress: BatchProgress) -> None:
        """Receive batch-worker updates without touching Tkinter widgets."""

        self.message_queue.put(("batch_progress", progress))

    def _poll_worker_messages(self) -> None:
        """Apply worker messages from Tkinter's main thread."""

        try:
            while True:
                message_type, payload = self.message_queue.get_nowait()

                if message_type == "progress":
                    self._show_progress(payload)

                elif message_type == "batch_progress":
                    self._show_batch_progress(payload)

                elif message_type == "complete":
                    self._append_log(f"Output folder: {payload.run_directory}")
                    for format_name, path in payload.exported_paths.items():
                        self._append_log(
                            f"Saved {format_name.title()}: {path}"
                        )
                    self._finish_processing()
                    self._open_completed_folder(payload.run_directory)
                    self._show_completion_dialog(payload)

                elif message_type == "batch_complete":
                    for item in payload.failed_items:
                        self._append_log(
                            f"FAILED: {Path(item.source_path).name}\n"
                            f"Reason: {item.error_message}"
                        )
                    self._finish_processing()
                    self._set_batch_controls_state("normal")
                    if payload.successful_items:
                        self._open_completed_folder(payload.log_path.parent)
                    self._show_batch_completion_dialog(payload)

                elif message_type == "error":
                    self._set_status(f"Processing failed: {payload}")
                    self._finish_processing()
                    self._set_batch_controls_state("normal")

        except queue.Empty:
            pass

        if self.processing:
            self.after(100, self._poll_worker_messages)

    def _show_batch_progress(self, batch_progress: BatchProgress) -> None:
        prefix = (
            f"Video {batch_progress.current_item} of "
            f"{batch_progress.total_items}: {batch_progress.filename}"
        )
        if batch_progress.progress is None:
            self.status.set(prefix)
            self._append_log(prefix)
        else:
            self._show_progress(batch_progress.progress, prefix=prefix)

    def _show_progress(
        self,
        progress: ProcessingProgress,
        prefix: str | None = None,
    ) -> None:
        """Render a worker event in Tkinter's main thread."""

        step = ""
        if progress.step_current is not None and progress.step_total is not None:
            step = f"Step {progress.step_current} of {progress.step_total}\n"

        message = step + progress.message
        if progress.current is not None and progress.total is not None:
            if progress.stage == "frame_selection":
                percentage = (
                    f" ({progress.percentage:.0f}%)"
                    if progress.percentage is not None
                    else ""
                )
                message += f"\n{progress.current:,} / {progress.total:,} frames{percentage}"
            elif progress.stage == "ocr":
                message += (
                    f"\nCandidate frame {progress.current} of {progress.total}"
                )
            else:
                item_label = "frame " if progress.stage in {"ocr", "reading_order"} else ""
                message += f" — {item_label}{progress.current} of {progress.total}"
            self.progress_bar.stop()
            self.progress_bar.configure(mode="determinate", maximum=progress.total)
            self.progress_value.set(progress.current)
        elif progress.stage == "frame_selection" and progress.current is not None:
            message += f"\n{progress.current:,} frames processed"
            self.progress_bar.configure(mode="indeterminate")
            self.progress_bar.start(10)
        elif progress.stage == "complete":
            self.progress_bar.stop()
            self.progress_bar.configure(mode="determinate", maximum=100)
            self.progress_value.set(100)
        else:
            self.progress_bar.configure(mode="indeterminate")
            self.progress_bar.start(10)

        details = f"Phase elapsed: {format_duration(progress.elapsed_seconds)}"
        if progress.estimated_remaining_seconds is not None:
            details += (
                " | Estimated phase remaining: "
                f"{format_duration(progress.estimated_remaining_seconds)}"
            )

        if prefix is not None:
            message = f"{prefix}\n{message}"

        self.status.set(message)
        self.progress_details.set(details)
        self._append_log(f"{message} | {details}")

    def _finish_processing(self) -> None:
        self.processing = False
        self.progress_bar.stop()
        self.process_button.configure(state="normal")

    def _open_completed_folder(self, folder: Path) -> None:
        """Optionally open one successful output folder without affecting success."""

        if not getattr(self, "preferences", Preferences()).open_output_folder_after_completion:
            return

        warning = open_folder(folder)
        if warning:
            self._append_log(f"Warning: {warning}")

    def _set_status(self, message: str) -> None:
        self._reset_progress()
        self.status.set(message)
        self._append_log(message)

    def _reset_progress(self) -> None:
        """Clear determinate values and stale ETA after a start or failure."""

        self.progress_bar.stop()
        self.progress_bar.configure(mode="determinate", maximum=100)
        self.progress_value.set(0)
        self.progress_details.set("")

    def _show_completion_dialog(self, result) -> None:
        """Show the shared completion summary in a readable modal dialog."""

        dialog = tk.Toplevel(self.master)
        dialog.title("Processing Complete")
        dialog.transient(self.master)

        _center_dialog(dialog, self.master, preferred_width=700, preferred_height=500)
        dialog.minsize(300, 240)

        dialog.columnconfigure(0, weight=1)
        dialog.rowconfigure(1, weight=1)
        ttk.Label(
            dialog,
            text="Processing Complete",
            font=("TkDefaultFont", 12, "bold"),
        ).grid(row=0, column=0, sticky="w", padx=12, pady=(12, 6))

        text_frame = ttk.Frame(dialog)
        text_frame.grid(row=1, column=0, sticky="nsew", padx=12)
        text_frame.columnconfigure(0, weight=1)
        text_frame.rowconfigure(0, weight=1)

        summary_text = tk.Text(
            text_frame,
            wrap="none",
            height=20,
            padx=8,
            pady=8,
        )
        summary_text.grid(row=0, column=0, sticky="nsew")
        vertical_scrollbar = ttk.Scrollbar(
            text_frame,
            orient="vertical",
            command=summary_text.yview,
        )
        vertical_scrollbar.grid(row=0, column=1, sticky="ns")
        horizontal_scrollbar = ttk.Scrollbar(
            text_frame,
            orient="horizontal",
            command=summary_text.xview,
        )
        horizontal_scrollbar.grid(row=1, column=0, sticky="ew")
        summary_text.configure(
            yscrollcommand=vertical_scrollbar.set,
            xscrollcommand=horizontal_scrollbar.set,
        )
        summary_text.insert(
            "1.0",
            _format_completion_dialog_text(format_processing_summary(result)),
        )
        summary_text.configure(state="disabled")

        button_frame = ttk.Frame(dialog)
        button_frame.grid(row=2, column=0, sticky="e", padx=12, pady=12)

        def close_dialog() -> None:
            dialog.grab_release()
            dialog.destroy()

        close_button = ttk.Button(
            button_frame,
            text="Close",
            command=close_dialog,
        )
        close_button.grid(row=0, column=0)
        dialog.protocol("WM_DELETE_WINDOW", close_dialog)
        dialog.bind("<Escape>", lambda _event: close_dialog())
        dialog.bind("<Return>", lambda _event: close_dialog())
        dialog.grab_set()
        close_button.focus_set()

    def _show_batch_completion_dialog(self, result) -> None:
        """Show one selectable custom summary after all batch items finish."""

        dialog = tk.Toplevel(self.master)
        dialog.title("Batch Processing Complete")
        dialog.transient(self.master)
        dialog.resizable(True, True)
        _center_dialog(dialog, self.master, preferred_width=700, preferred_height=500)
        dialog.columnconfigure(0, weight=1)
        dialog.rowconfigure(0, weight=1)

        summary_text = tk.Text(dialog, wrap="none", padx=8, pady=8)
        summary_text.grid(row=0, column=0, sticky="nsew", padx=(12, 0), pady=(12, 0))
        scrollbar = ttk.Scrollbar(dialog, orient="vertical", command=summary_text.yview)
        scrollbar.grid(row=0, column=1, sticky="ns", pady=(12, 0))
        horizontal_scrollbar = ttk.Scrollbar(
            dialog,
            orient="horizontal",
            command=summary_text.xview,
        )
        horizontal_scrollbar.grid(row=1, column=0, sticky="ew", padx=(12, 0))
        summary_text.configure(
            yscrollcommand=scrollbar.set,
            xscrollcommand=horizontal_scrollbar.set,
        )
        summary_text.insert("1.0", format_batch_summary(result))
        summary_text.configure(state="disabled")

        def close_dialog() -> None:
            dialog.destroy()

        close_button = ttk.Button(dialog, text="Close", command=close_dialog)
        close_button.grid(row=2, column=0, columnspan=2, sticky="e", padx=12, pady=(6, 12))
        dialog.protocol("WM_DELETE_WINDOW", close_dialog)
        dialog.bind("<Escape>", lambda _event: close_dialog())
        close_button.focus_set()

    def _append_log(self, message: str) -> None:
        self.log_text.configure(state="normal")
        self.log_text.insert("end", message + "\n")
        self.log_text.see("end")
        self.log_text.configure(state="disabled")


def _insert_formatted_help_topic(
    text_widget: tk.Text,
    content: str,
    title: str,
    headings: set[str],
    subheadings: set[str] = set(),
) -> None:
    """Insert a selectable help topic with the shared accessible Text tags."""

    text_widget.tag_configure(
        "title",
        font=("TkDefaultFont", 16, "bold"),
        justify="center",
        spacing1=6,
        spacing3=18,
    )
    text_widget.tag_configure(
        "heading",
        font=("TkDefaultFont", 13, "bold"),
        spacing1=16,
        spacing3=6,
    )
    text_widget.tag_configure(
        "subheading",
        font=("TkDefaultFont", 11, "bold"),
        spacing1=10,
        spacing3=2,
    )
    text_widget.tag_configure("body", spacing3=7)
    text_widget.tag_configure(
        "bullet",
        lmargin1=20,
        lmargin2=36,
        spacing3=3,
    )
    text_widget.tag_configure("code", font=("Courier New", 10), spacing3=8)
    text_widget.tag_configure(
        "note",
        font=("TkDefaultFont", 10, "bold"),
        lmargin1=12,
        lmargin2=12,
        spacing1=10,
        spacing3=4,
    )

    code_block = False

    for line in content.splitlines():
        if line == title:
            tag = "title"
        elif line in headings:
            tag = "heading"
        elif line in subheadings:
            tag = "subheading"
        elif line == "Note":
            tag = "note"
        elif line == "output/":
            code_block = True
            tag = "code"
        elif not line:
            code_block = False
            tag = "body"
        elif code_block:
            tag = "code"
        elif line.startswith(("• ", "1. ", "2. ", "3. ", "4. ", "5. ")):
            tag = "bullet"
        else:
            tag = "body"
        text_widget.insert("end", line + "\n", tag)


def _insert_formatted_user_guide(text_widget: tk.Text, content: str) -> None:
    """Insert the built-in user guide with reusable, accessible Text tags."""
    _insert_formatted_help_topic(
        text_widget,
        content,
        "VideoText User Guide",
        {
            "What is VideoText?",
            "Getting Started",
            "Processing Stages",
            "Export Formats",
            "Batch Processing",
            "Advanced Mode (Replay)",
            "Output Folder Structure",
            "Tips",
            "Troubleshooting",
        },
        {
            "Markdown",
            "CSV",
            "Excel Translation Workbook",
            "Slow OCR",
            "Missing text",
            "Replay availability",
            "Output location",
        },
    )


def _insert_formatted_accuracy_validation(
    text_widget: tk.Text,
    content: str,
) -> None:
    """Insert the Accuracy & Validation topic with the shared Help style."""
    _insert_formatted_help_topic(
        text_widget,
        content,
        "Accuracy & Validation",
        {
            "What VideoText Is Designed For",
            "How VideoText Works",
            "Expected Accuracy",
            "Factors That Affect Accuracy",
            "Validation",
            "Engineering Philosophy",
            "Future Validation",
            "Practical Recommendation",
        },
    )


def _insert_formatted_about(
    text_widget: tk.Text,
    sections: tuple[tuple[str, tuple[str, ...]], ...],
) -> None:
    """Insert shared About content with a compact visual hierarchy."""

    text_widget.tag_configure(
        "about_title",
        font=("TkDefaultFont", 16, "bold"),
        justify="center",
        spacing1=8,
        spacing3=4,
    )
    text_widget.tag_configure(
        "about_version",
        font=("TkDefaultFont", 11, "bold"),
        justify="center",
        spacing3=2,
    )
    text_widget.tag_configure(
        "about_status",
        font=("TkDefaultFont", 10, "italic"),
        justify="center",
        spacing3=8,
    )
    text_widget.tag_configure(
        "about_rule",
        justify="center",
        spacing3=12,
    )
    text_widget.tag_configure(
        "about_heading",
        font=("TkDefaultFont", 12, "bold"),
        spacing1=10,
        spacing3=5,
    )
    text_widget.tag_configure("about_body", spacing3=7)
    text_widget.tag_configure(
        "about_bullet",
        lmargin1=20,
        lmargin2=36,
        spacing3=3,
    )
    text_widget.tag_configure(
        "about_footer",
        font=("TkDefaultFont", 9),
        justify="center",
        spacing1=12,
    )

    text_widget.insert("end", APP_NAME + "\n", "about_title")
    version_text = f"Version {APP_RELEASE}"
    text_widget.insert("end", version_text + "\n", "about_version")
    text_widget.insert("end", APP_STATUS + "\n", "about_status")
    text_widget.insert("end", "─" * 52 + "\n", "about_rule")
    text_widget.insert("end", get_about_introduction() + "\n", "about_body")

    for heading, items in sections:
        text_widget.insert("end", heading + "\n", "about_heading")
        for item in items:
            tag = "about_bullet" if item.startswith("• ") else "about_body"
            text_widget.insert("end", item + "\n", tag)

    text_widget.insert("end", "\n" + APP_COPYRIGHT + "\n", "about_footer")


def _center_dialog(
    dialog: tk.Toplevel,
    parent: tk.Tk,
    preferred_width: int,
    preferred_height: int,
) -> None:
    """Size a dialog sensibly and center it within the available screen."""

    screen_width = dialog.winfo_screenwidth()
    screen_height = dialog.winfo_screenheight()
    width = min(preferred_width, max(300, screen_width - 80))
    height = min(preferred_height, max(240, screen_height - 120))
    parent.update_idletasks()
    x = min(
        screen_width - width,
        max(0, parent.winfo_rootx() + (parent.winfo_width() - width) // 2),
    )
    y = min(
        screen_height - height,
        max(0, parent.winfo_rooty() + (parent.winfo_height() - height) // 2),
    )
    dialog.geometry(f"{width}x{height}+{x}+{y}")


def _format_completion_dialog_text(summary: str) -> str:
    """Present shared summary data in readable sections without recomputing it."""

    fields: dict[str, str] = {}
    exports: list[tuple[str, str]] = []
    in_exports = False

    for line in summary.splitlines():
        if line == "Exports:":
            in_exports = True
            continue
        if in_exports and line.startswith("- ") and ": " in line:
            label, path = line[2:].split(": ", maxsplit=1)
            exports.append((label, path))
        elif not in_exports and ": " in line:
            label, value = line.split(": ", maxsplit=1)
            fields[label] = value

    frame_labels = (
        "Candidate frames processed",
        "Candidate frames loaded",
        "OCR frames processed",
        "Reading-order frames loaded",
    )
    frame_line = next(
        (
            f"{('OCR frames' if label == 'OCR frames processed' else label)}: "
            f"{fields[label]}"
            for label in frame_labels
            if label in fields
        ),
        None,
    )

    lines = [
        "Processing Complete",
        "",
        "Run Summary",
        "--------------------",
    ]
    for label in ("Mode",):
        if label in fields:
            lines.append(f"{label}: {fields[label]}")
    if frame_line is not None:
        lines.append(frame_line)
    if "Slides created" in fields:
        lines.append(f"Slides: {fields['Slides created']}")
    if "Elapsed time" in fields:
        lines.append(f"Elapsed: {fields['Elapsed time']}")

    lines.extend(["", "Source", "--------------------"])
    if "Source" in fields:
        lines.extend(("Source:", fields["Source"]))
    if "Resolved checkpoint" in fields:
        lines.extend(("", "Resolved checkpoint:", fields["Resolved checkpoint"]))

    lines.extend(["", "Output", "--------------------"])
    if "Output folder" in fields:
        lines.append(fields["Output folder"])

    lines.extend(["", "Exports", "--------------------"])
    for label, path in exports:
        lines.extend((label, f"    {path}", ""))

    return "\n".join(lines).rstrip()


def main() -> None:
    """Launch the VideoText GUI shell."""

    root = tk.Tk()
    VideoTextApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
