"""Manage a local llama.cpp server for Universal Code AI (no API key)."""
from __future__ import annotations
import os
import shutil
import signal
import subprocess
import time
from pathlib import Path
from typing import Any
from config import BASE_DIR, LOCAL_MODEL_BASE_URL
from core.local_model import LocalModel

MODEL_DIR = BASE_DIR / "models"
LOG_DIR = BASE_DIR / "logs"
PID_FILE = LOG_DIR / "llama-server.pid"
LOG_FILE = LOG_DIR / "llama-server.log"
DEFAULT_MODEL = MODEL_DIR / "qwen2.5-coder-1.5b-instruct-q4_k_m.gguf"


def _meminfo_kb(key: str) -> int:
    try:
        for line in Path('/proc/meminfo').read_text().splitlines():
            if line.startswith(key + ':'):
                return int(line.split()[1])
    except OSError:
        pass
    return 0


class ModelManager:
    def __init__(self, model_path: str | Path | None = None, port: int = 8080):
        self.model_path = Path(model_path).expanduser() if model_path else DEFAULT_MODEL
        self.port = int(port)
        self.client = LocalModel()
        MODEL_DIR.mkdir(parents=True, exist_ok=True)
        LOG_DIR.mkdir(parents=True, exist_ok=True)

    def device_info(self) -> dict[str, Any]:
        total = _meminfo_kb('MemTotal')
        available = _meminfo_kb('MemAvailable')
        try:
            free = shutil.disk_usage(str(BASE_DIR)).free
        except OSError:
            free = 0
        return {
            'machine': os.uname().machine if hasattr(os, 'uname') else 'unknown',
            'ram_total_gb': round(total / 1024 / 1024, 2) if total else None,
            'ram_available_gb': round(available / 1024 / 1024, 2) if available else None,
            'storage_free_gb': round(free / 1024**3, 2),
            'model_path': str(self.model_path),
            'model_exists': self.model_path.is_file(),
            'model_size_gb': round(self.model_path.stat().st_size / 1024**3, 2) if self.model_path.is_file() else None,
            'server_available': self.client.is_available(),
            'server_url': LOCAL_MODEL_BASE_URL,
        }

    def _read_pid(self) -> int | None:
        try:
            pid = int(PID_FILE.read_text().strip())
            cmdline = Path(f'/proc/{pid}/cmdline').read_bytes().replace(b'\0', b' ').decode(errors='ignore')
            if 'llama-server' in cmdline:
                return pid
        except (OSError, ValueError):
            pass
        return None

    def start(self, context: int = 2048, threads: int | None = None, wait_seconds: int = 90) -> dict[str, Any]:
        if self.client.is_available():
            return {'success': True, 'already_running': True, 'message': 'Local model server already responds on 127.0.0.1:8080.'}
        binary = Path(os.environ['UCA_LLAMA_SERVER']) if os.environ.get('UCA_LLAMA_SERVER') else Path.home() / 'llama.cpp' / 'build' / 'bin' / 'llama-server'
        if not binary.is_file():
            return {'success': False, 'error': f'llama-server binary not found: {binary}. Run bash setup_termux.sh first.'}
        if not self.model_path.is_file():
            return {'success': False, 'error': f'Model file not found: {self.model_path}. Download the GGUF model first.'}
        if self.model_path.suffix.lower() != '.gguf':
            return {'success': False, 'error': 'Model must be a .gguf file.'}
        if _meminfo_kb('MemAvailable') and _meminfo_kb('MemAvailable') < 1800 * 1024:
            return {'success': False, 'error': 'Available RAM is below 1.8 GB. Close other apps and retry; model loading may otherwise be killed by Android.'}
        old_pid = self._read_pid()
        if old_pid:
            try:
                os.kill(old_pid, signal.SIGTERM)
            except OSError:
                pass
        cpu_count = os.cpu_count() or 4
        thread_count = max(1, min(int(threads or min(cpu_count, 4)), 6))
        command = [str(binary), '-m', str(self.model_path), '--host', '127.0.0.1', '--port', str(self.port),
                   '-c', str(max(512, min(int(context), 4096))), '-t', str(thread_count), '--parallel', '1']
        log_handle = LOG_FILE.open('ab')
        process = subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=log_handle,
                                   stderr=subprocess.STDOUT, start_new_session=True, close_fds=True)
        PID_FILE.write_text(str(process.pid), encoding='utf-8')
        deadline = time.time() + max(5, wait_seconds)
        client = LocalModel(base_url=f'http://127.0.0.1:{self.port}/v1')
        while time.time() < deadline:
            if process.poll() is not None:
                return {'success': False, 'error': f'llama-server exited with code {process.returncode}. Check {LOG_FILE}'}
            if client.is_available():
                return {'success': True, 'pid': process.pid, 'model': str(self.model_path),
                        'server': f'http://127.0.0.1:{self.port}', 'context': context, 'threads': thread_count,
                        'log': str(LOG_FILE)}
            time.sleep(1)
        return {'success': False, 'error': f'Server did not become healthy within {wait_seconds}s. Check {LOG_FILE}; model load can take longer on a phone.', 'pid': process.pid}

    def stop(self) -> dict[str, Any]:
        pid = self._read_pid()
        if not pid:
            try:
                PID_FILE.unlink(missing_ok=True)
            except OSError:
                pass
            return {'success': True, 'stopped': False, 'message': 'No managed llama-server process found.'}
        try:
            os.kill(pid, signal.SIGTERM)
            for _ in range(10):
                try:
                    os.kill(pid, 0)
                except OSError:
                    break
                time.sleep(0.5)
            else:
                os.kill(pid, signal.SIGKILL)
            PID_FILE.unlink(missing_ok=True)
            return {'success': True, 'stopped': True, 'pid': pid}
        except OSError as exc:
            PID_FILE.unlink(missing_ok=True)
            return {'success': False, 'error': str(exc)}
