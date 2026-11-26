# Скрипт проверки: cinema_clip, режим deepseek, Idea Engine, валидация всех дек.
# Запуск из корня dup-presenter:
#   powershell -ExecutionPolicy Bypass -File scripts\verify_cinema_deepseek.ps1
# Живой вызов DeepSeek (расходует токены, нужен DUP_LLM_API_KEY или DEEPSEEK_API_KEY):
#   powershell -ExecutionPolicy Bypass -File scripts\verify_cinema_deepseek.ps1 -Live

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

Step "unit: cinema_clip validation (8 tests)" { python -m unittest discover -s tests -p "test_cinema_clip.py" -q }
Step "unit: deepseek/cloud mode, network mocked (8 tests)" { python -m unittest discover -s tests -p "test_deepseek_mode.py" -q }
Step "unit: idea_engine (9 tests)" { python -m unittest discover -s tests -p "test_idea_engine.py" -q }
Step "validate: big-bang-cinema-real.json (needs public/cinema clips)" {
    python -c "import json,sys; sys.path.insert(0,'scripts'); from build_deck import resolve_director_preset, validate_deck; validate_deck(resolve_director_preset(json.load(open('decks/big-bang-cinema-real.json', encoding='utf-8')))); print('deck OK')"
}
Step "validate: all decks in decks/ (regression)" {
    python -c "import json,sys,glob; sys.path.insert(0,'scripts'); from build_deck import resolve_director_preset, validate_deck; bad=[p for p in sorted(glob.glob('decks/*.json')) if not (lambda p: (validate_deck(resolve_director_preset(json.load(open(p, encoding='utf-8')))) is None))(p)]; print('invalid decks:', bad); sys.exit(1 if bad else 0)"
}
Step "typecheck: npx tsc --noEmit" { npx tsc --noEmit }

if ($Live) {
    Step "LIVE: DeepSeek count=3 -> validated decks" {
        python -c "import sys; sys.path.insert(0,'scripts'); from idea_engine import generate_ideas, idea_to_deck; from build_deck import validate_deck; res=generate_ideas('Большой взрыв и рождение Земли', lang='ru', mode='deepseek', count=3); ok=[validate_deck(idea_to_deck(i)) is None for i in res['ideas']]; print('source:', res['source'], 'ideas:', len(ok), 'valid:', sum(ok)); sys.exit(0 if all(ok) and len(ok)==3 else 1)"
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
