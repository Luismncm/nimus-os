# Copia los datos locales a la base Neon de Vercel y crea el primer usuario administrador.
# La dirección de la base y la contraseña se escriben aquí, ocultas; no se guardan en ningún archivo.
#   powershell -ExecutionPolicy Bypass -File scripts\conectar_neon.ps1
$ErrorActionPreference = 'Stop'
Set-Location (Split-Path $PSScriptRoot -Parent)
$python = '.\.venv\Scripts\python.exe'

Write-Host ''
Write-Host 'NIMUS · conectar con Neon' -ForegroundColor Cyan
Write-Host 'Pega la conexión SIN pooling de Neon (empieza con postgresql:// y el host no dice -pooler).'
$secure = Read-Host 'Dirección de la base' -AsSecureString
$url = [Runtime.InteropServices.Marshal]::PtrToStringAuto([Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure))
if (-not ($url.StartsWith('postgres://') -or $url.StartsWith('postgresql://'))) { Write-Host 'Esa dirección no empieza con postgresql://. No se hizo nada.' -ForegroundColor Red; exit 1 }
# The copy runs one long transaction: it needs the direct host, not the pooler in front of it.
if ($url -match '-pooler\.') { $url = $url -replace '-pooler\.', '.'; Write-Host 'Usaré la conexión directa (sin -pooler).' }
$env:DATABASE_URL = $url

Write-Host ''
Write-Host '1/2 · Copiando tus datos (con respaldo local y verificación de conteos y totales)…' -ForegroundColor Cyan
& $python scripts\migrar_a_postgres.py
if ($LASTEXITCODE -ne 0) { Write-Host 'La copia no se completó; no se guardó nada en Neon. Revisa el mensaje de arriba.' -ForegroundColor Red; exit 1 }

Write-Host ''
Write-Host '2/2 · Tu usuario administrador para entrar a la web' -ForegroundColor Cyan
$email = Read-Host 'Correo'
$name = Read-Host 'Nombre (opcional)'
& $python scripts\crear_usuario.py $email --rol admin --nombre $name
if ($LASTEXITCODE -ne 0) { exit 1 }

Remove-Item Env:DATABASE_URL
Write-Host ''
Write-Host 'Listo. En Vercel → Deployments pulsa Redeploy y entra con ese correo y contraseña.' -ForegroundColor Green
