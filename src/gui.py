"""
gui.py

Initial desktop GUI shell for VideoText.
"""

import os
from pathlib import Path
import queue
import sys
import threading
import tkinter as tk
import traceback
from tkinter import filedialog, messagebox, simpledialog, scrolledtext, ttk

from app_info import APP_COPYRIGHT, APP_NAME, APP_RELEASE, APP_STATUS
from help_content import (
    get_about_introduction,
    get_about_sections,
    get_about_text,
    get_accuracy_validation_text,
    get_accessibility_text,
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
    add_recent_source,
    clear_recent_sources,
)

from processing_service import (
    ProcessingMode,
    ProcessingProgress,
    ProcessingRequest,
    format_bytes,
    format_duration,
    format_processing_summary,
    process_request,
)
from video_source import VideoSource, VideoSourceError
from openai_translation_provider import OpenAITranslationConfig, OpenAITranslationProvider
from local_translation_provider import (LocalCTranslate2Provider, LocalTranslationConfig,
    default_local_translation_model_root, inspect_installed_local_translation_models)
from runtime_diagnostics import write_gui_diagnostic
from translation_application import TranslationApplicationSource, run_translation_job
from translation_job import TranslationOutputGrouping, TranslationSourceItem
from translation_settings import (
    OPENAI_TRANSLATION_MODEL, RECOMMENDED_OPENAI_MODEL_LABEL,
    TRANSLATION_TARGET_LOCALES, VETTED_OPENAI_TRANSLATION_MODELS,
    resolve_vetted_openai_model, translation_locale_display_name,
)


def _application_icon_path() -> Path:
    """Return the bundled VideoText icon for the main Tkinter window."""

    if getattr(sys, "frozen", False):
        resource_root = Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    else:
        resource_root = Path(__file__).resolve().parent.parent
    return resource_root / "icons" / "VT-icon.ico"


def _next_locale_control_index(current_index: int, control_count: int, direction: int) -> int:
    """Return the wrapped keyboard-navigation index for selectable locales."""

    if control_count <= 0:
        raise ValueError("Locale navigation requires at least one selectable control.")
    return (current_index + direction) % control_count


class VideoTextApp(ttk.Frame):
    """Top-level layout and placeholder interactions for VideoText."""

    def __init__(self, master: tk.Tk):
        super().__init__(master, padding=12)
        self.master = master
        self.preferences = load_preferences()
        self.preferences_dialog: tk.Toplevel | None = None
        self.video_path = tk.StringVar()
        self.video_source_type = tk.StringVar(value="local")
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
        self.batch_excel_consolidated = tk.BooleanVar(value=False)
        self.translation_enabled = tk.BooleanVar(value=False)
        self.translation_provider = tk.StringVar(value="")
        self.translation_model = tk.StringVar(value=RECOMMENDED_OPENAI_MODEL_LABEL)
        self.translation_grouping = tk.StringVar(value=TranslationOutputGrouping.BY_SOURCE.value)
        self.translation_languages = {code: tk.BooleanVar(value=False) for code, _label in TRANSLATION_TARGET_LOCALES}
        self.translation_formats = {"excel": tk.BooleanVar(value=True), "csv": tk.BooleanVar(value=False), "markdown": tk.BooleanVar(value=False)}
        # Manifest discovery is deliberately lightweight.  Do not import the
        # CTranslate2 runtime or construct a provider until downstream
        # translation begins after OCR has completed.
        self.local_translation_model_root = default_local_translation_model_root()
        self.local_translation_availability = inspect_installed_local_translation_models(
            self.local_translation_model_root,
        )
        self.batch_controls: list[ttk.Button] = []
        self.batch_excel_controls: list[ttk.Radiobutton] = []
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
        file_menu = tk.Menu(menu_bar, tearoff=False)
        self.recent_sources_menu = tk.Menu(file_menu, tearoff=False)
        file_menu.add_cascade(
            label="Recent Sources",
            underline=0,
            menu=self.recent_sources_menu,
        )
        file_menu.add_command(label="Clear Recent Sources", command=self._clear_recent_sources)
        menu_bar.add_cascade(label="File", underline=0, menu=file_menu)
        edit_menu = tk.Menu(menu_bar, tearoff=False)
        edit_menu.add_command(label="Preferences...", command=self._show_preferences)
        menu_bar.add_cascade(label="Edit", underline=0, menu=edit_menu)
        help_menu = tk.Menu(menu_bar, tearoff=False)
        help_menu.add_command(
            label="How to Use VideoText",
            command=self._show_how_to_use,
        )
        help_menu.add_command(
            label="Accuracy & Validation",
            command=self._show_accuracy_validation,
        )
        help_menu.add_command(label="Accessibility", command=self._show_accessibility)
        help_menu.add_command(
            label="About VideoText",
            command=self._show_about,
        )
        menu_bar.add_cascade(label="Help", underline=0, menu=help_menu)
        self.master.configure(menu=menu_bar)
        self._refresh_recent_sources_menu()

    def _build_layout(self) -> None:
        self.master.title("VideoText")
        self.master.iconbitmap(default=str(_application_icon_path()))
        self.master.minsize(650, 500)

        self.grid(sticky="nsew")
        self.master.columnconfigure(0, weight=1)
        self.master.rowconfigure(0, weight=1)
        self.columnconfigure(1, weight=1)
        self.rowconfigure(10, weight=1)

        self.source_choice_frame = ttk.Frame(self)
        self.source_choice_frame.grid(
            row=0, column=0, columnspan=3, sticky="w", pady=(0, 4),
        )
        ttk.Label(self.source_choice_frame, text="Video Source").grid(
            row=0, column=0, padx=(0, 12), sticky="w",
        )
        ttk.Radiobutton(
            self.source_choice_frame,
            text="Local File",
            value="local",
            variable=self.video_source_type,
            command=self._set_video_source_type,
        ).grid(row=0, column=1, padx=(0, 12), sticky="w")
        ttk.Radiobutton(
            self.source_choice_frame,
            text="URL",
            value="url",
            variable=self.video_source_type,
            command=self._set_video_source_type,
        ).grid(row=0, column=2, sticky="w")
        ttk.Label(
            self.source_choice_frame,
            text="Enter a direct HTTP or HTTPS link to a video file.",
        ).grid(row=1, column=1, columnspan=2, sticky="w", pady=(2, 0))

        self.video_label = ttk.Label(self, text="Video File")
        self.video_label.grid(
            row=1,
            column=0,
            sticky="w",
            padx=(0, 8),
            pady=(0, 8),
        )
        self.video_entry = ttk.Entry(self, textvariable=self.video_path)
        self.video_entry.grid(
            row=1,
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
            row=1,
            column=2,
            padx=(8, 0),
            pady=(0, 8),
        )

        mode_frame = ttk.LabelFrame(self, text="Processing Mode", padding=6)
        mode_frame.grid(row=2, column=0, columnspan=3, sticky="ew", pady=(0, 8))
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
        self.advanced_checkbutton.grid(row=3, column=0, columnspan=3, sticky="w", pady=(0, 8))

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
        self.batch_excel_frame = ttk.LabelFrame(self.batch_frame, text="Excel output", padding=6)
        self.batch_excel_frame.grid(row=2, column=0, columnspan=4, sticky="w")
        per_video_excel = ttk.Radiobutton(
            self.batch_excel_frame,
            text="One workbook per video",
            value=False,
            variable=self.batch_excel_consolidated,
        )
        per_video_excel.grid(row=0, column=0, padx=(0, 12), sticky="w")
        consolidated_excel = ttk.Radiobutton(
            self.batch_excel_frame,
            text="One workbook for the entire batch",
            value=True,
            variable=self.batch_excel_consolidated,
        )
        consolidated_excel.grid(row=0, column=1, sticky="w")
        self.batch_excel_controls.extend((per_video_excel, consolidated_excel))

        ttk.Label(self, text="Output Folder").grid(
            row=5,
            column=0,
            sticky="w",
            padx=(0, 8),
            pady=(0, 8),
        )
        ttk.Entry(self, textvariable=self.output_folder).grid(
            row=5,
            column=1,
            sticky="ew",
            pady=(0, 8),
        )
        ttk.Button(self, text="Browse", command=self._browse_output_folder).grid(
            row=5,
            column=2,
            padx=(8, 0),
            pady=(0, 8),
        )

        formats_frame = ttk.LabelFrame(self, text="OCR Outputs", padding=8)
        formats_frame.grid(
            row=6,
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
                command=self._update_batch_excel_options if name == "excel" else None,
            ).grid(row=0, column=column, padx=(0, 16), sticky="w")
        self._update_batch_excel_options()

        self.translation_frame = ttk.LabelFrame(self, text="Optional Translation", padding=8)
        self.translation_frame.grid(row=7, column=0, columnspan=3, sticky="ew", pady=(0, 8))
        ttk.Checkbutton(self.translation_frame, text="Translate OCR text", variable=self.translation_enabled,
                        command=self._update_translation_controls).grid(row=0, column=0, columnspan=3, sticky="w")
        self.translation_controls = []
        ttk.Label(self.translation_frame, text="Provider").grid(row=1, column=0, sticky="w", pady=(6, 0))
        openai = ttk.Radiobutton(self.translation_frame, text="OpenAI Cloud — Uses your OpenAI API key", value="openai", variable=self.translation_provider)
        openai.grid(row=1, column=1, sticky="w", pady=(6, 0)); self.translation_controls.append(openai)
        local_state = "normal" if self.local_translation_availability.installed_models else "disabled"
        local_text = ("Local Translation - Offline, no API key required"
                      if self.local_translation_availability.installed_models
                      else "Local Translation (No approved models installed)")
        self.local_translation_control = ttk.Radiobutton(
            self.translation_frame, text=local_text, value="local", variable=self.translation_provider,
            state=local_state, command=self._update_translation_provider_view)
        self.local_translation_control.grid(row=2, column=1, columnspan=2, sticky="w")
        ttk.Label(self.translation_frame, text="Model").grid(row=3, column=0, sticky="w")
        model_selector = ttk.Combobox(self.translation_frame, textvariable=self.translation_model,
            values=tuple(label for label, _model in VETTED_OPENAI_TRANSLATION_MODELS), state="readonly", width=32)
        model_selector.grid(row=3, column=1, sticky="w"); self.translation_controls.append(model_selector)
        self.translation_model_selector = model_selector
        self.translation_provider_detail = ttk.Label(self.translation_frame, text="Internet required • API charges may apply to your account")
        self.translation_provider_detail.grid(row=3, column=2, sticky="w")
        ttk.Label(self.translation_frame, text="Target locales").grid(row=4, column=0, sticky="w", pady=(6, 0))
        self.translation_locale_summary = tk.StringVar()
        self.translation_locale_button = ttk.Button(
            self.translation_frame,
            textvariable=self.translation_locale_summary,
            command=self._show_translation_locale_selector,
        )
        self.translation_locale_button.grid(row=4, column=1, columnspan=2, sticky="w", pady=(6, 0))
        self.translation_controls.append(self.translation_locale_button)

        self.single_translation_grouping_label = ttk.Label(
            self.translation_frame,
            text="Workbook organization: One workbook per video",
        )
        self.single_translation_grouping_label.grid(row=5, column=0, columnspan=3, sticky="w", pady=(6, 0))
        self.translation_grouping_frame = ttk.Frame(self.translation_frame)
        self.translation_grouping_frame.grid(row=5, column=0, columnspan=3, sticky="w", pady=(6, 0))
        self.translation_grouping_controls = []
        for index, (label, value) in enumerate((("One workbook per language", "by_language"),("One workbook per video", "by_source"),("One combined workbook", "combined"),("Separate workbook per video/language", "separate"))):
            control = ttk.Radiobutton(self.translation_grouping_frame, text=label, value=value, variable=self.translation_grouping)
            control.grid(row=index // 2, column=index % 2, padx=(0, 16), sticky="w")
            self.translation_controls.append(control)
            self.translation_grouping_controls.append(control)

        self.translation_outputs_frame = ttk.LabelFrame(
            self.translation_frame, text="Translation Outputs", padding=6,
        )
        self.translation_outputs_frame.grid(row=6, column=0, columnspan=3, sticky="w", pady=(6, 0))
        translation_output_labels = {
            "excel": "Translation Review Workbook",
            "csv": "Translation CSV",
            "markdown": "Translation Markdown",
        }
        for index, (name, variable) in enumerate(self.translation_formats.items()):
            control = ttk.Checkbutton(
                self.translation_outputs_frame,
                text=translation_output_labels[name],
                variable=variable,
            )
            control.grid(row=0, column=index, padx=(0, 16), sticky="w")
            self.translation_controls.append(control)
        self.translation_provider.trace_add("write", lambda *_args: self._update_translation_provider_view())
        self._update_translation_workbook_grouping()
        self._update_translation_controls()

        self.process_button = ttk.Button(
            self,
            text="Process",
            command=self._start_processing,
        )
        self.process_button.grid(
            row=8,
            column=0,
            columnspan=3,
            pady=(0, 8),
        )

        progress_frame = ttk.LabelFrame(self, text="Progress", padding=8)
        progress_frame.grid(
            row=9,
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
            row=10,
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

    def _set_video_source_type(self) -> None:
        """Keep one source entry while making its local/URL purpose explicit."""

        is_url = self.video_source_type.get() == "url"
        self.video_label.configure(text="Video URL" if is_url else "Video File")
        self.video_browse_button.configure(state="disabled" if is_url else "normal")

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
            self._restore_main_focus()

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
        dialog.bind("<Return>", lambda _event: save_dialog())
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
            self.source_choice_frame.grid_remove()
            self.video_label.grid_remove()
            self.video_entry.grid_remove()
            self.video_browse_button.grid_remove()
            self.advanced_checkbutton.grid_remove()
            self.advanced_frame.grid_remove()
            self.batch_frame.grid(
                row=4,
                column=0,
                columnspan=3,
                sticky="ew",
                pady=(0, 8),
            )
        else:
            self.batch_frame.grid_remove()
            self.advanced_checkbutton.grid()
            if self.advanced_mode.get():
                self.source_choice_frame.grid_remove()
                self.video_label.grid_remove()
                self.video_entry.grid_remove()
                self.video_browse_button.grid_remove()
                self.advanced_frame.grid(
                    row=4,
                    column=0,
                    columnspan=3,
                    sticky="ew",
                    pady=(0, 8),
                )
            else:
                self.source_choice_frame.grid()
                self.video_label.grid()
                self.video_entry.grid()
                self.video_browse_button.grid()

        self._update_batch_excel_options()
        self._update_translation_workbook_grouping()

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
            self._remember_recent_source(str(Path(folder)))
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

    def _update_batch_excel_options(self) -> None:
        """Allow consolidated Excel only when Excel is selected for a batch."""

        enabled = (
            self.run_mode.get() == "batch"
            and self.format_options["excel"].get()
        )
        # LabelFrame is a layout container and does not support ``state``.
        # Only the two interactive Excel-choice radiobuttons are enabled.
        for control in self.batch_excel_controls:
            control.configure(state="normal" if enabled else "disabled")
        if not enabled:
            self.batch_excel_consolidated.set(False)

    def _update_translation_controls(self) -> None:
        """Enable translation choices only after explicit user opt-in."""
        state = "normal" if self.translation_enabled.get() else "disabled"
        for control in self.translation_controls:
            control.configure(state=state)
        local_state = state if self.local_translation_availability.installed_models else "disabled"
        self.local_translation_control.configure(state=local_state)
        self._update_translation_provider_view()

    def _update_translation_provider_view(self) -> None:
        """Reflect provider availability and discard selections it cannot use."""

        local = self.translation_provider.get() == "local"
        self._discard_unavailable_translation_targets()
        self.translation_model_selector.configure(state="disabled" if local else
                                                 ("readonly" if self.translation_enabled.get() else "disabled"))
        self.translation_provider_detail.configure(
            text="Offline • No API key required" if local else "Internet required • API charges may apply to your account")
        self._update_translation_summary()

    def _available_translation_targets(self) -> set[str]:
        """Return the exact target locales usable by the selected provider."""

        if self.translation_provider.get() != "local":
            return set(self.translation_languages)
        return {target for source, target in self.local_translation_availability.installed_pairs
                if source in {"en", "en-US"}}

    def _discard_unavailable_translation_targets(self) -> tuple[str, ...]:
        """Deselect targets unsupported by the active provider, preserving valid choices."""

        available = self._available_translation_targets()
        discarded = []
        for code, variable in self.translation_languages.items():
            if variable.get() and code not in available:
                variable.set(False)
                discarded.append(code)
        return tuple(discarded)

    def _update_translation_summary(self) -> None:
        """Summarize compact locale state without hiding unavailable selections."""

        selected = [label for code, label in TRANSLATION_TARGET_LOCALES
                    if self.translation_languages[code].get()]
        unavailable = set(self.translation_languages) - self._available_translation_targets()
        unavailable_selected = sum(self.translation_languages[code].get() for code in unavailable)
        if not selected:
            text = "Choose target locales…"
        elif len(selected) <= 2:
            text = "; ".join(selected)
        else:
            text = f"{len(selected)} locales selected"
        if unavailable_selected:
            text += f" ({unavailable_selected} unavailable)"
        self.translation_locale_summary.set(text)

    def _show_translation_locale_selector(self) -> None:
        """Open a native-control, keyboard-accessible multi-locale chooser."""

        if not self.translation_enabled.get():
            return
        dialog = tk.Toplevel(self.master)
        dialog.title("Target Locales")
        dialog.transient(self.master)
        dialog.resizable(True, False)
        dialog.columnconfigure(0, weight=1)
        _center_dialog(dialog, self.master, preferred_width=520, preferred_height=390)
        ttk.Label(dialog, text="Target locales", font=("TkDefaultFont", 11, "bold")).grid(
            row=0, column=0, sticky="w", padx=12, pady=(12, 4),
        )
        ttk.Label(dialog, text="Use Up/Down or Tab to move, Space to select a locale, Enter to apply, or Escape to cancel.").grid(
            row=1, column=0, sticky="w", padx=12, pady=(0, 8),
        )
        choices = ttk.Frame(dialog)
        choices.grid(row=2, column=0, sticky="ew", padx=12)
        available = self._available_translation_targets()
        pending = {code: tk.BooleanVar(value=variable.get())
                   for code, variable in self.translation_languages.items()}
        first_enabled = None
        selectable_controls = []
        for row, (code, label) in enumerate(TRANSLATION_TARGET_LOCALES):
            enabled = code in available
            control = ttk.Checkbutton(
                choices, text=label if enabled else f"{label} — model not installed",
                variable=pending[code], state="normal" if enabled else "disabled",
            )
            control.grid(row=row, column=0, sticky="w", pady=2)
            if enabled:
                selectable_controls.append(control)
                if first_enabled is None:
                    first_enabled = control

        def move_locale_focus(current_index: int, direction: int):
            """Keep arrow navigation within selectable locale choices."""

            selectable_controls[
                _next_locale_control_index(current_index, len(selectable_controls), direction)
            ].focus_set()
            return "break"

        for index, control in enumerate(selectable_controls):
            control.bind("<Up>", lambda _event, index=index: move_locale_focus(index, -1))
            control.bind("<Down>", lambda _event, index=index: move_locale_focus(index, 1))
        buttons = ttk.Frame(dialog)
        buttons.grid(row=3, column=0, sticky="e", padx=12, pady=12)

        def close() -> None:
            dialog.destroy()
            self.translation_locale_button.focus_set()

        def apply() -> None:
            for code, variable in self.translation_languages.items():
                if code in available:
                    variable.set(pending[code].get())
            self._update_translation_summary()
            close()

        ttk.Button(buttons, text="Cancel", command=close).grid(row=0, column=0, padx=(0, 8))
        apply_button = ttk.Button(buttons, text="Apply", command=apply)
        apply_button.grid(row=0, column=1)
        dialog.protocol("WM_DELETE_WINDOW", close)
        dialog.bind("<Escape>", lambda _event: close())
        dialog.bind("<Return>", lambda _event: apply())
        dialog.grab_set()
        (first_enabled or apply_button).focus_set()

    def _update_translation_workbook_grouping(self) -> None:
        """Expose only the useful default grouping for a single video."""

        if self.run_mode.get() == "single":
            self.translation_grouping.set(TranslationOutputGrouping.BY_SOURCE.value)
            self.translation_grouping_frame.grid_remove()
            self.single_translation_grouping_label.grid()
        else:
            self.single_translation_grouping_label.grid_remove()
            self.translation_grouping_frame.grid()

    def _translation_configuration(self):
        """Collect explicit, session-only cloud choices without constructing a provider."""
        if not self.translation_enabled.get():
            return None
        languages = tuple(code for code, variable in self.translation_languages.items() if variable.get())
        if not languages:
            self._set_status("Select at least one target language for translation.")
            return False
        provider_name = self.translation_provider.get()
        if provider_name not in {"openai", "local"}:
            self._set_status("Select an available translation provider.")
            return False
        if any(language not in self._available_translation_targets() for language in languages):
            self._set_status("Selected target language is unavailable for this translation provider.")
            return False
        formats = tuple(name for name, variable in self.translation_formats.items() if variable.get())
        if not formats:
            self._set_status("Select at least one translation output format.")
            return False
        if provider_name == "local":
            grouping = (
                TranslationOutputGrouping.BY_SOURCE
                if self.run_mode.get() == "single"
                else TranslationOutputGrouping(self.translation_grouping.get())
            )
            return ("local", languages, grouping, formats, None, None)
        try:
            model = resolve_vetted_openai_model(self.translation_model.get())
        except ValueError as error:
            self._set_status(str(error))
            return False
        acknowledged = messagebox.askokcancel(
            "Cloud Translation Disclosure",
            "Selected OCR-derived text will be transmitted to OpenAI.\n\n"
            "Video and image data are not sent by this translation provider. Internet access and an API key are required; usage may incur charges. Translation remains subject to human review.\n\nContinue?",
            parent=self.master,
        )
        if not acknowledged:
            self._set_status("Translation was cancelled before any text was sent.")
            return False
        api_key = simpledialog.askstring("OpenAI API Key", "Enter an API key for this session only:", parent=self.master, show="*")
        if not api_key or not api_key.strip():
            self._set_status("Translation requires an OpenAI API key.")
            return False
        grouping = (
            TranslationOutputGrouping.BY_SOURCE
            if self.run_mode.get() == "single"
            else TranslationOutputGrouping(self.translation_grouping.get())
        )
        return ("openai", languages, grouping, formats, api_key.strip(), model)

    def _remember_recent_source(self, source: str) -> None:
        preferences = getattr(self, "preferences", None)
        if preferences is None:
            return
        add_recent_source(preferences, source)
        save_preferences(preferences)
        self._refresh_recent_sources_menu()

    def _refresh_recent_sources_menu(self) -> None:
        menu = self.recent_sources_menu
        menu.delete(0, "end")
        if not self.preferences.recent_sources:
            menu.add_command(label="No recent sources", state="disabled")
            return
        for source in self.preferences.recent_sources:
            label = source if len(source) <= 60 else source[:57] + "..."
            menu.add_command(
                label=label,
                command=lambda selected=source: self._select_recent_source(selected),
            )

    def _clear_recent_sources(self) -> None:
        clear_recent_sources(self.preferences)
        save_preferences(self.preferences)
        self._refresh_recent_sources_menu()
        self._append_log("Recent sources cleared.")

    def _select_recent_source(self, source: str) -> None:
        """Restore a remembered URL, file, or batch folder without temp paths."""

        if "://" in source:
            self.run_mode.set("single")
            self._set_run_mode()
            self.video_source_type.set("url")
            self._set_video_source_type()
            self.video_path.set(source)
            return

        path = Path(source)
        if path.is_dir():
            try:
                self.run_mode.set("batch")
                self._set_run_mode()
                self._add_batch_paths(videos_in_folder(path))
            except ValueError as error:
                self._set_status(str(error))
            return
        if not path.is_file():
            self._set_status(f"Recent local source is no longer available: {path}")
            return
        self.run_mode.set("single")
        self._set_run_mode()
        self.video_source_type.set("local")
        self._set_video_source_type()
        self.video_path.set(str(path))

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
            self._restore_main_focus()

        close_button = ttk.Button(button_frame, text="Close", command=close_dialog)
        close_button.grid(row=0, column=0)
        dialog.protocol("WM_DELETE_WINDOW", close_dialog)
        dialog.bind("<Escape>", lambda _event: close_dialog())
        dialog.bind("<Return>", lambda _event: close_dialog())
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
            self.source_choice_frame.grid_remove()
            self.video_label.grid_remove()
            self.video_entry.grid_remove()
            self.video_browse_button.grid_remove()
            self.advanced_source_path.set(self.video_path.get())
            self.advanced_frame.grid(
                row=4,
                column=0,
                columnspan=3,
                sticky="ew",
                pady=(0, 8),
            )
        else:
            self.advanced_frame.grid_remove()
            self.source_choice_frame.grid()
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
        output_folder = Path(self.output_folder.get())

        if mode is ProcessingMode.FULL_VIDEO:
            try:
                VideoSource.from_value(source_path)
            except VideoSourceError as error:
                self._set_status(str(error))
                return

        checkpoint_path = Path(source_path) if source_path else None
        if mode is not ProcessingMode.FULL_VIDEO and (
            checkpoint_path is None or not checkpoint_path.exists()
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
        translation_configuration = (
            self._translation_configuration()
            if hasattr(self, "translation_enabled") else None
        )
        if translation_configuration is False:
            return

        self.processing = True
        self.process_button.configure(state="disabled")
        self._reset_progress()
        self._append_log(f"Processing mode: {mode.value}")
        self._append_log(f"Source selected: {source_path}")
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
                    source_path=source_path,
                    output_directory=output_folder,
                    formats=selected_formats,
                    progress_callback=self._queue_progress,
                ),
            ) if translation_configuration is None else (
                ProcessingRequest(
                    mode=mode, source_path=source_path, output_directory=output_folder,
                    formats=selected_formats, progress_callback=self._queue_progress,
                ), translation_configuration),
            daemon=True,
        )
        worker.start()
        self.after(100, self._poll_worker_messages)

    def _show_accessibility(self) -> None:
        """Open keyboard guidance and current accessibility limitations."""
        self._show_help_dialog("Accessibility", get_accessibility_text())

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
        translation_configuration = (
            self._translation_configuration()
            if hasattr(self, "translation_enabled") else None
        )
        if translation_configuration is False:
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
                consolidated_excel=self.batch_excel_consolidated.get(),
                progress_callback=self._queue_batch_progress,
            ), translation_configuration),
            daemon=True,
        )
        worker.start()
        self.after(100, self._poll_worker_messages)

    def _run_processing_worker(self, request: ProcessingRequest, translation_configuration=None) -> None:
        """Run the pipeline without interacting with Tkinter widgets."""

        try:
            write_gui_diagnostic("processing started", f"mode={request.mode.value}")
            result = process_request(request)
            write_gui_diagnostic("ocr processing completed", f"run_directory={result.run_directory}")
            translation_result = self._translate_completed_results(
                (result,), translation_configuration, result.run_directory / "translations",
            )
            write_gui_diagnostic("processing completed", f"run_directory={result.run_directory}")
            self.message_queue.put(("complete", (result, translation_result)))

        except PermissionError as error:
            diagnostic_path = write_gui_diagnostic("processing permission error", traceback.format_exc())
            if diagnostic_path is not None:
                self.message_queue.put(("error", f"{error}\nDiagnostic log: {diagnostic_path}"))
                return
            self.message_queue.put(("error", str(error)))

        except Exception as error:
            diagnostic_path = write_gui_diagnostic("processing exception", traceback.format_exc())
            detail = f"{type(error).__name__}: {error}"
            if diagnostic_path is not None:
                detail += f"\nDiagnostic log: {diagnostic_path}"
            self.message_queue.put(
                ("error", detail)
            )

    def _translate_completed_results(self, processing_results, configuration, output_directory: Path):
        """Invoke optional translation only after OCR processing and consent."""
        if configuration is None:
            return None
        provider_name, languages, grouping, formats, api_key, model = configuration
        if provider_name == "local":
            # Constructing the provider does not load its model.  The first
            # model load happens inside translation, after OCR has returned.
            write_gui_diagnostic("local translation provider construction")
            provider = LocalCTranslate2Provider(
                LocalTranslationConfig(self.local_translation_model_root),
            )
        else:
            provider = OpenAITranslationProvider(OpenAITranslationConfig(
                model=model, api_key=api_key,
            ))
            # A missing frozen SDK or invalid client construction is an
            # application-level failure, not one failed API call per paragraph.
            provider.ensure_ready()
        sources = tuple(TranslationApplicationSource(
            TranslationSourceItem(
                f"source-{index}", _translation_source_identity(result) or f"Video {index + 1}",
                f"processing:{index}", index,
            ), result.presentation,
        ) for index, result in enumerate(processing_results))
        job_id = f"translation-{Path(processing_results[0].run_directory).name}"
        self.message_queue.put(("translation_progress", (0, sum(
            sum(len(slide.paragraphs) for slide in result.presentation.slides) for result in processing_results
        ) * len(languages))))
        write_gui_diagnostic("translation started", f"provider={provider_name}; targets={','.join(languages)}")
        return run_translation_job(job_id, sources, "en", languages, provider, grouping,
            formats, output_directory,
            progress_callback=lambda current, total: self.message_queue.put(("translation_progress", (current, total))),
        )

    def _run_batch_worker(self, request: BatchProcessingRequest, translation_configuration=None) -> None:
        """Run the shared batch service without interacting with Tkinter."""

        try:
            write_gui_diagnostic("batch processing started", f"items={len(request.source_paths)}")
            result = process_batch(request)
            processing_results = tuple(item.processing_result for item in result.successful_items if item.processing_result is not None)
            translation_result = self._translate_completed_results(
                processing_results, translation_configuration, request.output_directory / "translations",
            ) if processing_results else None
            self.message_queue.put(("batch_complete", (result, translation_result)))
        except Exception as error:
            diagnostic_path = write_gui_diagnostic("batch processing exception", traceback.format_exc())
            detail = f"{type(error).__name__}: {error}"
            if diagnostic_path is not None:
                detail += f"\nDiagnostic log: {diagnostic_path}"
            self.message_queue.put(
                ("error", detail)
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
                    if isinstance(payload, tuple):
                        payload, translation_result = payload
                    else:
                        translation_result = None
                    self._remember_recent_source(payload.source_path)
                    self._append_log(f"Output folder: {payload.run_directory}")
                    for format_name, path in payload.exported_paths.items():
                        self._append_log(
                            f"Saved {format_name.title()}: {path}"
                        )
                    if translation_result is not None:
                        self._append_log(f"Translation provider: {translation_result.job.provider_name}")
                        self._append_log(f"Translations: {translation_result.export_result.success_count} succeeded, {translation_result.export_result.failure_count} failed, {translation_result.review_recommended_count} marked Review Recommended")
                        for format_name, paths in translation_result.export_result.paths.items():
                            for path in paths: self._append_log(f"Saved translation {format_name.title()}: {path}")
                    self._finish_processing()
                    if translation_result is None:
                        self._show_completion_dialog(payload)
                    else:
                        self._show_completion_dialog(payload, translation_result)

                elif message_type == "batch_complete":
                    if isinstance(payload, tuple):
                        payload, translation_result = payload
                    else:
                        translation_result = None
                    for item in payload.successful_items:
                        self._remember_recent_source(item.source_path)
                    for item in payload.failed_items:
                        self._append_log(
                            f"FAILED: {Path(item.source_path).name}\n"
                            f"Reason: {item.error_message}"
                        )
                    self._finish_processing()
                    self._set_batch_controls_state("normal")
                    if translation_result is not None:
                        self._append_log(f"Translations: {translation_result.export_result.success_count} succeeded, {translation_result.export_result.failure_count} failed, {translation_result.review_recommended_count} marked Review Recommended")
                        for format_name, paths in translation_result.export_result.paths.items():
                            for path in paths: self._append_log(f"Saved translation {format_name.title()}: {path}")
                    self._show_batch_completion_dialog(payload, translation_result)

                elif message_type == "translation_progress":
                    current, total = payload
                    self.status.set(f"Translating {current} of {total}")
                    if total:
                        self.progress_bar.configure(mode="determinate")
                        self.progress_value.set(int((current / total) * 100))

                elif message_type == "error":
                    self._set_status(f"Processing failed: {payload}")
                    self._finish_processing()
                    self._set_batch_controls_state("normal")
                    if hasattr(self, "master"):
                        self._show_processing_error(payload)

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
            elif progress.stage == "download":
                percentage = (
                    f" ({progress.percentage:.0f}%)"
                    if progress.percentage is not None
                    else ""
                )
                message += (
                    f"\n{format_bytes(progress.current)} of "
                    f"{format_bytes(progress.total)}{percentage}"
                )
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
        elif progress.stage in {"frame_selection", "download"} and progress.current is not None:
            if progress.stage == "download":
                message += f"\n{format_bytes(progress.current)} downloaded"
            else:
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
        self._restore_main_focus()

    def _restore_main_focus(self) -> None:
        """Return keyboard users to the primary action after a dialog closes."""

        self.process_button.focus_set()

    def _open_output_folder(self, folder: Path) -> None:
        """Open a user-requested successful output folder without affecting success."""

        warning = open_folder(folder)
        if warning:
            self._append_log(f"Warning: {warning}")

    def _open_completed_folder(self, folder: Path) -> None:
        """Retain the saved preference behavior for callers that opt into it."""

        if getattr(self, "preferences", Preferences()).open_output_folder_after_completion:
            self._open_output_folder(folder)

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

    def _show_processing_error(self, detail: str) -> None:
        """Present a concise recoverable worker failure on the GUI thread."""

        messagebox.showerror("VideoText Processing Failed", detail, parent=self.master)

    def _show_completion_dialog(self, result, translation_result=None) -> None:
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
        summary = _compose_completion_dialog_text(result, translation_result)
        summary_text.insert("1.0", summary)
        summary_text.configure(state="disabled")

        button_frame = ttk.Frame(dialog)
        button_frame.grid(row=2, column=0, sticky="e", padx=12, pady=12)

        def close_dialog() -> None:
            dialog.grab_release()
            dialog.destroy()
            self._restore_main_focus()

        ttk.Button(
            button_frame,
            text="Open Output Folder",
            command=lambda: self._open_output_folder(result.run_directory),
        ).grid(row=0, column=0, padx=(0, 8))
        close_button = ttk.Button(
            button_frame,
            text="Close",
            command=close_dialog,
        )
        close_button.grid(row=0, column=1)
        dialog.protocol("WM_DELETE_WINDOW", close_dialog)
        dialog.bind("<Escape>", lambda _event: close_dialog())
        dialog.bind("<Return>", lambda _event: close_dialog())
        dialog.grab_set()
        close_button.focus_set()

    def _show_batch_completion_dialog(self, result, translation_result=None) -> None:
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
        summary = format_batch_summary(result)
        if translation_result is not None:
            summary += _format_translation_completion_section(translation_result)
        summary_text.insert("1.0", summary)
        summary_text.configure(state="disabled")

        def close_dialog() -> None:
            dialog.destroy()
            self._restore_main_focus()

        button_frame = ttk.Frame(dialog)
        button_frame.grid(row=2, column=0, columnspan=2, sticky="e", padx=12, pady=(6, 12))
        ttk.Button(
            button_frame,
            text="Open Output Folder",
            command=lambda: self._open_output_folder(result.output_directory),
        ).grid(row=0, column=0, padx=(0, 8))
        close_button = ttk.Button(button_frame, text="Close", command=close_dialog)
        close_button.grid(row=0, column=1)
        dialog.protocol("WM_DELETE_WINDOW", close_dialog)
        dialog.bind("<Escape>", lambda _event: close_dialog())
        dialog.bind("<Return>", lambda _event: close_dialog())
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
            "Video URLs",
            "Processing Stages",
            "Export Formats",
            "OCR Quality",
            "Batch Processing",
            "Recent Sources",
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


def _format_translation_completion_section(translation_result) -> str:
    """Format optional completed translation evidence without exposing secrets."""

    exported = translation_result.export_result
    target_labels = [
        translation_locale_display_name(locale)
        for locale in translation_result.job.target_languages
    ]
    provider_label = {
        "local-ctranslate2": "Local Translation",
        "openai": "OpenAI Cloud",
    }.get(translation_result.job.provider_name, translation_result.job.provider_name)
    lines = ["", "Translation", "--------------------",
             f"Provider: {provider_label}", "Target languages:"]
    lines.extend(f"    {target_label}" for target_label in target_labels)
    lines.extend((
        f"Succeeded: {exported.success_count}",
        f"Failed: {exported.failure_count}",
        f"Review Recommended: {translation_result.review_recommended_count}",
        "",
        "Translation Outputs",
        "--------------------",
    ))
    for format_name, paths in exported.paths.items():
        for path in paths:
            label = "Translation Review Workbook" if format_name == "excel" else f"Translation {format_name.upper()}"
            lines.extend((label, f"    {path}"))
    return "\n".join(lines) + "\n"


def _compose_completion_dialog_text(result, translation_result=None) -> str:
    """Compose the exact single-run text inserted into the live Tk dialog."""

    sections = [
        _format_completion_dialog_text(format_processing_summary(result)).strip(),
    ]
    ocr_quality = _format_ocr_quality_section(
        result.ocr_confidence_statistics,
    ).strip()
    if ocr_quality:
        sections.append(ocr_quality)
    if translation_result is not None:
        sections.append(
            _format_translation_completion_section(translation_result).strip(),
        )
    return "\n\n".join(sections) + "\n"


def _translation_source_identity(result) -> str:
    """Resolve a stable video name for downstream translation artifacts.

    Replay requests name a checkpoint as their source path.  Prefer a top-level
    canonical OCR export from its originating run, which retains the video stem
    without turning ``candidate_frames.pkl`` into a workbook name.
    """

    checkpoint = getattr(result, "resolved_checkpoint_path", None)
    if checkpoint is not None:
        source_run = checkpoint.parent.parent if checkpoint.parent.name.lower() == "cache" else checkpoint.parent
        # Replay directories are deliberately named ``<source>_replay`` with
        # an optional numeric collision suffix.  When a replay is replayed,
        # follow those existing sibling directories back to the original OCR
        # run before choosing its canonical export stem.
        while source_run.is_dir():
            marker = source_run.name.rfind("_replay")
            suffix = source_run.name[marker + len("_replay"):] if marker >= 0 else None
            if marker < 0 or suffix is None or (suffix and not (suffix.startswith("_") and suffix[1:].isdigit())):
                break
            parent_run = source_run.parent / source_run.name[:marker]
            if not parent_run.is_dir():
                break
            source_run = parent_run
        candidates = sorted(
            (path for path in source_run.iterdir()
             if path.is_file() and path.suffix.lower() in {".md", ".csv", ".xlsx"}),
            key=lambda path: (path.stem.casefold(), path.suffix.casefold()),
        ) if source_run.is_dir() else []
        if candidates:
            return candidates[0].stem
        name = source_run.name
        if name:
            return name
    return Path(result.source_path).stem


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
    if "Video" in fields:
        lines.append(f"Video: {fields['Video']}")
    if "Source type" in fields:
        lines.append(f"Source type: {fields['Source type']}")
    if "Source" in fields:
        lines.extend(("Source:", fields["Source"]))
    if "Resolved checkpoint" in fields:
        lines.extend(("", "Resolved checkpoint:", fields["Resolved checkpoint"]))

    lines.extend(["", "Output", "--------------------"])
    if "Output folder" in fields:
        lines.append(fields["Output folder"])

    lines.extend(["", "OCR Exports", "--------------------"])
    for label, path in exports:
        lines.extend((label, f"    {path}", ""))

    return "\n".join(lines).rstrip()


def _format_ocr_quality_section(statistics) -> str:
    """Format the immutable shared OCR summary for the completion dialog."""

    if statistics is None:
        return ""

    lines = ["", "", "OCR Quality", "--------------------"]
    lines.append(f"OCR regions: {statistics.region_count:,}")
    if statistics.region_count == 0:
        lines.append("Confidence statistics unavailable")
        lines.append(f"Active threshold: {statistics.threshold:.1%}")
        return "\n".join(lines)

    lines.extend((
        f"Mean confidence: {statistics.mean:.1%}",
        f"Median confidence: {statistics.median:.1%}",
        f"Minimum confidence: {statistics.minimum:.1%}",
        "Below "
        f"{statistics.threshold:.0%}: {statistics.below_threshold_count} regions "
        f"({statistics.below_threshold_proportion:.1%})",
        f"Active threshold: {statistics.threshold:.1%}",
    ))
    return "\n".join(lines)


def main() -> None:
    """Launch the VideoText GUI shell."""

    root = tk.Tk()
    VideoTextApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
