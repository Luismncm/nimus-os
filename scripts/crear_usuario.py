"""Create a user of the cloud app. The password is typed in the terminal and only its scrypt hash is stored.

    set DATABASE_URL=postgresql://…   (the Neon database from Vercel)
    python scripts/crear_usuario.py correo@ejemplo.com --rol admin --nombre "Luis"
    python scripts/crear_usuario.py taller@ejemplo.com            # rol taller: producción, sin finanzas
"""
import argparse
import getpass
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('correo')
    parser.add_argument('--rol', choices=('admin', 'taller'), default='taller')
    parser.add_argument('--nombre', default='')
    args = parser.parse_args()
    if not os.environ.get('DATABASE_URL', '').startswith(('postgres://', 'postgresql://')):
        sys.exit('Define DATABASE_URL con la dirección de Postgres.')
    password = getpass.getpass('Contraseña (mínimo 10 caracteres): ')
    if password != getpass.getpass('Repítela: '):
        sys.exit('Las contraseñas no coinciden.')
    from cloud.auth import create_user
    try:
        user_id = create_user(args.correo, password, role=args.rol, name=args.nombre)
    except ValueError as exc:
        sys.exit(str(exc))
    print(f'Usuario {args.correo} creado (id {user_id}, rol {args.rol}).')


if __name__ == '__main__':
    main()
