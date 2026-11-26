# Скрипт проверки Этапа 1: cinema_clip v2 (shots, crossfade, trim, slow-mo, audio_volume, grade, letterbox),
# slide.sfx[], --crf и --draft + Media QA.
#
# Запуск из корня dup-presenter:
#   powershell -ExecutionPolicy Bypass -File scripts\verify_stage1_cinema_v2.ps1
# С реальным тестовым рендером 8-сек черновика (--draft --offline-only, нужен public/cinema/bb_01_explosion.mp4):
#   powershell -ExecutionPolicy Bypass -File scripts\verify_stage1_cinema_v2.ps1 -SmokeRender

param([switch]$SmokeRender)

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

Step "unit: cinema_clip v2 + sfx + crf + draft (18 tests)" { python -m unittest discover -s tests -p "test_cinema_clip.py" -q }
Step "unit: deck_doctor + presenter_gates + universal_slides" {
    python -m unittest discover -s tests -p "test_deck_doctor.py" -q
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    python -m unittest discover -s tests -p "test_presenter_gates.py" -q
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    python -m unittest discover -s tests -p "test_universal_slides.py" -q
}
Step "typecheck: npx tsc --noEmit" { npx tsc --noEmit }
Step "lint: eslint src/types.ts src/UniversalSlides.tsx src/Composition.tsx" {
    npx eslint src/types.ts src/UniversalSlides.tsx src/Composition.tsx
}
Step "validate: all decks in decks/ (regression)" {
    python -c "import json,sys,glob; sys.path.insert(0,'scripts'); from build_deck import resolve_director_preset, validate_deck; bad=[]
for p in sorted(glob.glob('decks/*.json')):
    try: validate_deck(resolve_director_preset(json.load(open(p, encoding='utf-8'))))
    except Exception as ex: bad.append((p, str(ex)))
print('checked:', len(glob.glob('decks/*.json')), 'invalid:', bad)
sys.exit(1 if bad else 0)"
}

if ($SmokeRender) {
    Step "SMOKE RENDER: multi-shot cinema_clip v2 + native audio + SFX (--draft --offline-only)" {
        if (-not (Test-Path "public\cinema\bb_01_explosion.mp4") -or -not (Test-Path "public\cinema\bb_02_nebulae_stars.mp4")) {
            Write-Host "Missing public\cinema\bb_01_explosion.mp4 or bb_02_nebulae_stars.mp4" -ForegroundColor Yellow
            exit 1
        }
        python -c "import json; from pathlib import Path; deck={'slug':'stage1-smoke-v2','lang':'en','theme':'quantum_ledger','aspect':'16:9','brand':'DUP LABS','burn_captions':True,'caption_style':'bold','background':{'enabled':False},'music':{'enabled':False},'voice':{'engine':'kokoro_v1','lang':'en','speaker':'am_michael','rate':'100%'},'slides':[{'id':'s1','tag':'01','type':'cinema_clip','title':'Stage 1 Multi-Shot Smoke','voice_text':'From a single point of blazing energy, the first stars ignite across the dark void of space.','cinema':{'badge':'STAGE 1 · MULTI-SHOT','crossfade_frames':12,'grade':'cinema_warm','letterbox':True,'shots':[{'src':'cinema/bb_01_explosion.mp4','duration_sec':4.0,'start_sec':1.0,'end_sec':6.0,'playback_rate':0.85,'zoom':1.08,'audio_volume':0.22},{'src':'cinema/bb_02_nebulae_stars.mp4','start_sec':0.5,'end_sec':6.5,'zoom':1.1,'pan_x':-20}]},'sfx':[{'src':'sfx/transition_whoosh.wav','at_sec':3.6,'volume':0.45}]}]}; Path('work').mkdir(exist_ok=True); Path('work/stage1_smoke_deck.json').write_text(json.dumps(deck, indent=2), encoding='utf-8')"
        if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
        python scripts/build_deck.py work/stage1_smoke_deck.json --render --draft --offline-only
        if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
        Get-Content out\stage1-smoke-v2_draft_qa.json
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
