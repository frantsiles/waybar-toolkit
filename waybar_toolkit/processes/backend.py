"""Backend for querying processes and system stats via /proc.

No external dependencies — reads directly from the Linux procfs.
"""

from __future__ import annotations

import os
import signal
import time
from dataclasses import dataclass, field
from pathlib import Path

# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class ProcessInfo:
    """Information about a single process."""

    pid: int
    ppid: int
    name: str
    user: str
    state: str
    cpu_percent: float
    mem_percent: float
    mem_rss_kb: int
    threads: int
    cmdline: str

    # Internal — previous CPU jiffies for delta calculation
    _utime: int = field(default=0, repr=False)
    _stime: int = field(default=0, repr=False)


@dataclass
class SystemStats:
    """System-wide resource statistics."""

    cpu_percent_total: float
    cpu_percent_per_core: list[float]
    mem_total_kb: int
    mem_used_kb: int
    mem_available_kb: int
    mem_cached_kb: int
    uptime_seconds: float
    load_avg: tuple[float, float, float]
    process_count: int


# ---------------------------------------------------------------------------
# Signal definitions
# ---------------------------------------------------------------------------

SIGNALS = {
    "SIGTERM": signal.SIGTERM,
    "SIGKILL": signal.SIGKILL,
    "SIGSTOP": signal.SIGSTOP,
    "SIGCONT": signal.SIGCONT,
    "SIGHUP": signal.SIGHUP,
}


# ---------------------------------------------------------------------------
# UID → username cache
# ---------------------------------------------------------------------------

_UID_CACHE: dict[int, str] = {}


def _uid_to_user(uid: int) -> str:
    """Resolve UID to username, caching results."""
    if uid in _UID_CACHE:
        return _UID_CACHE[uid]
    try:
        import pwd

        name = pwd.getpwuid(uid).pw_name
    except (KeyError, ImportError):
        name = str(uid)
    _UID_CACHE[uid] = name
    return name


# ---------------------------------------------------------------------------
# /proc readers
# ---------------------------------------------------------------------------

PROC = Path("/proc")


def _read_file(path: Path) -> str | None:
    """Read a proc file, returning None on any error."""
    try:
        return path.read_text()
    except (OSError, PermissionError):
        return None


def _parse_proc_stat_line(line: str) -> tuple[int, ...]:
    """Parse a 'cpuN ...' line from /proc/stat into integer jiffies."""
    parts = line.split()
    return tuple(int(p) for p in parts[1:])


def _read_proc_pid(pid: int) -> ProcessInfo | None:
    """Read process info from /proc/<pid>/."""
    pid_dir = PROC / str(pid)

    # --- /proc/<pid>/stat ---
    stat_text = _read_file(pid_dir / "stat")
    if not stat_text:
        return None

    # The comm field is enclosed in parens and may contain spaces/parens itself.
    # Find the last ')' to safely split.
    try:
        comm_start = stat_text.index("(")
        comm_end = stat_text.rindex(")")
        comm = stat_text[comm_start + 1 : comm_end]
        fields = stat_text[comm_end + 2 :].split()
    except (ValueError, IndexError):
        return None

    if len(fields) < 20:
        return None

    state = fields[0]       # index 2 in stat(5), but 0 after split past comm
    ppid = int(fields[1])   # index 3
    utime = int(fields[11]) # index 13
    stime = int(fields[12]) # index 14
    threads = int(fields[17])  # index 19

    # --- /proc/<pid>/status (for UID and RSS) ---
    status_text = _read_file(pid_dir / "status")
    uid = 0
    rss_kb = 0
    if status_text:
        for line in status_text.splitlines():
            if line.startswith("Uid:"):
                uid = int(line.split()[1])
            elif line.startswith("VmRSS:"):
                try:
                    rss_kb = int(line.split()[1])
                except (ValueError, IndexError):
                    pass

    # --- /proc/<pid>/cmdline ---
    cmdline_text = _read_file(pid_dir / "cmdline")
    if cmdline_text:
        cmdline = cmdline_text.replace("\x00", " ").strip()
    else:
        cmdline = f"[{comm}]"

    user = _uid_to_user(uid)

    return ProcessInfo(
        pid=pid,
        ppid=ppid,
        name=comm,
        user=user,
        state=state,
        cpu_percent=0.0,  # Calculated later via delta
        mem_percent=0.0,  # Calculated later with total mem
        mem_rss_kb=rss_kb,
        threads=threads,
        cmdline=cmdline if cmdline else f"[{comm}]",
        _utime=utime,
        _stime=stime,
    )


# ---------------------------------------------------------------------------
# ProcessBackend
# ---------------------------------------------------------------------------


class ProcessBackend:
    """Reads process and system information from /proc."""

    def __init__(self) -> None:
        # Previous snapshots for CPU% delta calculation
        self._prev_procs: dict[int, tuple[int, int]] = {}  # pid → (utime, stime)
        self._prev_cpu_jiffies: list[tuple[int, ...]] = []  # per core
        self._prev_total_jiffies: tuple[int, ...] = ()
        self._prev_time: float = 0.0
        self._hz: int = os.sysconf("SC_CLK_TCK")  # Usually 100

    # ------------------------------------------------------------------
    # Processes
    # ------------------------------------------------------------------

    def get_processes(self) -> list[ProcessInfo]:
        """Return a list of all running processes with CPU/MEM%."""
        now = time.monotonic()
        elapsed = now - self._prev_time if self._prev_time else 0.0
        self._prev_time = now

        mem_total = self._get_mem_total_kb()

        procs: list[ProcessInfo] = []
        for entry in PROC.iterdir():
            if not entry.name.isdigit():
                continue
            pid = int(entry.name)
            info = _read_proc_pid(pid)
            if info is None:
                continue

            # CPU% delta
            if elapsed > 0 and pid in self._prev_procs:
                prev_u, prev_s = self._prev_procs[pid]
                delta_jiffies = (info._utime - prev_u) + (info._stime - prev_s)
                cpu_seconds = delta_jiffies / self._hz
                info.cpu_percent = round((cpu_seconds / elapsed) * 100, 1)
            else:
                info.cpu_percent = 0.0

            # MEM%
            if mem_total > 0:
                info.mem_percent = round((info.mem_rss_kb / mem_total) * 100, 1)

            self._prev_procs[pid] = (info._utime, info._stime)
            procs.append(info)

        # Clean stale PIDs from cache
        live_pids = {p.pid for p in procs}
        self._prev_procs = {
            k: v for k, v in self._prev_procs.items() if k in live_pids
        }

        return procs

    # ------------------------------------------------------------------
    # System stats
    # ------------------------------------------------------------------

    def get_system_stats(self) -> SystemStats:
        """Return system-wide CPU, memory, uptime, and load average."""
        # --- CPU from /proc/stat ---
        stat_text = _read_file(PROC / "stat")
        cpu_total = 0.0
        cpu_per_core: list[float] = []

        if stat_text:
            lines = stat_text.splitlines()
            new_total: tuple[int, ...] = ()
            new_cores: list[tuple[int, ...]] = []

            for line in lines:
                if line.startswith("cpu "):
                    new_total = _parse_proc_stat_line(line)
                elif line.startswith("cpu"):
                    new_cores.append(_parse_proc_stat_line(line))

            cpu_total = self._calc_cpu_percent(
                self._prev_total_jiffies, new_total
            )
            for i, core in enumerate(new_cores):
                prev = (
                    self._prev_cpu_jiffies[i]
                    if i < len(self._prev_cpu_jiffies)
                    else ()
                )
                cpu_per_core.append(self._calc_cpu_percent(prev, core))

            self._prev_total_jiffies = new_total
            self._prev_cpu_jiffies = new_cores

        # --- Memory from /proc/meminfo ---
        mem_total, mem_available, mem_cached = 0, 0, 0
        meminfo = _read_file(PROC / "meminfo")
        if meminfo:
            for line in meminfo.splitlines():
                if line.startswith("MemTotal:"):
                    mem_total = int(line.split()[1])
                elif line.startswith("MemAvailable:"):
                    mem_available = int(line.split()[1])
                elif line.startswith("Cached:"):
                    mem_cached = int(line.split()[1])
        mem_used = mem_total - mem_available

        # --- Uptime from /proc/uptime ---
        uptime = 0.0
        uptime_text = _read_file(PROC / "uptime")
        if uptime_text:
            uptime = float(uptime_text.split()[0])

        # --- Load average ---
        load_avg = os.getloadavg()

        # --- Process count ---
        proc_count = sum(1 for e in PROC.iterdir() if e.name.isdigit())

        return SystemStats(
            cpu_percent_total=cpu_total,
            cpu_percent_per_core=cpu_per_core,
            mem_total_kb=mem_total,
            mem_used_kb=mem_used,
            mem_available_kb=mem_available,
            mem_cached_kb=mem_cached,
            uptime_seconds=uptime,
            load_avg=(load_avg[0], load_avg[1], load_avg[2]),
            process_count=proc_count,
        )

    # ------------------------------------------------------------------
    # Signals
    # ------------------------------------------------------------------

    @staticmethod
    def send_signal(pid: int, sig: int) -> bool:
        """Send a signal to a process. Returns True on success."""
        try:
            os.kill(pid, sig)
            return True
        except (ProcessLookupError, PermissionError, OSError):
            return False

    # ------------------------------------------------------------------
    # Process details
    # ------------------------------------------------------------------

    @staticmethod
    def get_process_details(pid: int) -> dict | None:
        """Read extended details for a single process."""
        pid_dir = PROC / str(pid)
        if not pid_dir.exists():
            return None

        details: dict = {"pid": pid}

        # cmdline
        cmdline_text = _read_file(pid_dir / "cmdline")
        details["cmdline"] = (
            cmdline_text.replace("\x00", " ").strip() if cmdline_text else ""
        )

        # status fields
        status_text = _read_file(pid_dir / "status")
        if status_text:
            for line in status_text.splitlines():
                key, _, value = line.partition(":")
                key = key.strip()
                value = value.strip()
                if key in (
                    "Threads", "VmSize", "VmRSS", "VmSwap",
                    "voluntary_ctxt_switches", "nonvoluntary_ctxt_switches",
                ):
                    details[key] = value

        # fd count
        fd_dir = pid_dir / "fd"
        try:
            details["open_fds"] = len(list(fd_dir.iterdir()))
        except (OSError, PermissionError):
            details["open_fds"] = "N/A"

        # cwd
        try:
            details["cwd"] = str((pid_dir / "cwd").resolve())
        except (OSError, PermissionError):
            details["cwd"] = "N/A"

        # exe
        try:
            details["exe"] = str((pid_dir / "exe").resolve())
        except (OSError, PermissionError):
            details["exe"] = "N/A"

        return details

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _get_mem_total_kb() -> int:
        """Read MemTotal from /proc/meminfo."""
        meminfo = _read_file(PROC / "meminfo")
        if meminfo:
            for line in meminfo.splitlines():
                if line.startswith("MemTotal:"):
                    return int(line.split()[1])
        return 0

    @staticmethod
    def _calc_cpu_percent(
        prev: tuple[int, ...], curr: tuple[int, ...]
    ) -> float:
        """Calculate CPU usage percent from two jiffies snapshots."""
        if not prev or not curr or len(prev) < 4 or len(curr) < 4:
            return 0.0

        prev_idle = prev[3] + (prev[4] if len(prev) > 4 else 0)  # idle + iowait
        curr_idle = curr[3] + (curr[4] if len(curr) > 4 else 0)

        prev_total = sum(prev)
        curr_total = sum(curr)

        total_delta = curr_total - prev_total
        idle_delta = curr_idle - prev_idle

        if total_delta <= 0:
            return 0.0

        return round(((total_delta - idle_delta) / total_delta) * 100, 1)

    @staticmethod
    def format_uptime(seconds: float) -> str:
        """Format uptime seconds into a human-readable string."""
        days = int(seconds // 86400)
        hours = int((seconds % 86400) // 3600)
        minutes = int((seconds % 3600) // 60)
        if days > 0:
            return f"{days}d {hours}h {minutes}m"
        if hours > 0:
            return f"{hours}h {minutes}m"
        return f"{minutes}m"
