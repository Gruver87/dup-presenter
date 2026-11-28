# Сохраняет RUNWAYML_API_SECRET в переменные окружения Windows (уровень пользователя).
# Ключ не печатается на экран и не записывается ни в один файл проекта.
# Запуск: правый клик по файлу -> "Выполнить с PowerShell", либо в PowerShell:
#   .\scripts\set_runway_key.ps1

$secure = Read-Host "Вставьте ключ Runway (правый клик мышью, затем Enter)" -AsSecureString
$bstr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
try {
    $key = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($bstr).Trim()
} finally {
    [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr)
}

if ([string]::IsNullOrWhiteSpace($key)) {
    Write-Host "Ключ пустой. Ничего не сохранено." -ForegroundColor Red
    exit 1
}

[Environment]::SetEnvironmentVariable("RUNWAYML_API_SECRET", $key, "User")
Write-Host "Готово: RUNWAYML_API_SECRET сохранён для вашего пользователя Windows." -ForegroundColor Green
Write-Host "Перезапустите console_server.py, чтобы дашборд увидел ключ." -ForegroundColor Yellow
