# Скрипт проверки Этапа 2: Director Script engine (DeepSeek, fail-closed, 1-10 мин, multi-act).
#
# Запуск из корня dup-presenter:
#   powershell -ExecutionPolicy Bypass -File scripts\verify_stage2_director.ps1
# С живым вызовом DeepSeek (1 минута, RU, расходует токены; результат только в work\director_live\):
#   powershell -ExecutionPolicy Bypass -File scripts\verify_stage2_director.ps1 -Live
#
# Без -Live тесты полностью офлайн (сеть подменяется); ключ DeepSeek не требуется.

param([switch]$Live)

$ErrorActionPreference = "Continue"
$env:PYTHONIOENCODING = "utf-8"
$failed = @()

function Step($name, [scriptblock]$cmd) {
    Write-Host ""
    Write-Host "=== $name ===" -ForegroundColor Cyan
    & $cmd
    $rc = $LASTEXITCODE
    if ($rc -eq 0) {
        Write-Host "[PASS] $name" -ForegroundColor Green
    } else {
        Write-Host "[FAIL] $name (exit $rc)" -ForegroundColor Red
        $script:failed += $name
    }
}

Step "compile: director_script.py" { python -m py_compile scripts\director_script.py }
Step "unit: director_script (offline, mocked LLM and HTTP)" {
    python -m unittest discover -s tests -p "test_director_script.py" -q
}
Step "regression: cinema_clip + deck_doctor + build_deck validation" {
    python -m unittest discover -s tests -p "test_cinema_clip.py" -q
}

if ($Live) {
    Step "LIVE: DeepSeek 1-min RU director script -> work\director_live\ (no decks\ write)" {
        python scripts\director_script.py --topic "Большой взрыв: как из одной точки возникла Вселенная" --minutes 1 --lang ru --out work\director_live\big-bang-live.json --script-out work\director_live\big-bang-live-script.json --overwrite
    }
}

Write-Host ""
if ($failed.Count -eq 0) {
    Write-Host "ИТОГ: все проверки PASS" -ForegroundColor Green
    exit 0
} else {
    Write-Host ("ИТОГ: FAIL -> " + ($failed -join "; ")) -ForegroundColor Red
    exit 1
}
