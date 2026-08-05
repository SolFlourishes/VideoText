"""Review pending v2 OCR reference text against saved benchmark frame images."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys
import tkinter as tk
from tkinter import messagebox, simpledialog

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from ground_truth_review import GroundTruthReview


class ReviewApp(tk.Tk):
    def __init__(self, review: GroundTruthReview, reviewer: str) -> None:
        super().__init__()
        self.review, self.reviewer, self.image = review, reviewer, None
        self.title("VideoText Ground Truth Review")
        self.protocol("WM_DELETE_WINDOW", self.exit)
        self.status = tk.StringVar()
        self.meta = tk.StringVar()
        tk.Label(self, textvariable=self.meta, anchor="w").pack(fill="x", padx=8, pady=4)
        self.preview = tk.Label(self, text="Image preview")
        self.preview.pack(fill="both", expand=True, padx=8)
        self.text = tk.Text(self, height=10, wrap="word")
        self.text.pack(fill="both", expand=True, padx=8, pady=4)
        self.notes = tk.Text(self, height=4, wrap="word")
        self.notes.pack(fill="x", padx=8, pady=4)
        buttons = tk.Frame(self); buttons.pack(pady=4)
        for label, command in (("Previous", lambda: self.navigate(-1)), ("Next", lambda: self.navigate(1)), ("Verify", self.verify), ("Needs Review", self.needs_review), ("Skip", lambda: self.navigate(1)), ("Save", self.save), ("Exit", self.exit)):
            tk.Button(buttons, text=label, command=command).pack(side="left", padx=3)
        tk.Label(self, textvariable=self.status, anchor="w").pack(fill="x", padx=8, pady=4)
        self.bind("<Control-s>", lambda _: self.save()); self.bind("<Alt-v>", lambda _: self.verify()); self.bind("<Alt-n>", lambda _: self.needs_review()); self.bind("<Alt-s>", lambda _: self.navigate(1)); self.bind("<Left>", lambda _: self.navigate(-1)); self.bind("<Right>", lambda _: self.navigate(1))
        self.load()

    def commit(self): self.review.update_text_and_notes(self.text.get("1.0", "end-1c"), self.notes.get("1.0", "end-1c"))
    def load(self):
        record, frame, progress = self.review.record, self.review.frame, self.review.progress()
        self.meta.set(f"Frame {progress['current']} of {progress['total']} — {frame['frame_id']} — source frame {frame['frame_number']} — {record['verification_status']} — reviewer: {record['reviewer'] or 'unassigned'} — date: {record['verification_date'] or 'unverified'}")
        self.status.set(f"Verified: {progress['verified']}  Needs Review: {progress['needs_review']}  Pending: {progress['pending']}")
        self.text.delete("1.0", "end"); self.text.insert("1.0", record["reference_text"]); self.notes.delete("1.0", "end"); self.notes.insert("1.0", record["notes"] or "")
        image = tk.PhotoImage(file=str(self.review.manifest_path.parent / frame["image"]))
        factor = max(1, (image.width() + 899) // 900, (image.height() + 499) // 500)
        self.image = image.subsample(factor, factor); self.preview.configure(image=self.image, text="")
    def navigate(self, offset): self.commit(); self.review.move(offset) and self.load()
    def verify(self):
        self.commit()
        try: self.review.verify(self.reviewer)
        except ValueError as error: messagebox.showerror("Verification", str(error), parent=self); return
        self.load()
    def needs_review(self): self.commit(); self.review.needs_review(); self.load()
    def save(self): self.commit(); backup = self.review.save(); self.status.set(f"Saved. Backup: {backup}" if backup else "No changes to save.")
    def exit(self):
        if self.review.dirty:
            decision = messagebox.askyesnocancel("Unsaved changes", "Save changes before exiting?", parent=self)
            if decision is None:
                return
            if decision:
                self.save()
        self.destroy()


def main(argv=None):
    parser = argparse.ArgumentParser(); parser.add_argument("--manifest", type=Path, default=Path("benchmarks/ocr_engine_v2/manifest.json")); parser.add_argument("--ground-truth", type=Path, default=Path("benchmarks/ocr_engine_v2/ground_truth.json")); args = parser.parse_args(argv)
    review = GroundTruthReview(args.manifest, args.ground_truth)
    root = tk.Tk(); root.withdraw(); reviewer = simpledialog.askstring("Reviewer", "Reviewer name:", parent=root) or ""; root.destroy()
    ReviewApp(review, reviewer).mainloop()

if __name__ == "__main__": main()
