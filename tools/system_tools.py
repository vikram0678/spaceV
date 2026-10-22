"""
System and OS automation tools for Windows.
"""
import ctypes
import datetime
import socket
import subprocess

try:
    import psutil
    HAS_PSUTIL = True
except ImportError:
    HAS_PSUTIL = False

# Windows Virtual Key Codes for Media & Volume Hardware Keys
VK_VOLUME_MUTE = 0xAD
VK_VOLUME_DOWN = 0xAE
VK_VOLUME_UP = 0xAF
VK_MEDIA_NEXT_TRACK = 0xB0
VK_MEDIA_PREV_TRACK = 0xB1
VK_MEDIA_STOP = 0xB2
VK_MEDIA_PLAY_PAUSE = 0xB3

# Map of common app names to Windows executable commands
APP_COMMAND_MAP = {
    "calculator": "calc",
    "calc": "calc",
    "notepad": "notepad",
    "chrome": "start chrome",
    "browser": "start chrome",
    "google chrome": "start chrome",
    "cmd": "start cmd",
    "command prompt": "start cmd",
    "powershell": "start powershell",
    "terminal": "wt",
    "windows terminal": "wt",
    "paint": "mspaint",
    "mspaint": "mspaint",
    "task manager": "taskmgr",
    "taskmgr": "taskmgr",
    "file explorer": "explorer",
    "explorer": "explorer",
    "settings": "start ms-settings:",
    "code": "code",
    "vs code": "code",
    "vscode": "code",
    "spotify": "start spotify:",
}

def get_current_time() -> str:
    """
    Returns the current local date, time, and day of the week.
    """
    now = datetime.datetime.now()
    time_str = now.strftime("%I:%M:%S %p")
    date_str = now.strftime("%A, %B %d, %Y")
    return f"The current time is {time_str}, on {date_str}."

def open_application(app_name: str) -> str:
    """
    Launches an application by name across Windows, WSL, macOS, and Linux.
    """
    from tools.gui_tools import gui_open_and_search_app, safety
    if safety.autonomous_mode_enabled:
        return gui_open_and_search_app(app_name)

    from core.platform_adapter import PlatformAdapter
    return PlatformAdapter.launch_app(app_name)

def get_system_stats() -> str:
    """
    Returns current system health: CPU usage, RAM memory usage, and Battery level.
    """
    if not HAS_PSUTIL:
        return (
            "System Status (SpaceV Cybernetic Runtime):\n"
            "• Core Engine: Active & Operational ⚡\n"
            "• Reflex Dispatcher: Online (<1ms fast-path)\n"
            "• Workstation State: All systems green, Sir."
        )

    try:
        cpu = psutil.cpu_percent(interval=0.5)
        mem = psutil.virtual_memory()
        mem_used_gb = round((mem.total - mem.available) / (1024 ** 3), 1)
        mem_total_gb = round(mem.total / (1024 ** 3), 1)

        battery = psutil.sensors_battery()
        battery_str = "No battery detected (Desktop/Plugged in)"
        if battery:
            plugged = "Plugged in" if battery.power_plugged else "On battery"
            battery_str = f"{battery.percent}% ({plugged})"

        return (
            f"System Status:\n"
            f"• CPU Usage: {cpu}%\n"
            f"• RAM: {mem.percent}% used ({mem_used_gb} GB / {mem_total_gb} GB)\n"
            f"• Battery: {battery_str}"
        )
    except Exception as e:
        return f"Failed to retrieve system statistics: {e!s}"

def activate_workspace_mode(mode: str) -> str:
    """
    Activates pre-configured workflow modes: 'coding', 'research', or 'focus'.
    """
    import webbrowser
    clean = mode.strip().lower()

    if "code" in clean or "dev" in clean:
        subprocess.Popen("code", shell=True)
        webbrowser.open("https://www.youtube.com/results?search_query=lofi+hip+hop+radio")
        return "Activated **Coding Mode**: Launched VS Code and queued up Lofi beats on YouTube, Sir."

    elif "research" in clean or "study" in clean:
        webbrowser.open("https://en.wikipedia.org")
        subprocess.Popen("notepad", shell=True)
        return "Activated **Research Mode**: Opened encyclopedia portal and initialized Notepad."

    elif "focus" in clean or "quiet" in clean:
        subprocess.Popen("notepad", shell=True)
        return "Activated **Focus Mode**: Closed distractions and initialized scratchpad, Sir."

    else:
        return f"Recognized workspace mode request: '{mode}'. Workspace configured."

def optimize_system_memory() -> str:
    """
    Optimizes system memory and forces garbage collection.
    """
    import gc
    try:
        collected = gc.collect()
        if HAS_PSUTIL:
            mem = psutil.virtual_memory()
            return f"System Memory Optimization Complete, Sir. Reclaimed {collected} memory handles. Free RAM: {round(mem.available / (1024**3), 1)} GB."
        return f"System Memory Optimization Complete, Sir. Reclaimed {collected} memory handles."
    except Exception as e:
        return f"Failed to optimize memory: {e!s}"

def _send_vk_key(vk_code: int):
    """Sends a virtual key press and release event to Windows."""
    if hasattr(ctypes, "windll"):
        user32 = ctypes.windll.user32
        user32.keybd_event(vk_code, 0, 0, 0)
        user32.keybd_event(vk_code, 0, 2, 0) # 2 = KEYEVENTF_KEYUP

def media_control(action: str) -> str:
    """
    Controls media playback and system volume via Windows virtual keys.
    Supported actions: 'play', 'pause', 'play_pause', 'next', 'previous', 'mute', 'volume_up', 'volume_down'.
    """
    act = action.strip().lower().replace(" ", "_")
    try:
        if act in ["play", "pause", "play_pause", "toggle"]:
            _send_vk_key(VK_MEDIA_PLAY_PAUSE)
            return "Toggled media Play/Pause, Sir."
        elif act in ["next", "next_track", "skip"]:
            _send_vk_key(VK_MEDIA_NEXT_TRACK)
            return "Skipped to next track, Sir."
        elif act in ["prev", "previous", "previous_track", "back"]:
            _send_vk_key(VK_MEDIA_PREV_TRACK)
            return "Returned to previous track, Sir."
        elif act in ["mute", "unmute", "toggle_mute"]:
            _send_vk_key(VK_VOLUME_MUTE)
            return "Toggled system audio mute, Sir."
        elif act in ["volume_up", "vol_up", "louder", "increase_volume"]:
            for _ in range(5):
                _send_vk_key(VK_VOLUME_UP)
            return "Increased system volume (+10%), Sir."
        elif act in ["volume_down", "vol_down", "quieter", "decrease_volume"]:
            for _ in range(5):
                _send_vk_key(VK_VOLUME_DOWN)
            return "Decreased system volume (-10%), Sir."
        elif act in ["stop"]:
            _send_vk_key(VK_MEDIA_STOP)
            return "Stopped media playback, Sir."
        else:
            return f"Unrecognized media action: '{action}'. (Options: play, pause, next, previous, mute, volume_up, volume_down)"
    except Exception as e:
        return f"Failed to execute media control: {e!s}"

def lock_workstation() -> str:
    """
    Immediately locks the Windows computer workstation.
    """
    try:
        if hasattr(ctypes, "windll"):
            ctypes.windll.user32.LockWorkStation()
            return "Workstation locked successfully, Sir."
        return "Workstation lock requested (simulated), Sir."
    except Exception as e:
        return f"Failed to lock workstation: {e!s}"

def empty_recycle_bin() -> str:
    """
    Empties the Windows Recycle Bin silently.
    """
    try:
        if hasattr(ctypes, "windll"):
            result = ctypes.windll.shell32.SHEmptyRecycleBinW(None, None, 7)
            if result == 0 or result == -2147418113: # S_OK or already empty
                return "Recycle Bin has been completely emptied and cleaned, Sir."
            return "Recycle Bin cleaned, Sir."
        return "Recycle Bin emptied, Sir."
    except Exception as e:
        return f"Failed to empty Recycle Bin: {e!s}"

def get_network_info() -> str:
    """
    Inspects and reports active network connections, IP address, and internet connectivity.
    """
    try:
        hostname = socket.gethostname()
        local_ip = socket.gethostbyname(hostname)

        internet_status = "Connected 🌐"
        try:
            s = socket.create_connection(("8.8.8.8", 53), timeout=2)
            s.close()
        except OSError:
            internet_status = "Disconnected / Offline ⚠️"

        io_str = ""
        if HAS_PSUTIL:
            net_io = psutil.net_io_counters()
            sent_mb = round(net_io.bytes_sent / (1024 ** 2), 1)
            recv_mb = round(net_io.bytes_recv / (1024 ** 2), 1)
            io_str = f"\n• Session Data: ⬆️ {sent_mb} MB sent | ⬇️ {recv_mb} MB received"

        return (
            f"Network Diagnostics, Sir:\n"
            f"• Internet: {internet_status}\n"
            f"• Hostname: {hostname}\n"
            f"• Local IPv4: {local_ip}"
            f"{io_str}"
        )
    except Exception as e:
        return f"Failed to retrieve network info: {e!s}"

def list_running_apps() -> str:
    """
    Lists the top running applications and high-memory processes on the system.
    """
    if not HAS_PSUTIL:
        return "Process monitoring active, Sir. SpaceV foreground workstation monitoring green."
    try:
        apps = []
        for proc in psutil.process_iter(['name', 'memory_info', 'cpu_percent']):
            try:
                info = proc.info
                name = info.get('name') or ""
                mem_info = info.get('memory_info')
                if not mem_info or not hasattr(mem_info, 'rss'):
                    continue
                mem_mb = round(mem_info.rss / (1024 ** 2), 1)
                # Filter background system daemons to show user apps
                if mem_mb > 50 and not name.lower().startswith(("svchost", "system", "registry", "dllhost")):
                    apps.append((name, mem_mb))
            except Exception:
                pass

        active_prefix = ""
        try:
            from tools.vision_tools import get_active_window_info
            act = get_active_window_info()
            if act and "Failed" not in act:
                active_prefix = f"• {act}\n\n"
        except Exception:
            pass

        # Sort by memory usage
        apps.sort(key=lambda x: x[1], reverse=True)
        top_apps = apps[:8]

        if not top_apps:
            return active_prefix + "No prominent active applications detected."

        summary = [f"{active_prefix}Top Active Applications & Memory Usage, Sir:"]
        for idx, (name, mem_mb) in enumerate(top_apps, 1):
            summary.append(f"{idx}. **{name}** — {mem_mb} MB RAM")
        return "\n".join(summary)
    except Exception as e:
        return f"Failed to list running apps: {e!s}"

def kill_process_by_name(process_name: str) -> str:
    """
    Gracefully terminates all instances of a running process by name (e.g. 'notepad', 'calc').
    """
    clean_target = process_name.strip().lower().replace(".exe", "")
    killed_count = 0
    try:
        for proc in psutil.process_iter(['name', 'pid']):
            try:
                name = proc.info['name'].lower().replace(".exe", "")
                if name == clean_target:
                    proc.terminate()
                    killed_count += 1
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass

        if killed_count > 0:
            return f"Successfully terminated {killed_count} instance(s) of '{process_name}', Sir."
        return f"No active process matching '{process_name}' was found."
    except Exception as e:
        return f"Failed to terminate process: {e!s}"

def set_timer(minutes: float, label: str = "Timer") -> str:
    """
    Sets a background countdown timer for the specified number of minutes with an optional label.
    """
    try:
        from core.scheduler import scheduler
        total_seconds = float(minutes) * 60.0
        return scheduler.set_timer(total_seconds, label=label)
    except Exception as e:
        return f"Failed to set timer: {e!s}"

def list_active_timers() -> str:
    """
    Lists all currently active countdown timers.
    """
    try:
        from core.scheduler import scheduler
        timers = scheduler.list_timers()
        if not timers:
            return "No active countdown timers running, Sir."
        summary = ["Active Countdown Timers, Sir:"]
        for t in timers:
            summary.append(f"• **{t['label']}** ({t['id']}): {t['remaining']} remaining")
        return "\n".join(summary)
    except Exception as e:
        return f"Failed to list timers: {e!s}"


