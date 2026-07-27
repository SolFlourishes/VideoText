"""
gui.py

Initial desktop GUI shell for VideoText.
"""

import os
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, ttk


class VideoTextApp(ttk.Frame):
    """Top-level layout and placeholder interactions for VideoText."""

    def __init__(self, master: tk.Tk):
        super().__init__(master, padding=12)
        self.master = master
        self.video_path = tk.StringVar()
        self.output_folder = tk.StringVar()
        self.status = tk.StringVar(value="Select a video and output folder.")
        self.progress_value = tk.IntVar(value=0)
        self.processing = False
        self.format_options = {
            "markdown": tk.BooleanVar(value=True),
            "csv": tk.BooleanVar(value=True),
            "excel": tk.BooleanVar(value=True),
        }

        self._build_layout()

    def _build_layout(self) -> None:
        self.master.title("VideoText")
        self.master.minsize(650, 500)

        self.grid(sticky="nsew")
        self.master.columnconfigure(0, weight=1)
        self.master.rowconfigure(0, weight=1)
        self.columnconfigure(1, weight=1)
        self.rowconfigure(5, weight=1)

        ttk.Label(self, text="Video File").grid(
            row=0,
            column=0,
            sticky="w",
            padx=(0, 8),
            pady=(0, 8),
        )
        ttk.Entry(self, textvariable=self.video_path).grid(
            row=0,
            column=1,
            sticky="ew",
            pady=(0, 8),
        )
        ttk.Button(self, text="Browse", command=self._browse_video).grid(
            row=0,
            column=2,
            padx=(8, 0),
            pady=(0, 8),
        )

        ttk.Label(self, text="Output Folder").grid(
            row=1,
            column=0,
            sticky="w",
            padx=(0, 8),
            pady=(0, 8),
        )
        ttk.Entry(self, textvariable=self.output_folder).grid(
            row=1,
            column=1,
            sticky="ew",
            pady=(0, 8),
        )
        ttk.Button(self, text="Browse", command=self._browse_output_folder).grid(
            row=1,
            column=2,
            padx=(8, 0),
            pady=(0, 8),
        )

        formats_frame = ttk.LabelFrame(self, text="Export Formats", padding=8)
        formats_frame.grid(
            row=2,
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
            row=3,
            column=0,
            columnspan=3,
            pady=(0, 8),
        )

        progress_frame = ttk.LabelFrame(self, text="Progress", padding=8)
        progress_frame.grid(
            row=4,
            column=0,
            columnspan=3,
            sticky="ew",
            pady=(0, 8),
        )
        progress_frame.columnconfigure(0, weight=1)

        ttk.Progressbar(
            progress_frame,
            maximum=100,
            variable=self.progress_value,
        ).grid(row=0, column=0, sticky="ew")
        ttk.Label(progress_frame, textvariable=self.status).grid(
            row=1,
            column=0,
            sticky="w",
            pady=(6, 0),
        )

        log_frame = ttk.LabelFrame(self, text="Log", padding=8)
        log_frame.grid(
            row=5,
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
        )
        if path:
            self.video_path.set(path)

    def _browse_output_folder(self) -> None:
        path = filedialog.askdirectory(title="Select Output Folder")
        if path:
            self.output_folder.set(path)

    def _start_processing(self) -> None:
        if self.processing:
            return

        video = Path(self.video_path.get())
        output_folder = Path(self.output_folder.get())

        if not self.video_path.get() or not video.is_file():
            self._set_status("Select a valid video file.")
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
        self.progress_value.set(0)
        self._append_log(f"Video selected: {video}")
        self._append_log(f"Output folder selected: {output_folder}")
        self._append_log(
            "Selected formats: "
            + (", ".join(selected_formats) if selected_formats else "none")
        )
        self._run_placeholder_step(0)

    def _run_placeholder_step(self, step: int) -> None:
        try:
            updates = [
                (10, "Preparing video"),
                (25, "Selecting stable frames"),
                (45, "Running OCR"),
                (65, "Reconstructing paragraphs"),
                (80, "Consolidating slides"),
                (95, "Exporting files"),
                (100, "Complete"),
            ]

            progress, message = updates[step]
            self.progress_value.set(progress)
            self.status.set(message)
            self._append_log(message)

            if step + 1 < len(updates):
                self.after(400, self._run_placeholder_step, step + 1)
            else:
                self._finish_placeholder_processing()

        except Exception as error:
            try:
                self._set_status(f"Placeholder processing error: {error}")
            finally:
                self._finish_placeholder_processing()

    def _finish_placeholder_processing(self) -> None:
        self.processing = False
        self.process_button.configure(state="normal")

    def _set_status(self, message: str) -> None:
        self.status.set(message)
        self._append_log(message)

    def _append_log(self, message: str) -> None:
        self.log_text.configure(state="normal")
        self.log_text.insert("end", message + "\n")
        self.log_text.see("end")
        self.log_text.configure(state="disabled")


def main() -> None:
    """Launch the VideoText GUI shell."""

    root = tk.Tk()
    VideoTextApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
