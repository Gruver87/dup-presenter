# Скрипт проверки Этапа 5 (частично): именованная библиотека SFX и разбиение src/Composition.tsx.
#
# Запуск из корня dup-presenter:
#   powershell -ExecutionPolicy Bypass -File scripts\verify_stage5_sfx_split.ps1
# Живой прогон (драфт-рендер ~1 мин; создаёт decks\stage5-check.json и удаляет его в конце):
#   powershell -ExecutionPolicy Bypass -File scripts\verify_stage5_sfx_split.ps1 -Live
#
# Покрывает @remotion/media как opt-in движок (media_engine: "media"; по умолчанию offthread).
# НЕ покрывает: @remotion/three (отложен: нужен WebGL-рендер и отдельная проверка кадров).

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

function Check($name, [bool]$ok) {
    if ($ok) { Write-Host "[PASS] $name" -ForegroundColor Green }
    else { Write-Host "[FAIL] $name" -ForegroundColor Red; $script:failed += $name }
}

Step "compile: sfx_library.py, build_deck.py" {
    python -m py_compile scripts\sfx_library.py scripts\build_deck.py
}
Step "unit: named SFX library (synthesis, manifest, name resolution, validation)" {
    python -m unittest discover -s tests -p "test_sfx_library.py" -q
}
Step "unit: media_engine field (opt-in engine; allowed values only)" {
    python -m unittest discover -s tests -p "test_media_engine.py" -q
}
Step "regression: cinema_clip validation (shares validate_deck)" {
    python -m unittest discover -s tests -p "test_cinema_clip.py" -q
}
Step "regression: storyboard gate (Stage 4, build_deck integration)" {
    python -m unittest discover -s tests -p "test_storyboard_gate.py" -q
}

$expectedModules = @("deckContext.ts", "cosmicBackdrop.tsx", "aurora3d.tsx", "primitives.tsx", "slides3d.tsx", "captions.tsx", "stockBackdrop.tsx")
$missingModules = @($expectedModules | Where-Object { -not (Test-Path (Join-Path "src\composition" $_)) })
Check "split: src/composition has the 7 modules (missing: $($missingModules -join ', '))" ($missingModules.Count -eq 0)
$mainLines = (Get-Content src\Composition.tsx -Encoding UTF8).Count
Check "split: src/Composition.tsx is the thin entry (< 400 lines, now $mainLines)" ($mainLines -lt 400)
Check "split: no heavy component is left in src/Composition.tsx (Slides/Cube3D/Captions)" (
    -not (Select-String -Path src\Composition.tsx -Pattern "^(export )?const (Cube3D|Hero3DSlide|CaptionOverlay|StockBackdrop) " -Quiet)
)

Step "tsc --noEmit (strict, noUnusedLocals) over the split project" {
    npx tsc --noEmit
}

if ($Live) {
    $slug = "stage5-check"
    $deck = "decks\$slug.json"
    try {
        Step "LIVE: draft render with named SFX cues (impact, ding)" {
            python -c "import json; d=json.load(open(r'work/director_live/big-bang-live-visual.json',encoding='utf-8')); d['slug']='$slug'; d['slides'][0]['sfx']=[{'name':'impact','at_sec':0.2,'volume':0.5},{'name':'ding','at_sec':3.0,'volume':0.4}]; json.dump(d, open(r'$deck','w',encoding='utf-8'), ensure_ascii=False, indent=2)"
            if ($LASTEXITCODE -ne 0) { exit 1 }
            python scripts\build_deck.py $deck --render --draft --offline-only
        }
        Step "LIVE: resolved deck carries library paths (no name left)" {
            python -c "import json,sys; d=json.load(open(r'src/generated/deck_resolved.json',encoding='utf-8')); cues=d['slides'][0].get('sfx',[]); got=[c.get('src') for c in cues]; print(got); sys.exit(0 if got==['sfx/library/impact.wav','sfx/library/ding.wav'] else 1)"
        }
        Step "LIVE: library files exist and manifest matches them" {
            python -c "import json,hashlib,pathlib,sys; m=json.load(open(r'public/sfx/library/manifest.json',encoding='utf-8')); bad=[i['name'] for i in m['items'] if hashlib.sha256(pathlib.Path('public/sfx/library/'+i['name']+'.wav').read_bytes()).hexdigest()!=i['sha256']]; print('items', len(m['items']), 'bad', bad); sys.exit(1 if bad else 0)"
        }
        Step "LIVE: Remotion still renders a frame of the split composition" {
            npx remotion still DupPresenter "out\stage5-check_frame.png" --frame=400
        }
        Check "LIVE: still PNG written" (Test-Path "out\stage5-check_frame.png")

        # @remotion/media engine on one real cinema mp4 clip. disallowFallbackToOffthreadVideo is set,
        # so a successful render means the media engine decoded the clip (no silent switch to OffthreadVideo).
        $mediaSlug = "stage5-media"
        $mediaDeck = "decks\$mediaSlug.json"
        Step "LIVE: @remotion/media engine draft of one cinema mp4 clip (fallback disabled)" {
            python -c "import json; d=json.load(open(r'decks/big-bang-cinema-real.json',encoding='utf-8')); d['slug']='$mediaSlug'; d['slides']=d['slides'][:1]; d['media_engine']='media'; json.dump(d, open(r'$mediaDeck','w',encoding='utf-8'), ensure_ascii=False, indent=2)"
            if ($LASTEXITCODE -ne 0) { exit 1 }
            python scripts\build_deck.py $mediaDeck --render --draft --offline-only
        }
        Step "LIVE: media-engine draft passes Media QA (out\$mediaSlug`_draft_qa.json ok=true)" {
            python -c "import json,sys; q=json.load(open(r'out/$mediaSlug`_draft_qa.json',encoding='utf-8')); print('qa ok:', q.get('ok'), 'hard_fails:', q.get('hard_fails')); sys.exit(0 if q.get('ok') is True else 1)"
        }
    } finally {
        Remove-Item $deck -Force -ErrorAction SilentlyContinue
        Remove-Item "decks\stage5-media.json" -Force -ErrorAction SilentlyContinue
        Remove-Item "out\stage5-check*" -Force -ErrorAction SilentlyContinue
        Remove-Item "out\stage5-media*" -Force -ErrorAction SilentlyContinue
        Remove-Item "work\stage5-check" -Recurse -Force -ErrorAction SilentlyContinue
        Remove-Item "work\stage5-media" -Recurse -Force -ErrorAction SilentlyContinue
        Write-Host "[cleanup] removed stage5-check / stage5-media decks, out and work artifacts" -ForegroundColor DarkGray
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
