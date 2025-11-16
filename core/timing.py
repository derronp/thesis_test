# core/timing.py
from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
import time, csv, contextlib

def now_ms() -> float:
    return time.perf_counter() * 1000.0

@dataclass
class TimingEvent:
    iter: int
    phase: str
    step_id: str
    label: str
    t_ms: float
    dt_ms: float
    deadline_ms: float | None
    status: str  # "PASS" | "SOFTMISS" | "HARDMISS" | ""

class TimingSession:
    """
    Minimal timing logger: append rows and write a CSV at the end or anytime.
    """
    def __init__(self, csv_path: Path, start_ms: float | None = None):
        self.csv_path = Path(csv_path)
        self.csv_path.parent.mkdir(parents=True, exist_ok=True)
        self.t0 = now_ms() if start_ms is None else start_ms
        self.rows: list[TimingEvent] = []
        self.iter_idx = 0

    def new_iter(self):
        self.iter_idx += 1

    @contextlib.contextmanager
    def measure(self, phase: str, step_id: str = "", label: str = "",
                deadline_ms: float | None = None, hard_ratio: float = 1.0):
        """
        Context manager: with ts.measure("act", step_id="a3", label="run_proc", deadline_ms=50):
            ... measured code ...
        - If deadline_ms is set:
            status = PASS if dt <= deadline_ms
            status = SOFTMISS if dt > deadline_ms but dt <= hard_ratio*deadline_ms
            status = HARDMISS if dt > hard_ratio*deadline_ms
        """
        t1 = now_ms()
        try:
            yield
        finally:
            t2 = now_ms()
            dt = t2 - t1
            status = ""
            if deadline_ms is not None:
                hard = (hard_ratio or 1.0) * deadline_ms
                if dt <= deadline_ms:
                    status = "PASS"
                elif dt <= hard:
                    status = "SOFTMISS"
                else:
                    status = "HARDMISS"
            ev = TimingEvent(
                iter=self.iter_idx,
                phase=phase,
                step_id=step_id,
                label=label,
                t_ms=(t2 - self.t0),
                dt_ms=dt,
                deadline_ms=(deadline_ms if deadline_ms is not None else -1.0),
                status=status,
            )
            self.rows.append(ev)

    def write_csv(self):
        with self.csv_path.open("w", newline="", encoding="utf-8") as fp:
            w = csv.writer(fp)
            w.writerow(["iter", "phase", "step_id", "label", "t_ms", "dt_ms", "deadline_ms", "status"])
            for r in self.rows:
                w.writerow([r.iter, r.phase, r.step_id, r.label, f"{r.t_ms:.3f}", f"{r.dt_ms:.3f}",
                            f"{r.deadline_ms:.3f}" if r.deadline_ms is not None else "", r.status])

# Optional plotting helper (matplotlib). Safe to import if available.
def plot_timing(csv_path: Path, out_png: Path):
    try:
        import pandas as pd
        import matplotlib.pyplot as plt
    except Exception:
        return
    df = pd.read_csv(csv_path)
    if df.empty: return

    # Two simple figures: duration-by-phase and a timeline (cumulative t_ms vs dt_ms)
    fig1 = plt.figure(figsize=(7, 3.2))
    ax = fig1.gca()
    parts = df.groupby("phase")["dt_ms"].sum().sort_values(ascending=False)
    ax.bar(parts.index, parts.values)
    ax.set_ylabel("Total time (ms)")
    ax.set_title("Phase breakdown")
    fig1.tight_layout()
    out_png.parent.mkdir(parents=True, exist_ok=True)
    fig1.savefig(out_png.with_name(out_png.stem + "_breakdown.png"), dpi=140)
    plt.close(fig1)

    fig2 = plt.figure(figsize=(7, 3.2))
    ax2 = fig2.gca()
    ax2.scatter(df["t_ms"], df["dt_ms"], s=10)
    ax2.set_xlabel("t since start (ms)")
    ax2.set_ylabel("dt (ms)")
    ax2.set_title("Timeline (operation durations)")
    fig2.tight_layout()
    fig2.savefig(out_png.with_name(out_png.stem + "_timeline.png"), dpi=140)
    plt.close(fig2)
