# axioms_validator_gui.py
# GUI program that validates Kolmogorov's axioms of probability
# for a finite sample space. Uses tkinter (comes with Python).

import json
import math
import tkinter as tk
from datetime import datetime
from pathlib import Path
from tkinter import ttk, messagebox, simpledialog
from uuid import uuid4

TOL = 1e-9  # tolerance for floating-point comparisons


# ---------------------------------------------------------------
# BLOCK 1: Parsing helpers (turn the user's text into Python data)
# ---------------------------------------------------------------
def parse_pmf(text):
    """Convert 'a:0.2, b:0.3, c:0.5' into {'a': 0.2, 'b': 0.3, 'c': 0.5}."""
    pmf = {}
    for part in text.split(","):
        part = part.strip()
        if not part:
            continue
        if ":" not in part:
            raise ValueError(f"'{part}' must look like outcome:probability")
        name, value = part.split(":", 1)
        name = name.strip()
        if not name:
            raise ValueError("An outcome name is empty.")
        if name in pmf:
            raise ValueError(f"Outcome '{name}' is listed twice.")
        try:
            pmf[name] = float(value)
        except ValueError:
            raise ValueError(f"'{value.strip()}' is not a number.")
    if not pmf:
        raise ValueError("Please enter at least one outcome.")
    return pmf


def parse_events(text, pmf):
    """Convert 'a,b ; c' into [{'a','b'}, {'c'}] (one set per event)."""
    events = []
    for chunk in text.split(";"):
        names = {n.strip() for n in chunk.split(",") if n.strip()}
        if not names:
            continue
        unknown = names - set(pmf)
        if unknown:
            raise ValueError(f"Not in the sample space: {', '.join(sorted(unknown))}")
        events.append(names)
    return events


# ---------------------------------------------------------------
# BLOCK 2: The axiom checks (the "brain" of the program)
# ---------------------------------------------------------------
def prob(pmf, event):
    """P(event) = sum of the probabilities of the outcomes in it."""
    return sum(pmf[w] for w in event)


def check_axiom1(pmf):
    """Axiom 1: every probability must be >= 0."""
    negatives = {k: v for k, v in pmf.items() if v < -1e-12}
    return len(negatives) == 0, negatives


def check_axiom2(pmf):
    """Axiom 2: P(S) = 1, so all probabilities must add up to 1."""
    total = sum(pmf.values())
    return math.isclose(total, 1.0, abs_tol=TOL), total


def are_disjoint(events):
    """True if no two events share an outcome."""
    for i in range(len(events)):
        for j in range(i + 1, len(events)):
            if events[i] & events[j]:
                return False
    return True


def check_axiom3(pmf, events):
    """Axiom 3: for disjoint events, P(union) = sum of P(each)."""
    union = set().union(*events)
    p_union = prob(pmf, union)
    p_sum = sum(prob(pmf, e) for e in events)
    return math.isclose(p_union, p_sum, abs_tol=TOL), p_union, p_sum


# ---------------------------------------------------------------
# BLOCK 3: The GUI class
# ---------------------------------------------------------------
class AxiomsApp:
    def __init__(self, root):
        self.root = root
        self.history_path = Path(__file__).with_name("history.json")
        self.history = []
        self.sidebar_visible = True
        root.title("Kolmogorov Axioms Validator")
        root.geometry("960x600")
        root.minsize(680, 480)

        main = ttk.Frame(root, padding=12)
        main.pack(side="left", fill="both", expand=True)
        self.sidebar = ttk.Frame(root, padding=(8, 12, 12, 12), width=270)
        self.sidebar.pack(side="right", fill="y")
        self.sidebar.pack_propagate(False)

        # --- Optional session title ---
        main_header = ttk.Frame(main)
        main_header.pack(fill="x", pady=(0, 8))
        self.sidebar_toggle_button = ttk.Button(
            main_header, text="Hide history", command=self._toggle_sidebar
        )
        self.sidebar_toggle_button.pack(side="right")
        ttk.Label(main, text="Session title (optional)",
                  font=("Segoe UI", 10, "bold")).pack(anchor="w")
        self.title_entry = ttk.Entry(main, font=("Segoe UI", 10))
        self.title_entry.pack(fill="x", pady=(2, 10))

        # --- Input area ---
        ttk.Label(main, text="Probability assignment (outcome:probability, separated by commas)",
                  font=("Segoe UI", 10, "bold")).pack(anchor="w")
        self.pmf_entry = ttk.Entry(main, font=("Consolas", 11))
        self.pmf_entry.pack(fill="x", pady=(2, 10))

        ttk.Label(main, text="Disjoint events to test additivity (outcomes by commas, events by semicolons)",
                  font=("Segoe UI", 10, "bold")).pack(anchor="w")
        self.events_entry = ttk.Entry(main, font=("Consolas", 11))
        self.events_entry.pack(fill="x", pady=(2, 4))
        ttk.Label(main, text="Example:  a ; b   means events {a} and {b}",
                  foreground="gray").pack(anchor="w", pady=(0, 10))

        # --- Buttons ---
        buttons = ttk.Frame(main)
        buttons.pack(fill="x", pady=(0, 10))
        ttk.Button(buttons, text="Validate", command=self.validate).pack(side="left")
        ttk.Button(buttons, text="Valid example", command=self.load_valid).pack(side="left", padx=6)
        ttk.Button(buttons, text="Invalid example", command=self.load_invalid).pack(side="left")
        ttk.Button(buttons, text="Clear", command=self.clear).pack(side="right")

        # --- Results area ---
        self.output = tk.Text(main, height=14, font=("Consolas", 11),
                              state="disabled", wrap="word")
        self.output.pack(fill="both", expand=True)
        self.output.tag_config("pass", foreground="#1a7f37")
        self.output.tag_config("fail", foreground="#cf222e")
        self.output.tag_config("head", font=("Consolas", 11, "bold"))

        # --- Scrollable history sidebar ---
        ttk.Label(self.sidebar, text="History",
                  font=("Segoe UI", 11, "bold")).pack(anchor="w", pady=(0, 8))
        history_list_frame = ttk.Frame(self.sidebar)
        history_list_frame.pack(fill="both", expand=True)
        self.history_canvas = tk.Canvas(
            history_list_frame, highlightthickness=0, borderwidth=0
        )
        history_scrollbar = ttk.Scrollbar(
            history_list_frame,
            orient="vertical",
            command=self.history_canvas.yview,
        )
        self.history_canvas.configure(yscrollcommand=history_scrollbar.set)
        self.history_canvas.pack(side="left", fill="both", expand=True)
        history_scrollbar.pack(side="right", fill="y")
        self.history_inner = ttk.Frame(self.history_canvas)
        self.history_window = self.history_canvas.create_window(
            (0, 0), window=self.history_inner, anchor="nw"
        )
        self.history_inner.bind("<Configure>", self._update_history_scrollregion)
        self.history_canvas.bind("<Configure>", self._resize_history_content)

        self._load_history()
        self.load_valid()
        self._refresh_history_list()

    # -----------------------------------------------------------
    # BLOCK 4: Existing button and output helpers
    # -----------------------------------------------------------
    def load_valid(self):
        self._fill("a:0.2, b:0.3, c:0.5", "a ; b")

    def load_invalid(self):
        self._fill("a:0.5, b:-0.1, c:0.6", "a ; b")

    def _fill(self, pmf_text, events_text):
        self.pmf_entry.delete(0, tk.END)
        self.pmf_entry.insert(0, pmf_text)
        self.events_entry.delete(0, tk.END)
        self.events_entry.insert(0, events_text)
        self._write([])

    def clear(self):
        self._fill("", "")
        self.title_entry.delete(0, tk.END)

    def _write(self, lines):
        """lines is a list of (text, tag) pairs."""
        self.output.config(state="normal")
        self.output.delete("1.0", tk.END)
        for text, tag in lines:
            self.output.insert(tk.END, text + "\n", tag)
        self.output.config(state="disabled")

    # -----------------------------------------------------------
    # BLOCK 5: Loading and saving session history
    # -----------------------------------------------------------
    def _load_history(self):
        try:
            with self.history_path.open("r", encoding="utf-8") as history_file:
                entries = json.load(history_file)
            self._validate_history(entries)
            self.history = entries
        except FileNotFoundError:
            return
        except (OSError, ValueError) as err:
            messagebox.showerror(
                "History error",
                f"Could not load session history from:\n{self.history_path}\n\n"
                f"The history will start empty. Details: {err}",
            )

    @staticmethod
    def _validate_history(entries):
        if not isinstance(entries, list):
            raise ValueError("The history file must contain a list of sessions.")

        seen_ids = set()
        for entry in entries:
            if not isinstance(entry, dict):
                raise ValueError("The history file contains an invalid session.")
            if (
                not isinstance(entry.get("id"), str)
                or not entry["id"]
                or entry["id"] in seen_ids
                or not isinstance(entry.get("title"), str)
                or not isinstance(entry.get("created_at"), str)
                or not isinstance(entry.get("pmf"), str)
                or not isinstance(entry.get("events"), str)
                or not isinstance(entry.get("lines"), list)
                or entry.get("verdict") not in ("valid", "invalid")
                or not isinstance(entry.get("pinned"), bool)
                or not isinstance(entry.get("session_number"), int)
                or isinstance(entry.get("session_number"), bool)
                or entry["session_number"] < 1
                or any(
                    not isinstance(line, list)
                    or len(line) != 2
                    or not all(isinstance(part, str) for part in line)
                    for line in entry["lines"]
                )
            ):
                raise ValueError("The history file contains an invalid session.")
            datetime.fromisoformat(entry["created_at"])
            seen_ids.add(entry["id"])

    def _save_history(self):
        try:
            with self.history_path.open("w", encoding="utf-8") as history_file:
                json.dump(self.history, history_file, ensure_ascii=False, indent=2)
        except OSError as err:
            messagebox.showerror(
                "History error",
                f"Could not save session history to:\n{self.history_path}\n\n{err}",
            )

    # -----------------------------------------------------------
    # BLOCK 6: Drawing and collapsing the history sidebar
    # -----------------------------------------------------------
    def _toggle_sidebar(self):
        if self.sidebar_visible:
            self.sidebar.pack_forget()
            button_text = "Show history"
        else:
            self.sidebar.pack(side="right", fill="y")
            button_text = "Hide history"
        self.sidebar_visible = not self.sidebar_visible
        self.sidebar_toggle_button.configure(text=button_text)

    def _update_history_scrollregion(self, _event):
        self.history_canvas.configure(
            scrollregion=self.history_canvas.bbox("all")
        )

    def _resize_history_content(self, event):
        self.history_canvas.itemconfigure(self.history_window, width=event.width)

    def _refresh_history_list(self):
        for child in self.history_inner.winfo_children():
            child.destroy()

        pinned = [entry for entry in self.history if entry["pinned"]]
        recent = [entry for entry in self.history if not entry["pinned"]]
        ttk.Label(
            self.history_inner, text="Pinned", font=("Segoe UI", 9, "bold")
        ).pack(anchor="w", fill="x", pady=(2, 4))
        if pinned:
            for entry in pinned:
                self._create_history_row(entry)
        else:
            ttk.Label(
                self.history_inner, text="No pinned sessions",
                foreground="gray",
            ).pack(anchor="w", padx=6, pady=(0, 8))

        ttk.Label(
            self.history_inner, text="Recent", font=("Segoe UI", 9, "bold")
        ).pack(anchor="w", fill="x", pady=(8, 4))
        if recent:
            for entry in recent:
                self._create_history_row(entry)
        elif not pinned:
            ttk.Label(
                self.history_inner, text="No sessions yet",
                foreground="gray",
            ).pack(anchor="w", padx=6, pady=(0, 8))

    def _create_history_row(self, entry):
        row = ttk.Frame(self.history_inner, padding=(4, 5))
        row.pack(fill="x", pady=1)
        content = ttk.Frame(row)
        content.pack(side="left", fill="x", expand=True)

        dot_color = "#1a7f37" if entry["verdict"] == "valid" else "#cf222e"
        ttk.Label(
            content, text="●", foreground=dot_color,
            font=("Segoe UI", 9),
        ).pack(side="left", padx=(0, 5))
        title = ttk.Label(
            content, text=entry["title"], anchor="w",
            wraplength=155, justify="left",
        )
        title.pack(side="left", fill="x", expand=True)
        if entry["pinned"]:
            ttk.Label(content, text="📌", font=("Segoe UI", 9)).pack(side="left", padx=3)
        time_label = ttk.Label(
            row, text=self._format_time(entry["created_at"]),
            foreground="gray", font=("Segoe UI", 8),
        )
        time_label.pack(side="left", padx=(4, 2))
        menu_button = ttk.Button(
            row, text="⋯", width=3,
            command=lambda session_id=entry["id"]: self._show_history_menu(
                session_id, menu_button
            ),
        )
        menu_button.pack(side="right")

        for widget in (row, content, title):
            widget.bind(
                "<Button-1>",
                lambda _event, session_id=entry["id"]:
                    self._restore_history(session_id),
            )
        for widget in content.winfo_children():
            if widget is not title:
                widget.bind(
                    "<Button-1>",
                    lambda _event, session_id=entry["id"]:
                        self._restore_history(session_id),
                )
        time_label.bind(
            "<Button-1>",
            lambda _event, session_id=entry["id"]:
                self._restore_history(session_id),
        )

    # -----------------------------------------------------------
    # BLOCK 7: Restoring and managing individual sessions
    # -----------------------------------------------------------
    @staticmethod
    def _format_time(timestamp):
        return datetime.fromisoformat(timestamp).strftime("%I:%M %p").lstrip("0")

    def _find_history_entry(self, session_id):
        return next(
            (entry for entry in self.history if entry["id"] == session_id),
            None,
        )

    def _restore_history(self, session_id):
        entry = self._find_history_entry(session_id)
        if entry is None:
            return
        self.title_entry.delete(0, tk.END)
        self.title_entry.insert(0, entry["title"])
        self.pmf_entry.delete(0, tk.END)
        self.pmf_entry.insert(0, entry["pmf"])
        self.events_entry.delete(0, tk.END)
        self.events_entry.insert(0, entry["events"])
        self._write([tuple(line) for line in entry["lines"]])

    def _show_history_menu(self, session_id, button):
        entry = self._find_history_entry(session_id)
        if entry is None:
            return
        menu = tk.Menu(self.root, tearoff=False)
        menu.add_command(
            label="Rename",
            command=lambda: self._rename_history_entry(session_id),
        )
        menu.add_command(
            label="Delete",
            command=lambda: self._delete_history_entry(session_id),
        )
        pin_label = "Unpin" if entry["pinned"] else "Pin"
        menu.add_command(
            label=pin_label,
            command=lambda: self._toggle_pin(session_id),
        )
        menu.tk_popup(
            button.winfo_rootx(), button.winfo_rooty() + button.winfo_height()
        )
        menu.grab_release()

    def _rename_history_entry(self, session_id):
        entry = self._find_history_entry(session_id)
        if entry is None:
            return
        new_title = simpledialog.askstring(
            "Rename session",
            "Enter a title for this session:",
            initialvalue=entry["title"],
            parent=self.root,
        )
        if new_title is None:
            return
        new_title = new_title.strip()
        if not new_title:
            new_title = (
                f"Session {entry['session_number']} · "
                f"{self._format_time(entry['created_at'])}"
            )
        entry["title"] = new_title
        self._save_history()
        self._refresh_history_list()

    def _delete_history_entry(self, session_id):
        entry = self._find_history_entry(session_id)
        if entry is None:
            return
        if not messagebox.askyesno(
            "Delete session",
            f"Delete '{entry['title']}' from history?",
            parent=self.root,
        ):
            return
        self.history = [
            item for item in self.history if item["id"] != session_id
        ]
        self._save_history()
        self._refresh_history_list()

    def _toggle_pin(self, session_id):
        entry = self._find_history_entry(session_id)
        if entry is None:
            return
        entry["pinned"] = not entry["pinned"]
        self._save_history()
        self._refresh_history_list()

    def _record_session(self, lines, verdict):
        session_number = max(
            (entry["session_number"] for entry in self.history),
            default=0,
        ) + 1
        timestamp = datetime.now().astimezone().isoformat(timespec="seconds")
        title = self.title_entry.get().strip()
        if not title:
            title = (
                f"Session {session_number} · "
                f"{self._format_time(timestamp)}"
            )
        self.history.insert(0, {
            "id": uuid4().hex,
            "session_number": session_number,
            "title": title,
            "created_at": timestamp,
            "pmf": self.pmf_entry.get(),
            "events": self.events_entry.get(),
            "lines": [[text, tag] for text, tag in lines],
            "verdict": verdict,
            "pinned": False,
        })
        self._save_history()
        self._refresh_history_list()

    # -----------------------------------------------------------
    # BLOCK 8: The main Validate action
    # -----------------------------------------------------------
    def validate(self):
        # Step 1: read and parse the input
        try:
            pmf = parse_pmf(self.pmf_entry.get())
            events = parse_events(self.events_entry.get(), pmf)
        except ValueError as err:
            messagebox.showerror("Input error", str(err))
            self._record_session(
                [
                    (f"Input error: {err}", "fail"),
                    ("VERDICT: INVALID probability assignment", "fail"),
                ],
                "invalid",
            )
            return

        lines = [("RESULTS", "head"), ("", "")]
        all_ok = True

        # Step 2: Axiom 1
        ok1, negatives = check_axiom1(pmf)
        if ok1:
            lines.append(("Axiom 1 (P(A) >= 0): PASS", "pass"))
        else:
            all_ok = False
            bad = ", ".join(f"P({k}) = {v}" for k, v in negatives.items())
            lines.append((f"Axiom 1 (P(A) >= 0): FAIL  ->  {bad}", "fail"))

        # Step 3: Axiom 2
        ok2, total = check_axiom2(pmf)
        if ok2:
            lines.append((f"Axiom 2 (P(S) = 1): PASS  (sum = {total:.6g})", "pass"))
        else:
            all_ok = False
            lines.append((f"Axiom 2 (P(S) = 1): FAIL  (sum = {total:.6g})", "fail"))

        # Step 4: Axiom 3
        if len(events) < 2:
            lines.append(("Axiom 3 (additivity): SKIPPED  (enter at least 2 events)", "head"))
        elif not are_disjoint(events):
            all_ok = False
            lines.append(("Axiom 3 (additivity): FAIL  ->  the events are not disjoint "
                          "(they share an outcome)", "fail"))
        else:
            ok3, p_union, p_sum = check_axiom3(pmf, events)
            detail = f"P(union) = {p_union:.6g},  sum of P(each) = {p_sum:.6g}"
            if ok3:
                lines.append((f"Axiom 3 (additivity): PASS  ({detail})", "pass"))
            else:
                all_ok = False
                lines.append((f"Axiom 3 (additivity): FAIL  ({detail})", "fail"))

        # Step 5: final verdict
        lines.append(("", ""))
        if all_ok:
            lines.append(("VERDICT: VALID probability assignment", "pass"))
        else:
            lines.append(("VERDICT: INVALID probability assignment", "fail"))

        self._write(lines)
        self._record_session(lines, "valid" if all_ok else "invalid")


# ---------------------------------------------------------------
# BLOCK 9: Program entry point
# ---------------------------------------------------------------
if __name__ == "__main__":
    root = tk.Tk()
    AxiomsApp(root)
    root.mainloop()