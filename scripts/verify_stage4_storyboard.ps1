# Скрипт проверки Этапа 4: гейт согласования раскадровки (draft -> storyboard -> approve -> master MP4), fail-closed.
#
# Запуск из корня dup-presenter:
#   powershell -ExecutionPolicy Bypass -File scripts\verify_stage4_storyboard.ps1
# Живой прогон (драфт-рендер ~2 мин, локальная консоль на 127.0.0.1:8791; decks\ трогает только временно,
# stage4-check.json удаляется в конце):
#   powershell -ExecutionPolicy Bypass -File scripts\verify_stage4_storyboard.ps1 -Live
#
# Без -Live: компиляция, unit-тесты гейта, регрессии Этапов 1-3, синтаксис inline JS консоли.

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

function StepExpect($name, [int]$want, [scriptblock]$cmd) {
    Write-Host ""
    Write-Host "=== $name (expect exit $want) ===" -ForegroundColor Cyan
    & $cmd
    $rc = $LASTEXITCODE
    if ($rc -eq $want) {
        Write-Host "[PASS] $name (exit $rc)" -ForegroundColor Green
    } else {
        Write-Host "[FAIL] $name (exit $rc, expected $want)" -ForegroundColor Red
        $script:failed += $name
    }
}

function Check($name, [bool]$ok) {
    if ($ok) {
        Write-Host "[PASS] $name" -ForegroundColor Green
    } else {
        Write-Host "[FAIL] $name" -ForegroundColor Red
        $script:failed += $name
    }
}

# ------------------------------------------------------------------ offline
Step "compile: storyboard_gate, build_deck, make_project_deck, video_pack, console_server" {
    python -m py_compile scripts\storyboard_gate.py scripts\build_deck.py scripts\make_project_deck.py scripts\video_pack.py scripts\console_server.py
}
Step "unit: storyboard approval gate (17 fail-closed cases)" {
    python -m unittest discover -s tests -p "test_storyboard_gate.py" -q
}
Step "regression: visual sourcing (Stage 3)" {
    python -m unittest discover -s tests -p "test_visual_sourcing.py" -q
}
Step "regression: director script (Stage 2)" {
    python -m unittest discover -s tests -p "test_director_script.py" -q
}
Step "regression: cinema_clip v2 (Stage 1)" {
    python -m unittest discover -s tests -p "test_cinema_clip.py" -q
}
Step "extract inline JS of console_ui.html" {
    python -c "import re,pathlib; h=pathlib.Path('scripts/console_ui.html').read_text(encoding='utf-8'); pathlib.Path('work').mkdir(exist_ok=True); pathlib.Path('work/console_inline_check.js').write_text(';\n'.join(re.findall(r'<script>([\s\S]*?)</script>', h)), encoding='utf-8')"
}
Step "JS syntax: console_ui.html inline script (node --check)" {
    node --check work\console_inline_check.js
}

if ($Live) {
    $slug = "stage4-check"
    $deckFile = "decks\$slug.json"
    $backup = "work\$slug\deck_backup.json"
    $srcDeck = "work\director_live\big-bang-live-visual.json"
    $srcPlan = "work\visual_sources\bolshoy-vzryv-kak-iz-odnoy-tochki-voznikla-vselenn-1min\plan.json"
    $consolePort = 8791
    $proc = $null

    if (-not (Test-Path $srcDeck)) {
        Write-Host "[FAIL] LIVE source deck missing: $srcDeck (run verify_stage3_visuals.ps1 -Live first)" -ForegroundColor Red
        $failed += "LIVE: source deck missing"
    } else {
        New-Item -ItemType Directory -Force "work\$slug" | Out-Null
        New-Item -ItemType Directory -Force "work\visual_sources\$slug" | Out-Null
        if (Test-Path $srcPlan) { Copy-Item $srcPlan "work\visual_sources\$slug\plan.json" -Force }
        # Copy the Stage 3 wired deck under a dedicated slug (UTF-8 without BOM, via Python).
        python -c "import json; d=json.load(open(r'$srcDeck',encoding='utf-8')); d['slug']='$slug'; json.dump(d, open(r'$deckFile','w',encoding='utf-8'), ensure_ascii=False, indent=2)"
        Copy-Item $deckFile $backup -Force
        try {
            Step "LIVE: draft render (writes out\$slug`_draft.mp4 and binds it to the deck sha256)" {
                python scripts\build_deck.py $deckFile --render --draft --offline-only
            }
            Check "LIVE: draft record exists (storyboard/draft_meta.json)" (Test-Path "work\$slug\storyboard\draft_meta.json")

            StepExpect "LIVE: master render refused before approval (exit 2, no master MP4)" 2 {
                python scripts\build_deck.py $deckFile --render --require-storyboard --offline-only
            }
            Check "LIVE: no master MP4 was produced by the refused render" (-not (Test-Path "out\$slug.mp4"))

            Step "LIVE: storyboard build (one frame per slide from the draft)" {
                python scripts\storyboard_gate.py build $slug
            }
            Step "LIVE: storyboard covers every deck slide" {
                python -c "import json,sys; i=json.load(open(r'work/$slug/storyboard/index.json',encoding='utf-8')); d=json.load(open(r'$deckFile',encoding='utf-8')); n=len(i['slides']); m=len(d['slides']); print('storyboard slides', n, 'deck slides', m); sys.exit(0 if n==m and n>0 else 1)"
            }
            StepExpect "LIVE: gate check refuses before approval" 2 {
                python scripts\storyboard_gate.py check $slug
            }
            Step "LIVE: approve storyboard (binds deck sha256 + draft sha256)" {
                python scripts\storyboard_gate.py approve $slug
            }
            Step "LIVE: gate check allows master after approval" {
                python scripts\storyboard_gate.py check $slug
            }

            # Deck edit must invalidate the approval; restoring the identical content must re-validate it.
            python -c "import json; d=json.load(open(r'$deckFile',encoding='utf-8')); d['slides'][0]['title']=d['slides'][0]['title']+' (edit)'; json.dump(d, open(r'$deckFile','w',encoding='utf-8'), ensure_ascii=False, indent=2)"
            StepExpect "LIVE: deck edit invalidates approval (gate refuses)" 2 {
                python scripts\storyboard_gate.py check $slug
            }
            Copy-Item $backup $deckFile -Force
            Step "LIVE: restored identical deck is approved again (content-hash binding)" {
                python scripts\storyboard_gate.py check $slug
            }

            # Console server: real HTTP probes of the gate endpoints (no master render is started).
            $proc = Start-Process -FilePath python -ArgumentList "scripts\console_server.py --port $consolePort --no-auto-ollama" -PassThru -WindowStyle Hidden -RedirectStandardOutput "work\stage4_console.log" -RedirectStandardError "work\stage4_console.err.log"
            $base = "http://127.0.0.1:$consolePort"
            $ready = $false
            for ($i = 0; $i -lt 60 -and -not $ready; $i++) {
                Start-Sleep -Milliseconds 500
                try { $null = Invoke-RestMethod "$base/api/live"; $ready = $true } catch { }
            }
            Check "CONSOLE: server answers /api/live on port $consolePort" $ready

            if ($ready) {
                $st = Invoke-RestMethod "$base/api/storyboard?slug=$slug"
                Check "CONSOLE: GET /api/storyboard reports can_master=true and frames" ($st.status.can_master -eq $true -and $st.index.slides.Count -gt 0)

                $frame = Invoke-WebRequest "$base/storyboard/$slug/a1s01.jpg" -UseBasicParsing
                Check "CONSOLE: frame served as image/jpeg" ($frame.Headers["Content-Type"] -eq "image/jpeg" -and $frame.RawContentLength -gt 1024)

                try { $null = Invoke-WebRequest "$base/storyboard/$slug/..%2Fdeck_backup.json" -UseBasicParsing; $trav = 200 } catch { $trav = $_.Exception.Response.StatusCode.value__ }
                Check "CONSOLE: path traversal in frame URL refused (404)" ($trav -eq 404)

                $body = @{ slug = $slug } | ConvertTo-Json
                Invoke-RestMethod -Method Post "$base/api/storyboard/revoke" -ContentType "application/json" -Body $body | Out-Null
                $masterBody = @{ slug = $slug; draft = $false } | ConvertTo-Json
                try { $null = Invoke-WebRequest -Method Post "$base/api/render" -ContentType "application/json" -Body $masterBody -UseBasicParsing; $code = 202 } catch { $code = $_.Exception.Response.StatusCode.value__ }
                Check "CONSOLE: master /api/render refused after revoke (409, no job started)" ($code -eq 409)

                $onlySlide = @{ slug = $slug; draft = $false; only_slide = "a1s01" } | ConvertTo-Json
                try { $null = Invoke-WebRequest -Method Post "$base/api/render" -ContentType "application/json" -Body $onlySlide -UseBasicParsing; $code2 = 202 } catch { $code2 = $_.Exception.Response.StatusCode.value__ }
                Check "CONSOLE: master single-slide render refused (400)" ($code2 -eq 400)

                Invoke-RestMethod -Method Post "$base/api/storyboard/approve" -ContentType "application/json" -Body $body | Out-Null
                $st2 = Invoke-RestMethod "$base/api/storyboard?slug=$slug"
                Check "CONSOLE: approve re-enables master gate (can_master=true)" ($st2.status.can_master -eq $true)
            }
        } finally {
            if ($proc -and -not $proc.HasExited) { Stop-Process -Id $proc.Id -Force }
            Remove-Item $deckFile -Force -ErrorAction SilentlyContinue
            Remove-Item "work\$slug" -Recurse -Force -ErrorAction SilentlyContinue
            Remove-Item "work\visual_sources\$slug" -Recurse -Force -ErrorAction SilentlyContinue
            Remove-Item "out\$slug*" -Force -ErrorAction SilentlyContinue
            Write-Host "[cleanup] removed decks\$slug.json, work\$slug, out\$slug*" -ForegroundColor DarkGray
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
