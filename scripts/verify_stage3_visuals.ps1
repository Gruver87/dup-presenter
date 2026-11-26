# Скрипт проверки Этапа 3: visual sourcing (NASA, Wikimedia Commons, Internet Archive, Openverse), fail-closed.
#
# Запуск из корня dup-presenter:
#   powershell -ExecutionPolicy Bypass -File scripts\verify_stage3_visuals.ps1
# Полный живой прогон (нужна сеть и DeepSeek; пишет только в work\, public\visual\, out\; decks\ не трогает):
#   powershell -ExecutionPolicy Bypass -File scripts\verify_stage3_visuals.ps1 -Live
#
# Без -Live: офлайн тесты (сеть подменяется), валидация всех decks/ и компиляция.

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

Step "compile: archive_sources.py, visual_sourcing.py, director_script.py" {
    python -m py_compile scripts\archive_sources.py scripts\visual_sourcing.py scripts\director_script.py
}
Step "unit: visual sourcing (licences, providers, relevance, filters, fetch, apply)" {
    python -m unittest discover -s tests -p "test_visual_sourcing.py" -q
}
Step "unit: director script (incl. min_duration_sec and words/sec bounds)" {
    python -m unittest discover -s tests -p "test_director_script.py" -q
}
Step "regression: cinema_clip v2 (Stage 1)" {
    python -m unittest discover -s tests -p "test_cinema_clip.py" -q
}
Step "regression: all decks/ validate (min_duration_sec is optional)" {
    python -c "import json,sys,glob; sys.path.insert(0,'scripts'); from build_deck import resolve_director_preset, validate_deck; bad=[]
for p in sorted(glob.glob('decks/*.json')):
    try: validate_deck(resolve_director_preset(json.load(open(p, encoding='utf-8'))), check_assets=False)
    except Exception as ex: bad.append((p, str(ex)))
print('checked:', len(glob.glob('decks/*.json')), 'invalid:', bad)
sys.exit(1 if bad else 0)"
}

if ($Live) {
    Step "LIVE: search all four free archives (no keys) - 'nebula' image" {
        python scripts\visual_sourcing.py search --query "nebula" --kind image --limit 3
    }
    # Fail-closed chain: if generation fails, nothing downstream may run on a stale script file.
    $liveBroken = $false
    Step "LIVE: director script 1 min RU -> work\director_live\ (DeepSeek)" {
        python scripts\director_script.py --topic "Большой взрыв: как из одной точки возникла Вселенная" --minutes 1 --lang ru --out work\director_live\big-bang-live.json --script-out work\director_live\big-bang-live-script.json --overwrite
    }
    if ($failed -contains "LIVE: director script 1 min RU -> work\director_live\ (DeepSeek)") {
        $liveBroken = $true
        Write-Host "[STOP] director failed: downstream LIVE steps skipped (would otherwise reuse a stale script)" -ForegroundColor Yellow
    }
    $slug = "bolshoy-vzryv-kak-iz-odnoy-tochki-voznikla-vselenn-1min"
    if (-not $liveBroken) {
        Step "LIVE: plan (search + licence/relevance/resolution filter)" {
            python scripts\visual_sourcing.py plan --script work\director_live\big-bang-live-script.json
        }
        Step "LIVE: fetch (download, magic-byte check, real probe)" {
            python scripts\visual_sourcing.py fetch --plan work\visual_sources\$slug\plan.json
        }
        Step "LIVE: apply strict (cinema_clip must have media) -> work\director_live\big-bang-live-visual.json" {
            python scripts\visual_sourcing.py apply --plan work\visual_sources\$slug\plan.json --deck work\director_live\big-bang-live.json --out work\director_live\big-bang-live-visual.json --overwrite
        }
        Step "LIVE: draft render offline (Remotion + QA) of the wired deck" {
            python scripts\build_deck.py work\director_live\big-bang-live-visual.json --render --draft --offline-only
        }
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
