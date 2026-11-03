"""Install only when dependencies are missing/out of the supported range."""
import sys
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

if sys.version_info < (3,11):
    print("NIMUS requiere Python 3.11 o superior.")
    sys.exit(1)
try:
    from packaging.requirements import Requirement
    for line in (Path(__file__).resolve().parents[1]/"requirements.txt").read_text().splitlines():
        if line.strip() and not line.startswith("#"):
            requirement=Requirement(line)
            if version(requirement.name) not in requirement.specifier:
                raise ValueError(f"Actualizar {requirement.name}")
except (ImportError,PackageNotFoundError,ValueError) as exc:
    print(f"Preparando dependencias: {exc}")
    sys.exit(1)
