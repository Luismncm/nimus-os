"""Open a project's files on this computer: the local app runs here, so a saved path opens in its own program.

Programs and scripts are never launched from a link; for those only their folder opens.
"""
import os
import subprocess
import sys
from pathlib import Path

NOT_OPENED = {'.exe', '.bat', '.cmd', '.com', '.ps1', '.psm1', '.vbs', '.vbe', '.js', '.jse', '.wsf', '.wsh', '.msi', '.msp',
              '.scr', '.lnk', '.reg', '.cpl', '.hta', '.pif', '.jar', '.py', '.pyw', '.sh', '.app', '.url'}


def status(target):
    """'Carpeta', 'Archivo' or 'No encontrado' for a path; network paths that are offline read as not found."""
    try:
        path = Path(target)
        return 'Carpeta' if path.is_dir() else 'Archivo' if path.exists() else 'No encontrado'
    except (OSError, ValueError):
        return 'No encontrado'


def can_open(target):
    return Path(target).suffix.lower() not in NOT_OPENED


def _launch(argument):
    if sys.platform == 'win32':
        os.startfile(argument)
    else:
        subprocess.Popen(['open' if sys.platform == 'darwin' else 'xdg-open', argument])


def open_target(target):
    """The file in its program (slicer, CAD, image viewer…) or the folder in the file explorer."""
    found = status(target)
    if found == 'No encontrado':
        raise ValueError('No se encuentra en este equipo. Revisa la ruta o si la unidad de red está conectada.')
    if found == 'Archivo' and not can_open(target):
        raise ValueError('Por seguridad, los programas y scripts no se abren desde aquí; usa «Carpeta».')
    _launch(target)


def reveal(target):
    """The folder that holds the file, with the file selected where the system allows it."""
    found = status(target)
    if found == 'No encontrado':
        raise ValueError('No se encuentra en este equipo. Revisa la ruta o si la unidad de red está conectada.')
    if found == 'Carpeta':
        _launch(target)
    elif sys.platform == 'win32':
        subprocess.Popen(f'explorer /select,"{Path(target)}"')
    elif sys.platform == 'darwin':
        subprocess.Popen(['open', '-R', target])
    else:
        _launch(str(Path(target).parent))
