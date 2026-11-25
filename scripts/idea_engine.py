"""DUP Presenter — Built-in Idea Engine (fail-closed, offline templates + LLM).

Generates structured, multi-angle video concepts (hook, genre, format, theme,
caption style, and scene blueprint) for diverse video types, and converts any
selected idea into a validated presentation deck JSON ready for `build_deck.py`.

Honesty invariant:
  - `mode="template"` produces deterministic offline ideas and labels `source="template"`.
  - `mode="ollama"` / `mode="cloud"` queries the configured LLM and fails closed
    (`IdeaEngineError`) if the provider is unreachable or returns invalid JSON.
    It NEVER silently substitutes template ideas while claiming LLM output.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from build_deck import ALLOWED_CAPTION_STYLES as CAPTION_STYLES, ASPECT_DIMS, validate_deck  # noqa: E402
from theme_catalog import THEME_IDS  # noqa: E402

DECKS_DIR = ROOT / "decks"
DEFAULT_OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434")
DEFAULT_OLLAMA_MODEL = os.environ.get("DUP_IDEA_MODEL", "qwen2.5:14b")
SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{1,62}$")

GENRE_CATALOG: list[dict[str, Any]] = [
    {
        "id": "tech_explainer",
        "label_ru": "Разбор технологии / архитектуры",
        "label_en": "Tech / Architecture Explainer",
        "default_aspect": "16:9",
        "default_theme": "quantum_ledger",
        "default_caption_style": "karaoke",
        "duration_hint_sec": 150,
    },
    {
        "id": "versus_battle",
        "label_ru": "Сравнение A vs B",
        "label_en": "Versus Comparison (A vs B)",
        "default_aspect": "16:9",
        "default_theme": "neon_cyber",
        "default_caption_style": "karaoke",
        "duration_hint_sec": 120,
    },
    {
        "id": "short_60s",
        "label_ru": "Динамичный Short / Reels (9:16)",
        "label_en": "Fast 60s Short / Reels (9:16)",
        "default_aspect": "9:16",
        "default_theme": "cyber_magenta",
        "default_caption_style": "bold",
        "duration_hint_sec": 55,
    },
    {
        "id": "news_digest",
        "label_ru": "Новостной / рыночный дайджест",
        "label_en": "News / Market Digest",
        "default_aspect": "16:9",
        "default_theme": "cosmic_radar",
        "default_caption_style": "karaoke",
        "duration_hint_sec": 110,
    },
    {
        "id": "investor_pitch",
        "label_ru": "Питч продукта / проекта",
        "label_en": "Product / Investor Pitch",
        "default_aspect": "16:9",
        "default_theme": "deep_ocean",
        "default_caption_style": "box",
        "duration_hint_sec": 160,
    },
    {
        "id": "case_study",
        "label_ru": "Кейс-стади (проблема → решение)",
        "label_en": "Case Study (Problem -> Result)",
        "default_aspect": "16:9",
        "default_theme": "aurora_purple",
        "default_caption_style": "karaoke",
        "duration_hint_sec": 135,
    },
    {
        "id": "tutorial",
        "label_ru": "Пошаговый гайд / туториал",
        "label_en": "Step-by-Step Tutorial",
        "default_aspect": "16:9",
        "default_theme": "terminal_green",
        "default_caption_style": "karaoke",
        "duration_hint_sec": 140,
    },
]

GENRE_MAP: dict[str, dict[str, Any]] = {g["id"]: g for g in GENRE_CATALOG}
SUPPORTED_IDEA_SLIDE_TYPES: frozenset[str] = frozenset(
    {
        "hero_3d",
        "kpi",
        "timeline",
        "quote",
        "terminal",
        "outro_3d",
        "versus_split",
        "chart_story",
        "stat_burst",
        "broll_cinematic",
    }
)


class IdeaEngineError(RuntimeError):
    """Fail-closed error raised on invalid input, provider failure, or bad schema."""


class IdeaDeckExistsError(FileExistsError):
    """Raised when attempting to overwrite an existing deck without overwrite=True."""


def slugify_topic(text: str, fallback: str = "new-video") -> str:
    """Create a safe lowercase ASCII slug from an arbitrary topic string."""
    translit = {
        "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ё": "e",
        "ж": "zh", "з": "z", "и": "i", "й": "y", "к": "k", "л": "l", "м": "m",
        "н": "n", "о": "o", "п": "p", "р": "r", "с": "s", "т": "t", "у": "u",
        "ф": "f", "х": "h", "ц": "ts", "ч": "ch", "ш": "sh", "щ": "sch",
        "ъ": "", "ы": "y", "ь": "", "э": "e", "ю": "yu", "я": "ya",
    }
    buf = []
    for ch in str(text or "").lower():
        if ch in translit:
            buf.append(translit[ch])
        elif ch.isascii() and (ch.isalnum() or ch in "-_"):
            buf.append(ch)
        else:
            buf.append("-")
    slug = re.sub(r"-{2,}", "-", "".join(buf)).strip("-_")[:54]
    if len(slug) < 2 or not SLUG_RE.match(slug):
        return fallback
    return slug


def _angle_blueprints(topic: str, lang: str, genre_filter: str) -> list[dict[str, Any]]:
    """Deterministic multi-angle blueprints used by offline template mode."""
    t = topic.strip()
    is_en = lang == "en"

    all_angles: list[dict[str, Any]] = [
        {
            "genre": "tech_explainer",
            "angle": "Inside the Engine" if is_en else "Взгляд изнутри механизма",
            "title": f"How {t} Actually Works" if is_en else f"Как {t} работает изнутри",
            "hook": (
                f"Most people only see the surface of {t} — in 2 minutes, let us trace what really happens underneath."
                if is_en
                else f"Большинство видит только фасад {t} — за две минуты разберём, как всё устроено внутри."
            ),
            "theme": "quantum_ledger",
            "aspect": "16:9",
            "caption_style": "karaoke",
            "duration_hint_sec": 145,
            "slides": [
                {
                    "type": "hero_3d",
                    "tag": "EXPLAINER" if is_en else "РАЗБОР",
                    "title": f"{t}: Inside the System" if is_en else f"{t}: взгляд изнутри",
                    "subtitle": "Architecture, key guarantees, and real workflow" if is_en else "Архитектура, ключевые гарантии и реальный поток",
                    "voice_text": (
                        f"Most people only see the surface of {t}. Let us walk through how the system actually works step by step."
                        if is_en
                        else f"Большинство видит только фасад {t}. Разберём шаг за шагом, как система работает на самом деле."
                    ),
                },
                {
                    "type": "timeline",
                    "tag": "PIPELINE" if is_en else "ПАЙПЛАЙН",
                    "title": "Four Core Stages" if is_en else "Четыре ключевых этапа",
                    "subtitle": "From input boundary to verified output" if is_en else "От входной границы до проверенного результата",
                    "voice_text": (
                        f"Every request in {t} passes four clear stages: validation at the edge, deterministic processing, verification, and durable output."
                        if is_en
                        else f"Каждый запрос в {t} проходит четыре чётких этапа: проверку на входе, детерминированную обработку, верификацию и фиксацию результата."
                    ),
                    "steps": [
                        {"title": "Input Guard" if is_en else "Входной фильтр", "desc": "Reject malformed input fail-closed." if is_en else "Отсекаем некорректные данные на границе."},
                        {"title": "Core Engine" if is_en else "Рабочее ядро", "desc": "Deterministic execution of core logic." if is_en else "Детерминированное выполнение основной логики."},
                        {"title": "Verification" if is_en else "Верификация", "desc": "Automated checks before finalizing." if is_en else "Автоматическая проверка перед фиксацией."},
                        {"title": "Output" if is_en else "Результат", "desc": "Reproducible artifact ready for inspection." if is_en else "Воспроизводимый результат для проверки."},
                    ],
                },
                {
                    "type": "kpi",
                    "tag": "METRICS" if is_en else "МЕТРИКИ",
                    "title": "What Actually Matters" if is_en else "Что действительно важно",
                    "subtitle": "Replace placeholder metrics with verified measurements" if is_en else "Замените эти ориентиры на ваши измеренные цифры",
                    "voice_text": (
                        "Good engineering is measured by verifiable guarantees: zero silent failures, clear boundaries, and repeatable builds."
                        if is_en
                        else "Хорошая инженерия измеряется проверяемыми гарантиями: ноль тихих сбоев, чёткие границы и повторяемость."
                    ),
                    "kpis": [
                        {"value": "4", "label": "isolated pipeline stages" if is_en else "изолированных этапа пайплайна"},
                        {"value": "0", "label": "silent fallbacks allowed" if is_en else "тихих обходов при ошибках"},
                        {"value": "100%", "label": "reproducible workflow" if is_en else "воспроизводимый процесс"},
                    ],
                },
                {
                    "type": "quote",
                    "tag": "PRINCIPLE" if is_en else "ПРИНЦИП",
                    "title": (
                        "Clarity beats hype: if you can trace every step, you can trust the system."
                        if is_en
                        else "Ясность сильнее хайпа: когда виден каждый шаг, системе можно доверять."
                    ),
                    "subtitle": f"{t} · engineering summary" if is_en else f"{t} · инженерный вывод",
                    "voice_text": (
                        "Clarity always beats hype. When every stage is observable, the whole system becomes trustworthy."
                        if is_en
                        else "Ясность всегда сильнее хайпа. Когда каждый шаг прозрачен, системе можно доверять."
                    ),
                },
                {
                    "type": "outro_3d",
                    "tag": "SUMMARY" if is_en else "ФИНАЛ",
                    "title": f"Explore {t}" if is_en else f"Изучите {t}",
                    "subtitle": "Reproducible presentation built with DUP Presenter" if is_en else "Воспроизводимая презентация собрана в DUP Presenter",
                    "voice_text": (
                        f"That is the core mental model behind {t}. Customize the slides with your verified metrics and render."
                        if is_en
                        else f"Вот рабочая модель {t}. Подставьте ваши проверенные цифры и скриншоты и запускайте рендер."
                    ),
                },
            ],
        },
        {
            "genre": "short_60s",
            "angle": "60-Second Hook" if is_en else "60-секундный Short с хуком",
            "title": f"{t} in 60 Seconds" if is_en else f"{t} за 60 секунд",
            "hook": (
                f"Stop scrolling: here is the one thing about {t} that changes how you build."
                if is_en
                else f"Не пролистывай: одна деталь про {t}, которая полностью меняет подход."
            ),
            "theme": "cyber_magenta",
            "aspect": "9:16",
            "caption_style": "bold",
            "duration_hint_sec": 55,
            "slides": [
                {
                    "type": "hero_3d",
                    "tag": "60 SEC" if is_en else "60 СЕК",
                    "title": f"{t} in 60s" if is_en else f"{t} за 60 сек",
                    "subtitle": "One sharp idea, zero fluff" if is_en else "Одна сильная мысль, ноль воды",
                    "voice_text": (
                        f"Stop scrolling. Here is the single clearest way to understand {t} in under a minute."
                        if is_en
                        else f"Не пролистывай. Вот самый понятный способ разобраться в {t} меньше чем за минуту."
                    ),
                },
                {
                    "type": "kpi",
                    "tag": "KEY NUMBERS" if is_en else "ГЛАВНОЕ",
                    "title": "Three Takeaways" if is_en else "Три факта",
                    "subtitle": "Fast vertical digest" if is_en else "Короткий вертикальный разбор",
                    "voice_text": (
                        f"Three things matter in {t}: speed on the hot path, strict validation at the edge, and proof over promises."
                        if is_en
                        else f"В {t} решают три вещи: скорость ядра, жёсткая проверка на входе и факты вместо обещаний."
                    ),
                    "kpis": [
                        {"value": "3x", "label": "clearer workflow" if is_en else "понятнее процесс"},
                        {"value": "0", "label": "hidden magic" if is_en else "скрытой магии"},
                    ],
                },
                {
                    "type": "quote",
                    "tag": "TAKEAWAY" if is_en else "ВЫВОД",
                    "title": (
                        f"Understand the core of {t} once, and every detail clicks into place."
                        if is_en
                        else f"Пойми ядро {t} один раз — и все детали встанут на свои места."
                    ),
                    "subtitle": "Save this breakdown" if is_en else "Сохрани этот разбор",
                    "voice_text": (
                        f"Understand the core of {t} once, and every surrounding detail clicks into place."
                        if is_en
                        else f"Пойми ядро {t} один раз — и все остальные детали сразу встанут на свои места."
                    ),
                },
                {
                    "type": "outro_3d",
                    "tag": "NEXT" if is_en else "ДАЛЬШЕ",
                    "title": "Want the Full Deep Dive?" if is_en else "Нужен полный разбор?",
                    "subtitle": "Full 16:9 breakdown available" if is_en else "Полная версия 16:9 уже готова",
                    "voice_text": (
                        f"Follow for the full technical breakdown of {t}."
                        if is_en
                        else f"Подписывайся, чтобы не пропустить полный технический разбор {t}."
                    ),
                },
            ],
        },
        {
            "genre": "versus_battle",
            "angle": "Old Way vs New Way" if is_en else "Старый подход против нового",
            "title": f"{t}: Old Way vs Modern Approach" if is_en else f"{t}: старый подход против нового",
            "hook": (
                f"Why do classic setups fail on {t}, while modern architectures stay clean?"
                if is_en
                else f"Почему старый подход ломается в {t}, а современная схема работает без сбоев?"
            ),
            "theme": "neon_cyber",
            "aspect": "16:9",
            "caption_style": "karaoke",
            "duration_hint_sec": 120,
            "slides": [
                {
                    "type": "hero_3d",
                    "tag": "VERSUS" if is_en else "СРАВНЕНИЕ",
                    "title": f"{t}: A vs B" if is_en else f"{t}: подход A против B",
                    "subtitle": "Side-by-side breakdown of trade-offs" if is_en else "Честное сравнение плюсов и рисков",
                    "voice_text": (
                        f"Let us compare the legacy way and the modern way to approach {t}, side by side."
                        if is_en
                        else f"Сравним старый и современный подход к {t} лицом к лицу — без маркетинговых лозунгов."
                    ),
                },
                {
                    "type": "timeline",
                    "tag": "COMPARISON" if is_en else "КРИТЕРИИ",
                    "title": "Three Battlegrounds" if is_en else "Три критерия сравнения",
                    "subtitle": "Reliability, speed, and operational clarity" if is_en else "Надёжность, скорость и прозрачность работы",
                    "voice_text": (
                        "We evaluate both options across three real criteria: failure handling, execution speed, and auditability."
                        if is_en
                        else "Оценим оба варианта по трём реальным критериям: реакция на сбой, скорость и прозрачность проверки."
                    ),
                    "steps": [
                        {"title": "Failure Mode" if is_en else "Реакция на сбой", "desc": "Silent fallback vs fail-closed refusal." if is_en else "Тихий сбой против честного fail-closed отказа."},
                        {"title": "Performance" if is_en else "Скорость", "desc": "Ad-hoc scripts vs dedicated hot path." if is_en else "Ручная склейка против быстрого ядра."},
                        {"title": "Auditability" if is_en else "Проверяемость", "desc": "Guesswork vs deterministic artifacts." if is_en else "Догадки против проверяемых артефактов."},
                    ],
                },
                {
                    "type": "quote",
                    "tag": "VERDICT" if is_en else "ВЕРДИКТ",
                    "title": (
                        "Pick the architecture that fails loudly in testing rather than silently in production."
                        if is_en
                        else "Выбирайте архитектуру, которая громко падает на тесте, а не тихо врёт в проде."
                    ),
                    "subtitle": f"{t} · comparison verdict" if is_en else f"{t} · итог сравнения",
                    "voice_text": (
                        "Always pick the architecture that fails loudly during checks instead of silently drifting in production."
                        if is_en
                        else "Всегда выбирайте систему, которая громко останавливается на проверке, а не тихо врёт в работе."
                    ),
                },
                {
                    "type": "outro_3d",
                    "tag": "OUTRO" if is_en else "ИТОГ",
                    "title": f"Choose Clearly on {t}" if is_en else f"Выбирайте осознанно в {t}",
                    "subtitle": "Edit the comparison criteria in JSON or Console" if is_en else "Настройте критерии сравнения в JSON или консоли",
                    "voice_text": (
                        "Drop your own benchmark numbers into this deck and render your side-by-side comparison."
                        if is_en
                        else "Подставьте свои замеры в этот шаблон и соберите честное сравнение за пару минут."
                    ),
                },
            ],
        },
        {
            "genre": "investor_pitch",
            "angle": "Problem -> Proof -> Vision" if is_en else "Проблема → Доказательство → План",
            "title": f"{t}: Executive Pitch Deck" if is_en else f"{t}: питч-презентация",
            "hook": (
                f"Here is the problem {t} solves, what is already proven today, and what comes next."
                if is_en
                else f"Какую реальную проблему решает {t}, что уже доказано сегодня и что будет дальше."
            ),
            "theme": "deep_ocean",
            "aspect": "16:9",
            "caption_style": "box",
            "duration_hint_sec": 150,
            "slides": [
                {
                    "type": "hero_3d",
                    "tag": "PITCH" if is_en else "ПИТЧ",
                    "title": t,
                    "subtitle": "Evidence-first product overview" if is_en else "Обзор продукта с опорой на факты",
                    "voice_text": (
                        f"Welcome to the executive overview of {t}: the problem we solve, what is verified today, and the roadmap ahead."
                        if is_en
                        else f"Добро пожаловать в обзор {t}: какую проблему мы решаем, что уже подтверждено сегодня и какой план впереди."
                    ),
                },
                {
                    "type": "kpi",
                    "tag": "TRACTION" if is_en else "ФАКТЫ",
                    "title": "Verified Today" if is_en else "Подтверждено сегодня",
                    "subtitle": "Fill with audited or disk-backed numbers only" if is_en else "Заполните только подтверждёнными метриками",
                    "voice_text": (
                        "Start with honest numbers backed by artifacts on disk, clearly separated from future milestones."
                        if is_en
                        else "Начинаем с честных цифр, подтверждённых артефактами, чётко отделяя сделанное от планов."
                    ),
                    "kpis": [
                        {"value": "v1", "label": "working prototype / pipeline" if is_en else "рабочий контур на диске"},
                        {"value": "0", "label": "unverified claims" if is_en else "неподтверждённых обещаний"},
                        {"value": "24/7", "label": "automated verification target" if is_en else "автоматическая проверка"},
                    ],
                },
                {
                    "type": "timeline",
                    "tag": "ROADMAP" if is_en else "ДОРОЖНАЯ КАРТА",
                    "title": "Execution Roadmap" if is_en else "План развития",
                    "subtitle": "Ordered milestones with explicit gates" if is_en else "Последовательные этапы с явными воротами качества",
                    "voice_text": (
                        "Our roadmap moves in strict phases: core stability first, verification and external review second, then controlled scale."
                        if is_en
                        else "Развитие идёт строго по фазам: сначала надёжность ядра, затем проверки и аудит, и только потом масштабирование."
                    ),
                    "steps": [
                        {"title": "Phase 1 · Core" if is_en else "Фаза 1 · Ядро", "desc": "Solidify core workflow and tests." if is_en else "Закрепить ядро и автотесты."},
                        {"title": "Phase 2 · Verify" if is_en else "Фаза 2 · Проверка", "desc": "Independent review and stress runs." if is_en else "Независимая проверка и нагрузочные прогоны."},
                        {"title": "Phase 3 · Scale" if is_en else "Фаза 3 · Рост", "desc": "Broader rollout with monitoring." if is_en else "Расширение с полным мониторингом."},
                    ],
                },
                {
                    "type": "outro_3d",
                    "tag": "CONTACT" if is_en else "КОНТАКТЫ",
                    "title": f"{t} · Next Steps" if is_en else f"{t} · следующие шаги",
                    "subtitle": "Evidence pack and code available for inspection" if is_en else "Код и материалы открыты для проверки",
                    "voice_text": (
                        f"Thank you for watching this brief on {t}. All supporting materials are ready for direct inspection."
                        if is_en
                        else f"Спасибо за внимание к обзору {t}. Все подтверждающие материалы готовы к прямой проверке."
                    ),
                },
            ],
        },
        {
            "genre": "tutorial",
            "angle": "Hands-On Walkthrough" if is_en else "Пошаговая практика",
            "title": f"{t}: Hands-On Guide" if is_en else f"{t}: пошаговый гайд",
            "hook": (
                f"Follow these four commands to go from zero to a working {t} setup."
                if is_en
                else f"Пройдём четыре понятных шага от чистого старта до рабочего результата в {t}."
            ),
            "theme": "terminal_green",
            "aspect": "16:9",
            "caption_style": "karaoke",
            "duration_hint_sec": 130,
            "slides": [
                {
                    "type": "hero_3d",
                    "tag": "GUIDE" if is_en else "ГАЙД",
                    "title": f"{t} Tutorial" if is_en else f"Гайд: {t}",
                    "subtitle": "Practical step-by-step walkthrough" if is_en else "Практическое руководство шаг за шагом",
                    "voice_text": (
                        f"In this practical walkthrough, we will set up and verify {t} from scratch in four clear steps."
                        if is_en
                        else f"В этом практическом руководстве мы соберём и проверим {t} с нуля за четыре понятных шага."
                    ),
                },
                {
                    "type": "timeline",
                    "tag": "STEPS" if is_en else "ШАГИ",
                    "title": "Four-Step Setup" if is_en else "Четыре шага запуска",
                    "subtitle": "Prepare, configure, run, and verify" if is_en else "Подготовка, настройка, запуск и проверка",
                    "voice_text": (
                        "First install prerequisites, then configure parameters, run the build, and finally inspect the verification gate."
                        if is_en
                        else "Сначала ставим зависимости, затем задаём конфиг, запускаем сборку и проверяем итоговый гейт качества."
                    ),
                    "steps": [
                        {"title": "1. Setup" if is_en else "1. Установка", "desc": "Prepare clean local environment." if is_en else "Подготовьте чистое окружение."},
                        {"title": "2. Configure" if is_en else "2. Настройка", "desc": "Set explicit parameters, no hidden defaults." if is_en else "Задайте явные параметры без скрытых умолчаний."},
                        {"title": "3. Run" if is_en else "3. Запуск", "desc": "Execute the workflow end to end." if is_en else "Выполните полный прогон."},
                        {"title": "4. Verify" if is_en else "4. Проверка", "desc": "Confirm green checks and logs." if is_en else "Убедитесь в зелёных проверках и логах."},
                    ],
                },
                {
                    "type": "terminal",
                    "tag": "CLI" if is_en else "ТЕРМИНАЛ",
                    "title": "Run & Verify" if is_en else "Запуск и проверка",
                    "subtitle": "Example command sequence" if is_en else "Пример последовательности команд",
                    "voice_text": (
                        "Run the validation command first, then build and inspect the output status to be certain everything passed."
                        if is_en
                        else "Сначала запускаем проверку, затем сборку и смотрим итоговый статус, чтобы быть уверенными в результате."
                    ),
                    "lines": [
                        {"text": f"$ # Step 1: validate {slugify_topic(t)}", "color": "#94a3b8"},
                        {"text": "$ python scripts/deck_doctor.py decks/example.json", "color": "#22d3ee"},
                        {"text": "[OK] Schema valid · 0 errors", "color": "#10ff88"},
                        {"text": "$ python scripts/build_deck.py decks/example.json --render", "color": "#22d3ee"},
                        {"text": "[qa] PASS | 1920x1080 | LUFS=-16.0 | hard_fails=0", "color": "#10ff88"},
                    ],
                },
                {
                    "type": "outro_3d",
                    "tag": "DONE" if is_en else "ГОТОВО",
                    "title": "Ready to Build" if is_en else "Готово к запуску",
                    "subtitle": "Swap in your exact commands and render" if is_en else "Подставьте свои команды и запускайте рендер",
                    "voice_text": (
                        f"You now have a repeatable tutorial structure for {t}. Replace the terminal lines with your own commands."
                        if is_en
                        else f"У вас готов шаблон гайда по {t}. Замените строки терминала своими командами и рендерите видео."
                    ),
                },
            ],
        },
        {
            "genre": "news_digest",
            "angle": "Weekly Digest" if is_en else "Дайджест главных событий",
            "title": f"{t}: Key Signals Digest" if is_en else f"{t}: дайджест главных сигналов",
            "hook": (
                f"Three key shifts in {t} you should know today — without the noise."
                if is_en
                else f"Три главных сдвига по теме {t}, о которых важно знать сегодня — без лишнего шума."
            ),
            "theme": "cosmic_radar",
            "aspect": "16:9",
            "caption_style": "karaoke",
            "duration_hint_sec": 110,
            "slides": [
                {
                    "type": "hero_3d",
                    "tag": "DIGEST" if is_en else "ДАЙДЖЕСТ",
                    "title": f"{t} Digest" if is_en else f"Дайджест: {t}",
                    "subtitle": "Signal over noise · structured summary" if is_en else "Сигнал вместо шума · структурная сводка",
                    "voice_text": (
                        f"Welcome to the structured digest on {t}. Let us focus strictly on verified signals and skip the noise."
                        if is_en
                        else f"Добро пожаловать в дайджест по теме {t}. Смотрим только на подтверждённые сигналы и убираем шум."
                    ),
                },
                {
                    "type": "kpi",
                    "tag": "SIGNALS" if is_en else "ЦИФРЫ",
                    "title": "Snapshot" if is_en else "Срез дня",
                    "subtitle": "Insert real measured figures before rendering" if is_en else "Подставьте актуальные проверенные цифры",
                    "voice_text": (
                        "Here is the snapshot of key indicators — replace these slots with live measured data before publishing."
                        if is_en
                        else "Вот срез ключевых индикаторов — перед публикацией подставьте актуальные живые данные."
                    ),
                    "kpis": [
                        {"value": "3", "label": "top highlights" if is_en else "главных события"},
                        {"value": "100%", "label": "source-linked facts" if is_en else "фактов с источниками"},
                    ],
                },
                {
                    "type": "outro_3d",
                    "tag": "WRAP" if is_en else "ИТОГ",
                    "title": "Stay Informed" if is_en else "Будьте в курсе",
                    "subtitle": "Generated with DUP Presenter Idea Engine" if is_en else "Собрано через Генератор Идей DUP Presenter",
                    "voice_text": (
                        f"That wraps up the digest on {t}. Update the numbers whenever a new cycle starts."
                        if is_en
                        else f"На этом дайджест по теме {t} завершён. Обновляйте цифры в деке для каждого нового выпуска."
                    ),
                },
            ],
        },
        {
            "genre": "case_study",
            "angle": "Real Case Study" if is_en else "Кейс-стади: до и после",
            "title": f"{t}: Real-World Case Study" if is_en else f"{t}: разбор реального кейса",
            "hook": (
                f"What broke in {t}, how it was diagnosed, and what finally fixed it."
                if is_en
                else f"Что сломалось в {t}, как нашли корневую причину и какое решение сработало."
            ),
            "theme": "aurora_purple",
            "aspect": "16:9",
            "caption_style": "karaoke",
            "duration_hint_sec": 135,
            "slides": [
                {
                    "type": "hero_3d",
                    "tag": "CASE STUDY" if is_en else "КЕЙС",
                    "title": f"Case Study: {t}" if is_en else f"Кейс: {t}",
                    "subtitle": "Root cause, fix, and verified outcome" if is_en else "Корневая причина, решение и проверка результата",
                    "voice_text": (
                        f"Let us break down a real-world case study on {t}: the bottleneck, the root cause, and the verified fix."
                        if is_en
                        else f"Разберём реальный кейс по теме {t}: узкое место, корневую причину и проверенное исправление."
                    ),
                },
                {
                    "type": "timeline",
                    "tag": "CHRONOLOGY" if is_en else "ХОД РАБОТЫ",
                    "title": "From Symptom to Fix" if is_en else "От симптома к решению",
                    "subtitle": "Three steps of disciplined engineering" if is_en else "Три шага инженерного разбора",
                    "voice_text": (
                        "First we reproduced the issue reliably, then applied a surgical fix, and finally locked it down with regression tests."
                        if is_en
                        else "Сначала стабильно воспроизвели проблему, затем внесли хирургическое исправление и закрыли его регрессионным тестом."
                    ),
                    "steps": [
                        {"title": "Reproduce" if is_en else "Воспроизведение", "desc": "Capture exact logs and failing state." if is_en else "Зафиксировали точные логи и условия сбоя."},
                        {"title": "Surgical Fix" if is_en else "Точечный фикс", "desc": "Fix root cause without hiding errors." if is_en else "Устранили причину без костылей."},
                        {"title": "Regression Gate" if is_en else "Гейт регрессии", "desc": "Automated test prevents recurrence." if is_en else "Автотест не даст багу вернуться."},
                    ],
                },
                {
                    "type": "outro_3d",
                    "tag": "LESSON" if is_en else "УРОК",
                    "title": "Build With Evidence" if is_en else "Стройте на фактах",
                    "subtitle": f"{t} · case study template" if is_en else f"{t} · шаблон кейс-стади",
                    "voice_text": (
                        "Documenting real root causes builds far more trust than hiding problems."
                        if is_en
                        else "Честный разбор реальных причин даёт в разы больше доверия, чем замалчивание проблем."
                    ),
                },
            ],
        },
    ]

    if genre_filter and genre_filter != "all":
        if genre_filter not in GENRE_MAP:
            raise IdeaEngineError(f"Unknown genre {genre_filter!r}; allowed: {', '.join(sorted(GENRE_MAP))}")
        primary = [a for a in all_angles if a["genre"] == genre_filter]
        others = [a for a in all_angles if a["genre"] != genre_filter]
        ordered = primary + others
    else:
        ordered = all_angles
    return ordered


def _extract_json_object(raw: str) -> dict[str, Any]:
    text = str(raw or "").strip()
    if not text:
        raise IdeaEngineError("LLM returned an empty response")
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        m = re.search(r"\{[\s\S]*\}", text)
        if not m:
            raise IdeaEngineError("LLM response does not contain a JSON object")
        try:
            parsed = json.loads(m.group(0))
        except json.JSONDecodeError as exc:
            raise IdeaEngineError(f"LLM returned invalid JSON: {exc}") from exc
    if not isinstance(parsed, dict):
        raise IdeaEngineError("LLM JSON payload must be an object")
    return parsed


def _call_llm_ideas(
    topic: str,
    lang: str,
    genre: str,
    count: int,
    mode: str,
    model: str,
    host: str,
) -> dict[str, Any]:
    lang_label = "Russian" if lang == "ru" else "English"
    genre_note = f"Focus primarily on genre '{genre}'." if genre and genre != "all" else "Mix diverse genres."
    system_prompt = (
        "You are a senior video producer for DUP Presenter. Return ONLY valid JSON with key 'ideas' "
        f"(array of {count} objects). Language of all user-facing text: {lang_label}. {genre_note} "
        "Each idea must have: id (string), genre (one of: "
        + ", ".join(sorted(GENRE_MAP))
        + "), angle (string), title (string), hook (string, <=180 chars), "
        "aspect ('16:9' or '9:16'), theme (one of: "
        + ", ".join(THEME_IDS)
        + "), caption_style ('box'|'karaoke'|'bold'), duration_hint_sec (int 45..300), "
        "slides (array of 3..6 slide objects with type in ['hero_3d','kpi','timeline','quote','terminal','outro_3d'], "
        "tag, title, subtitle, voice_text, and type-specific fields: kpis for kpi, steps for timeline, lines for terminal). "
        "Do not fabricate fake benchmark numbers; mark placeholders clearly."
    )
    user_prompt = f"Topic / brief: {topic.strip()}\nGenerate {count} distinct, creative video concepts."

    if mode == "ollama":
        url = f"{host.rstrip('/')}/api/chat"
        payload = {
            "model": model or DEFAULT_OLLAMA_MODEL,
            "stream": False,
            "format": "json",
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        }
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=90) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except Exception as exc:
            raise IdeaEngineError(f"Ollama request failed ({url}): {exc}") from exc
        content = ((data.get("message") or {}).get("content")) or ""
        return _extract_json_object(content)

    if mode == "cloud":
        api_key = os.environ.get("DUP_LLM_API_KEY") or os.environ.get("OPENAI_API_KEY") or ""
        base_url = (os.environ.get("DUP_LLM_BASE_URL") or "https://api.openai.com/v1").rstrip("/")
        cloud_model = model or os.environ.get("DUP_LLM_MODEL") or "gpt-4o-mini"
        if not api_key:
            raise IdeaEngineError("Cloud LLM mode requires DUP_LLM_API_KEY or OPENAI_API_KEY")
        payload = {
            "model": cloud_model,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        }
        req = urllib.request.Request(
            f"{base_url}/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_key}",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=90) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except Exception as exc:
            raise IdeaEngineError(f"Cloud LLM request failed: {exc}") from exc
        choices = data.get("choices") or []
        content = ((choices[0].get("message") or {}).get("content")) if choices else ""
        return _extract_json_object(content)

    raise IdeaEngineError(f"Unsupported mode {mode!r}; expected 'template', 'ollama', or 'cloud'")


def _normalize_idea(raw: dict[str, Any], idx: int, topic: str, lang: str) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise IdeaEngineError(f"idea[{idx}] must be an object")
    title = str(raw.get("title") or "").strip()
    hook = str(raw.get("hook") or "").strip()
    if not title or not hook:
        raise IdeaEngineError(f"idea[{idx}] must have non-empty 'title' and 'hook'")
    genre = str(raw.get("genre") or "tech_explainer").strip()
    if genre not in GENRE_MAP:
        genre = "tech_explainer"
    theme = str(raw.get("theme") or GENRE_MAP[genre]["default_theme"]).strip()
    if theme not in THEME_IDS:
        theme = GENRE_MAP[genre]["default_theme"]
    aspect = str(raw.get("aspect") or GENRE_MAP[genre]["default_aspect"]).strip()
    if aspect not in ASPECT_DIMS:
        aspect = "16:9"
    caption_style = str(raw.get("caption_style") or GENRE_MAP[genre]["default_caption_style"]).strip()
    if caption_style not in CAPTION_STYLES:
        caption_style = "karaoke"
    slides = raw.get("slides")
    if not isinstance(slides, list) or len(slides) < 2:
        raise IdeaEngineError(f"idea[{idx}] must contain at least 2 slides")
    clean_slides: list[dict[str, Any]] = []
    for s_idx, s in enumerate(slides, 1):
        if not isinstance(s, dict):
            raise IdeaEngineError(f"idea[{idx}].slides[{s_idx}] must be an object")
        stype = str(s.get("type") or "").strip()
        if stype not in SUPPORTED_IDEA_SLIDE_TYPES:
            raise IdeaEngineError(
                f"idea[{idx}].slides[{s_idx}].type={stype!r} not in {sorted(SUPPORTED_IDEA_SLIDE_TYPES)}"
            )
        stitle = str(s.get("title") or "").strip()
        svoice = str(s.get("voice_text") or "").strip()
        if not stitle or not svoice:
            raise IdeaEngineError(f"idea[{idx}].slides[{s_idx}] requires non-empty title and voice_text")
        clean_slides.append(dict(s))
    return {
        "id": str(raw.get("id") or f"idea-{idx}"),
        "genre": genre,
        "angle": str(raw.get("angle") or GENRE_MAP[genre]["label_en" if lang == "en" else "label_ru"]).strip(),
        "title": title,
        "hook": hook,
        "theme": theme,
        "aspect": aspect,
        "caption_style": caption_style,
        "duration_hint_sec": int(raw.get("duration_hint_sec") or GENRE_MAP[genre]["duration_hint_sec"]),
        "lang": lang,
        "suggested_slug": slugify_topic(f"{topic}-{genre}"),
        "slides": clean_slides,
    }


def generate_ideas(
    topic: str,
    *,
    lang: str = "ru",
    genre: str = "all",
    count: int = 5,
    mode: str = "template",
    model: str = "",
    host: str = DEFAULT_OLLAMA_HOST,
) -> dict[str, Any]:
    """Generate structured video concepts. Fails closed on bad input or provider errors."""
    clean_topic = str(topic or "").strip()
    if len(clean_topic) < 2:
        raise IdeaEngineError("Topic must be at least 2 characters long")
    clean_lang = str(lang or "ru").strip().lower()
    if clean_lang not in {"ru", "en"}:
        raise IdeaEngineError(f"Unsupported lang {lang!r}; expected 'ru' or 'en'")
    if not isinstance(count, int) or not (1 <= count <= 7):
        raise IdeaEngineError("count must be an integer between 1 and 7")
    clean_mode = str(mode or "template").strip().lower()
    if clean_mode not in {"template", "ollama", "cloud"}:
        raise IdeaEngineError(f"Unsupported mode {mode!r}; expected 'template', 'ollama', or 'cloud'")

    if clean_mode == "template":
        blueprints = _angle_blueprints(clean_topic, clean_lang, genre)[:count]
        ideas = [_normalize_idea(bp, i + 1, clean_topic, clean_lang) for i, bp in enumerate(blueprints)]
        return {
            "ok": True,
            "source": "template",
            "topic": clean_topic,
            "lang": clean_lang,
            "genre": genre,
            "ideas": ideas,
        }

    raw_payload = _call_llm_ideas(clean_topic, clean_lang, genre, count, clean_mode, model, host)
    raw_ideas = raw_payload.get("ideas")
    if not isinstance(raw_ideas, list) or not raw_ideas:
        raise IdeaEngineError("LLM response JSON must contain a non-empty 'ideas' list")
    ideas = [_normalize_idea(item, i + 1, clean_topic, clean_lang) for i, item in enumerate(raw_ideas[:count])]
    return {
        "ok": True,
        "source": clean_mode,
        "topic": clean_topic,
        "lang": clean_lang,
        "genre": genre,
        "ideas": ideas,
    }


def idea_to_deck(
    idea: dict[str, Any],
    *,
    slug: str = "",
    brand: str = "DUP LABS",
) -> dict[str, Any]:
    """Convert a normalized idea dict into a validated DUP Presenter deck JSON."""
    if not isinstance(idea, dict):
        raise IdeaEngineError("idea must be a JSON object")
    lang = str(idea.get("lang") or "ru").strip().lower()
    if lang not in {"ru", "en"}:
        raise IdeaEngineError(f"Unsupported idea lang {lang!r}")
    theme = str(idea.get("theme") or "quantum_ledger").strip()
    if theme not in THEME_IDS:
        raise IdeaEngineError(f"Unsupported theme {theme!r}")
    aspect = str(idea.get("aspect") or "16:9").strip()
    if aspect not in ASPECT_DIMS:
        raise IdeaEngineError(f"Unsupported aspect {aspect!r}")
    caption_style = str(idea.get("caption_style") or "karaoke").strip()
    if caption_style not in CAPTION_STYLES:
        raise IdeaEngineError(f"Unsupported caption_style {caption_style!r}")

    final_slug = slug.strip().lower() if slug else str(idea.get("suggested_slug") or slugify_topic(str(idea.get("title") or "")))
    if not SLUG_RE.match(final_slug):
        raise IdeaEngineError(f"Invalid slug {final_slug!r}; must match {SLUG_RE.pattern}")

    raw_slides = idea.get("slides")
    if not isinstance(raw_slides, list) or not raw_slides:
        raise IdeaEngineError("idea.slides must be a non-empty list")

    width, height = ASPECT_DIMS[aspect]
    voice = (
        {
            "engine": "kokoro_v1",
            "lang": "en",
            "speaker": "am_michael",
            "rate": "96%",
            "ambient_volume": 0.08,
            "mode": "single",
        }
        if lang == "en"
        else {
            "engine": "edge_tts",
            "lang": "ru",
            "speaker": "dmitry",
            "rate": "98%",
            "ambient_volume": 0.08,
            "mode": "single",
            "fallback_speaker": "eugene",
        }
    )

    slides: list[dict[str, Any]] = []
    for idx, src in enumerate(raw_slides, 1):
        stype = str(src.get("type") or "").strip()
        if stype not in SUPPORTED_IDEA_SLIDE_TYPES:
            raise IdeaEngineError(f"Unsupported slide type {stype!r} in idea_to_deck")
        slide: dict[str, Any] = {
            "id": f"s{idx}",
            "tag": str(src.get("tag") or f"STEP {idx}").upper(),
            "type": stype,
            "title": str(src.get("title") or "").strip(),
            "subtitle": str(src.get("subtitle") or "").strip(),
            "voice_text": str(src.get("voice_text") or "").strip(),
        }
        if stype == "hero_3d":
            slide["pills"] = src.get("pills") or [
                {"name": "DUP Presenter", "color": "#00f0ff"},
                {"name": idea.get("genre", "story").replace("_", " ").title(), "color": "#10ff88"},
            ]
            slide["cube_faces"] = src.get("cube_faces") or ["DUP", "IDEA", "STORY", "3D", "QA", "LIVE"]
        elif stype == "kpi":
            kpis = src.get("kpis") or [{"value": "100%", "label": "reproducible build"}]
            slide["kpis"] = kpis[:4]
        elif stype == "timeline":
            steps = src.get("bullets") or src.get("steps") or [
                {"title": "Step 1", "desc": "Start cleanly."},
                {"title": "Step 2", "desc": "Verify output."},
            ]
            slide["bullets"] = steps[:6]
        elif stype == "quote":
            slide["bullets"] = []
        elif stype == "terminal":
            lines = (src.get("code") or {}).get("lines") or src.get("lines") or [
                {"text": "$ python scripts/build_deck.py --render", "color": "#22d3ee"}
            ]
            slide["code"] = {
                "filename": str((src.get("code") or {}).get("filename") or "terminal · cli"),
                "lines": lines,
            }
        elif stype == "outro_3d":
            slide["url"] = str(src.get("url") or "github.com/Gruver87/dup-presenter")
            slide["tagline"] = str(src.get("tagline") or "Built with DUP Presenter · Idea Engine")
            slide["badges"] = src.get("badges") or [
                {"name": "DUP Labs", "color": "#00f0ff"},
                {"name": "Media QA Gate", "color": "#10ff88"},
            ]
            slide["cube_faces"] = src.get("cube_faces") or ["DUP", "LABS", "3D", "TTS", "QA", "1080P"]
        elif stype == "versus_split":
            slide["versus"] = src.get("versus") or {
                "left": {"label": "Old Way", "badge": "BEFORE", "points": ["Manual work", "Hidden drift"]},
                "right": {"label": "New Way", "badge": "AFTER", "points": ["Automated pipeline", "Fail-closed checks"]},
            }
        elif stype == "chart_story":
            slide["chart"] = src.get("chart") or {
                "kind": "bar",
                "series": [{"label": "Baseline", "value": 30}, {"label": "Optimized", "value": 95}],
            }
        elif stype == "stat_burst":
            slide["stat_burst"] = src.get("stat_burst") or {
                "headline": "100%",
                "caption": slide["subtitle"] or slide["title"],
            }
        elif stype == "broll_cinematic":
            slide["broll"] = src.get("broll") or {
                "badge": slide["tag"],
                "caption": slide["subtitle"] or slide["title"],
            }
        slides.append(slide)

    deck: dict[str, Any] = {
        "slug": final_slug,
        "lang": lang,
        "theme": theme,
        "aspect": aspect,
        "burn_captions": True,
        "caption_style": caption_style,
        "transition_style": "fade",
        "transition_frames": 15,
        "sfx_enabled": True,
        "sfx_volume": 0.16,
        "brand": brand,
        "fps": 30,
        "width": width,
        "height": height,
        "music": {
            "enabled": True,
            "file": "atlasaudio-epic-emotional-640150.mp3",
            "volume": 0.1,
            "duck_db": -10.5,
        },
        "background": {"enabled": False, "provider": "pixabay"},
        "voice": voice,
        "slides": slides,
    }
    # Fail-closed verification against build_deck schema!
    validate_deck(deck)
    return deck


def write_idea_deck(
    idea: dict[str, Any],
    decks_dir: Path = DECKS_DIR,
    *,
    slug: str = "",
    brand: str = "DUP LABS",
    overwrite: bool = False,
) -> tuple[dict[str, Any], Path]:
    """Convert an idea into a validated deck JSON and write it to `decks/<slug>.json`."""
    deck = idea_to_deck(idea, slug=slug, brand=brand)
    decks_dir.mkdir(parents=True, exist_ok=True)
    target = (decks_dir / f"{deck['slug']}.json").resolve()
    if target.parent != decks_dir.resolve():
        raise IdeaEngineError("Resolved deck path escaped decks directory")
    if target.exists() and not overwrite:
        raise IdeaDeckExistsError(f"Deck already exists: {target.name}")
    target.write_text(json.dumps(deck, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return deck, target


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="DUP Presenter built-in Idea Engine")
    parser.add_argument("--topic", required=True, help="Topic, product name, or short brief")
    parser.add_argument("--lang", choices=["ru", "en"], default="ru")
    parser.add_argument("--genre", default="all", help=f"Genre filter: all | {', '.join(sorted(GENRE_MAP))}")
    parser.add_argument("--count", type=int, default=5, help="Number of ideas (1..7)")
    parser.add_argument("--mode", choices=["template", "ollama", "cloud"], default="template")
    parser.add_argument("--model", default="", help="Optional LLM model override")
    parser.add_argument("--host", default=DEFAULT_OLLAMA_HOST, help="Ollama base URL")
    parser.add_argument("--write-first", action="store_true", help="Convert idea #1 into decks/<slug>.json")
    parser.add_argument("--slug", default="", help="Optional slug when --write-first is set")
    parser.add_argument("--overwrite", action="store_true", help="Overwrite existing deck file")
    args = parser.parse_args(argv)

    try:
        result = generate_ideas(
            args.topic,
            lang=args.lang,
            genre=args.genre,
            count=args.count,
            mode=args.mode,
            model=args.model,
            host=args.host,
        )
        if args.write_first:
            deck, path = write_idea_deck(
                result["ideas"][0],
                DECKS_DIR,
                slug=args.slug,
                overwrite=args.overwrite,
            )
            result["written_deck"] = str(path)
            result["written_slug"] = deck["slug"]
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (IdeaEngineError, IdeaDeckExistsError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
