"""Open this NIMUS instance if running; otherwise start it on a free local port."""
from __future__ import annotations

import argparse
import json
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PORTS = range(8502, 8513)


def listening_instances() -> list[dict]:
    # Compare the absolute app path, so an unrelated Streamlit app is not reused.
    command = r"""$ErrorActionPreference='Stop'
    $result = @(Get-NetTCPConnection -State Listen -ErrorAction SilentlyContinue |
        Where-Object { $_.LocalPort -ge 8502 -and $_.LocalPort -le 8512 } |
        ForEach-Object {
            $process = Get-CimInstance Win32_Process -Filter ('ProcessId = ' + $_.OwningProcess)
            [PSCustomObject]@{port=$_.LocalPort; command=$process.CommandLine}
        })
    ConvertTo-Json -InputObject $result -Compress
    """
    result = subprocess.run(['powershell.exe', '-NoProfile', '-NonInteractive', '-Command', command],
                            capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=20,
                            creationflags=subprocess.CREATE_NO_WINDOW)
    if result.returncode:
        raise RuntimeError('No se pudo comprobar qué aplicación usa el puerto. ' + result.stderr.strip())
    rows = json.loads(result.stdout.strip() or '[]')
    return rows if isinstance(rows, list) else [rows]


def existing_port(app: Path, instances: list[dict]) -> int | None:
    identity = str(app.resolve()).casefold()
    for row in instances:
        command = (row.get('command') or '').casefold()
        if identity in command and 'streamlit' in command:
            return int(row['port'])
    return None


def healthy(port: int) -> bool:
    try:
        with urllib.request.urlopen(f'http://127.0.0.1:{port}/_stcore/health', timeout=1) as response:
            return response.status == 200 and response.read().strip() == b'ok'
    except (urllib.error.URLError, TimeoutError, OSError):
        return False


def port_is_free(port: int) -> bool:
    with socket.socket() as sock:
        if hasattr(socket, 'SO_EXCLUSIVEADDRUSE'):
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        try:
            sock.bind(('127.0.0.1', port))
            return True
        except OSError:
            return False


def available_port() -> int:
    for port in PORTS:
        if port_is_free(port):
            return port
    raise RuntimeError('No hay un puerto local libre entre 8502 y 8512. Cierra una instancia y vuelve a intentar.')


def wait_ready(port: int, process=None, seconds: float = 30) -> bool:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if process is not None and process.poll() is not None:
            return False
        if healthy(port):
            return True
        time.sleep(0.25)
    return False


def stop_owned_process(process) -> None:
    if process.poll() is None:
        subprocess.run(['taskkill.exe', '/PID', str(process.pid), '/T', '/F'],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                       creationflags=subprocess.CREATE_NO_WINDOW)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true', help='Comprueba el arranque sin abrir navegador ni iniciar otro servidor.')
    options = parser.parse_args()
    app = ROOT / 'app.py'
    try:
        port = existing_port(app, listening_instances())
        if port is not None:
            url = f'http://127.0.0.1:{port}/'
            if not wait_ready(port, seconds=10):
                raise RuntimeError(f'NIMUS ya está iniciado en {url}, pero no responde. Reinicia su ventana y vuelve a intentar.')
            print(f'NIMUS ya está funcionando: {url}', flush=True)
            if not options.check:
                webbrowser.open(url)
            return 0
        port = available_port()
        url = f'http://127.0.0.1:{port}/'
        if options.check:
            print(f'NIMUS puede iniciarse en {url}', flush=True)
            return 0
        print(f'Iniciando NIMUS en {url}', flush=True)
        process = subprocess.Popen([sys.executable, '-m', 'streamlit', 'run', str(app),
                                    '--server.address', '127.0.0.1', '--server.port', str(port), '--server.headless', 'true'],
                                   cwd=ROOT, creationflags=subprocess.CREATE_NEW_PROCESS_GROUP)
        try:
            if not wait_ready(port, process):
                raise RuntimeError('NIMUS no pudo arrancar. Revisa el mensaje del servidor que aparece arriba.')
            webbrowser.open(url)
            print('Para detener NIMUS, pulsa Ctrl+C en esta ventana.', flush=True)
            return process.wait()
        except KeyboardInterrupt:
            return 0
        finally:
            stop_owned_process(process)
    except (RuntimeError, subprocess.SubprocessError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
