"""
Global Background Hotkey Listener & IPC Summon Bridge for SpaceV.
Multi-modal activation architecture:
1. Native OS Keyboard Hook (Windows Win32 / supported X11 via pynput)
2. Localhost IPC Summon Bridge (TCP port 19890) for cross-VM (WSL2 <-> Windows Host) triggers
3. Graceful degradation to Arc Reactor Floating HUD and System Tray
"""

import socket
import threading
from PyQt6.QtCore import QObject, pyqtSignal

try:
    from pynput import keyboard
except ImportError:
    keyboard = None


class GlobalHotkeyListener(QObject):
    toggle_requested = pyqtSignal()

    def __init__(self, ipc_port: int = 19890):
        super().__init__()
        self._current_keys = set()
        self._listener = None
        self._ipc_port = ipc_port
        self._ipc_running = False
        self._ipc_socket = None
        self._ipc_thread = None
        self.start()

    def start(self):
        """Starts background hotkey listener and local IPC summon bridge."""
        self._start_keyboard_listener()
        self._start_ipc_bridge()

    def _start_keyboard_listener(self):
        if keyboard is None:
            print("[HOTKEY] ℹ️  Native OS keyboard hook unavailable (pynput disabled on this platform).")
            print("[HOTKEY] 💡 Summon SpaceV via: Arc Reactor HUD, System Tray, or IPC Bridge.")
            return

        def on_press(key):
            try:
                self._current_keys.add(key)
                
                # Check Ctrl + Space
                is_ctrl = (
                    keyboard.Key.ctrl in self._current_keys or
                    keyboard.Key.ctrl_l in self._current_keys or
                    keyboard.Key.ctrl_r in self._current_keys
                )
                is_space = (
                    keyboard.Key.space in self._current_keys or
                    getattr(key, 'char', None) == ' '
                )
                
                if is_ctrl and is_space:
                    print("[HOTKEY] ⚡ 'Ctrl + Space' pressed -> Toggling SpaceV window!")
                    self.toggle_requested.emit()
            except Exception:
                pass

        def on_release(key):
            try:
                self._current_keys.discard(key)
            except Exception:
                pass

        try:
            if self._listener is None:
                self._listener = keyboard.Listener(on_press=on_press, on_release=on_release)
                self._listener.daemon = True
                self._listener.start()
                print("[HOTKEY] ⚡ Global keyboard hook active: 'Ctrl + Space'")
        except Exception as e:
            print(f"[HOTKEY] Keyboard hook notice: {e}")

    def _start_ipc_bridge(self):
        """Spins up a lightweight loopback TCP server to allow cross-host/WSL2 window toggling."""
        try:
            self._ipc_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self._ipc_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self._ipc_socket.bind(("127.0.0.1", self._ipc_port))
            self._ipc_socket.listen(5)
            self._ipc_socket.settimeout(1.0)
            self._ipc_running = True

            def _ipc_worker():
                while self._ipc_running:
                    try:
                        conn, _ = self._ipc_socket.accept()
                        with conn:
                            if not self._ipc_running:
                                break
                            _ = conn.recv(64)
                            # Any connection or 'toggle' command summons SpaceV
                            self.toggle_requested.emit()
                            conn.sendall(b"OK: SpaceV Toggled\n")
                    except TimeoutError:
                        continue
                    except OSError:
                        break

            self._ipc_thread = threading.Thread(target=_ipc_worker, daemon=True)
            self._ipc_thread.start()
            print(f"[HOTKEY] 🌐 IPC Summon Bridge active on 127.0.0.1:{self._ipc_port}")
        except Exception as e:
            # If port is already in use or unavailable, log and continue gracefully
            print(f"[HOTKEY] IPC Bridge notice: {e}")

    def stop(self):
        """Halts the global background keyboard listener and IPC bridge."""
        if self._listener:
            try:
                self._listener.stop()
            except Exception:
                pass
            self._listener = None

        if self._ipc_running:
            self._ipc_running = False
            # Ping loopback to unblock accept() immediately
            try:
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as dummy:
                    dummy.settimeout(0.2)
                    dummy.connect(("127.0.0.1", self._ipc_port))
            except Exception:
                pass
            if self._ipc_socket:
                try:
                    self._ipc_socket.close()
                except Exception:
                    pass
                self._ipc_socket = None
