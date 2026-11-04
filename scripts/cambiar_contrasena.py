"""Change the password of a cloud app user. The new password is typed in the terminal; only its scrypt hash is stored.

    set DATABASE_URL=postgresql://…   (the Neon database from Vercel)
    python scripts/cambiar_contrasena.py correo@ejemplo.com
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
    args = parser.parse_args()
    if not os.environ.get('DATABASE_URL', '').startswith(('postgres://', 'postgresql://')):
        sys.exit('Define DATABASE_URL con la dirección de Postgres.')
    # The PowerShell wrapper asks with visible asterisks and hands the password over in this process only.
    password = os.environ.pop('NIMUS_NEW_PASSWORD', None)
    if password is None:
        password = getpass.getpass('Nueva contraseña (mínimo 10 caracteres): ')
        if password != getpass.getpass('Repítela: '):
            sys.exit('Las contraseñas no coinciden.')
    import db
    from cloud.auth import ensure_users, hash_password
    try:
        digest = hash_password(password)
    except ValueError as exc:
        sys.exit(str(exc))
    with db.connect(write=True) as conn:
        ensure_users(conn)
        row = conn._raw.execute('UPDATE nimus_users SET password_hash = %s WHERE LOWER(email) = LOWER(%s) RETURNING id',
                                (digest, args.correo.strip())).fetchone()
    if not row:
        sys.exit(f'No existe un usuario con el correo {args.correo}.')
    print(f'Contraseña de {args.correo} actualizada. Las sesiones abiertas siguen activas hasta que expiren o cierren sesión.')


if __name__ == '__main__':
    main()
