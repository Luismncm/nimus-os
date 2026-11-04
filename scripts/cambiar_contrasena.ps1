# Cambia la contraseña de un usuario de la web. La dirección de la base y la contraseña se escriben aquí;
# la contraseña se ve como asteriscos y solo pasa al proceso que la cifra, sin guardarse en ningún archivo.
#   powershell -ExecutionPolicy Bypass -File scripts\cambiar_contrasena.ps1
$ErrorActionPreference = 'Stop'
Set-Location (Split-Path $PSScriptRoot -Parent)
function Plain($secure) { [Runtime.InteropServices.Marshal]::PtrToStringAuto([Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)) }

Write-Host ''
Write-Host 'NIMUS · cambiar contraseña de la web' -ForegroundColor Cyan
Write-Host 'Pega la conexión de Neon (postgresql://…).'
$url = Plain (Read-Host 'Dirección de la base' -AsSecureString)
if (-not ($url.StartsWith('postgres://') -or $url.StartsWith('postgresql://'))) { Write-Host 'Esa dirección no empieza con postgresql://. No se hizo nada.' -ForegroundColor Red; exit 1 }
$env:DATABASE_URL = $url -replace '-pooler\.', '.'
$email = Read-Host 'Correo del usuario'

while ($true) {
    $first = Plain (Read-Host 'Nueva contraseña (mínimo 10 caracteres)' -AsSecureString)
    $second = Plain (Read-Host 'Repítela' -AsSecureString)
    if ($first -ne $second) { Write-Host 'No coinciden. Inténtalo de nuevo.' -ForegroundColor Yellow; continue }
    if ($first.Length -lt 10) { Write-Host "Tiene $($first.Length) caracteres; usa al menos 10." -ForegroundColor Yellow; continue }
    break
}
$env:NIMUS_NEW_PASSWORD = $first
& .\.venv\Scripts\python.exe scripts\cambiar_contrasena.py $email
Remove-Item Env:DATABASE_URL, Env:NIMUS_NEW_PASSWORD -ErrorAction SilentlyContinue
