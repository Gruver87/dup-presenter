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
                    "type": "stat_burst",
                    "tag": "60 SEC HOOK" if is_en else "ХУК 60 СЕК",
                    "title": f"{t} in 60s" if is_en else f"{t} за 60 сек",
                    "subtitle": "One sharp idea, zero fluff" if is_en else "Одна сильная мысль, ноль воды",
                    "voice_text": (
                        f"Stop scrolling. Here is the single clearest way to understand {t} in under a minute."
                        if is_en
                        else f"Не пролистывай. Вот самый понятный способ разобраться в {t} меньше чем за минуту."
                    ),
                    "stat_burst": {
                        "kicker": "60 SECOND BREAKDOWN" if is_en else "РАЗБОР ЗА 60 СЕКУНД",
                        "headline": "60 SEC" if is_en else "60 СЕК",
                        "caption": f"{t}: what actually matters without fluff" if is_en else f"{t}: главная суть без воды",
                        "chips": [
                            {"label": "9:16 Short", "color": "#00f0ff"},
                            {"label": "Zero Fluff" if is_en else "Без воды", "color": "#10ff88"},
                        ],
                    },
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
                    "type": "versus_split",
                    "tag": "COMPARISON" if is_en else "СРАВНЕНИЕ",
                    "title": f"{t}: A vs B" if is_en else f"{t}: Старый путь vs Новый путь",
                    "subtitle": "Reliability, speed, and operational clarity" if is_en else "Надёжность, скорость и прозрачность работы",
                    "voice_text": (
                        "We compare both options side by side across three real criteria: failure handling, execution speed, and auditability."
                        if is_en
                        else "Сравним оба подхода лицом к лицу по трём критериям: реакция на сбой, скорость ядра и проверяемость."
                    ),
                    "versus": {
                        "left": {
                            "label": "Legacy Way" if is_en else "Старый подход",
                            "badge": "RISK" if is_en else "РИСК",
                            "points": [
                                "Silent fallbacks hide errors" if is_en else "Тихие сбои скрывают ошибки",
                                "Ad-hoc glue slows down execution" if is_en else "Ручная склейка тормозит работу",
                                "Hard to reproduce or audit" if is_en else "Трудно повторить и проверить",
                            ],
                            "accent": "#ff2e63",
                        },
                        "right": {
                            "label": "Modern Approach" if is_en else "Новый подход",
                            "badge": "FAIL-CLOSED",
                            "points": [
                                "Refuses bad input at the boundary" if is_en else "Отказ на границе при ошибке",
                                "Dedicated hot path for speed" if is_en else "Быстрое ядро для горячего пути",
                                "Deterministic, auditable artifacts" if is_en else "Детерминированные артефакты на диске",
                            ],
                            "accent": "#10ff88",
                        },
                        "verdict": (
                            "Choose the design that fails loudly in tests rather than silently in production."
                            if is_en
                            else "Выбирайте систему, которая громко падает на тесте, а не тихо врёт в проде."
                        ),
                    },
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
                    "type": "chart_story",
                    "tag": "SIGNALS" if is_en else "ГРАФИК",
                    "title": "Signal Snapshot" if is_en else "Срез ключевых сигналов",
                    "subtitle": "Insert live measured figures before rendering" if is_en else "Подставьте актуальные проверенные цифры перед рендером",
                    "voice_text": (
                        "Here is a visual snapshot of the main signals — replace these placeholder bars with live measured data before publishing."
                        if is_en
                        else "Вот наглядный срез главных сигналов — перед публикацией подставьте актуальные живые данные."
                    ),
                    "chart": {
                        "kind": "bar",
                        "unit": "pts",
                        "source_note": "Placeholder values — replace with verified metrics" if is_en else "Ориентировочные значения — замените на реальные данные",
                        "series": [
                            {"label": "Signal A" if is_en else "Сигнал A", "value": 42, "color": "#00f0ff"},
                            {"label": "Signal B" if is_en else "Сигнал B", "value": 78, "color": "#10ff88"},
                            {"label": "Signal C" if is_en else "Сигнал C", "value": 64, "color": "#ffb800"},
                        ],
                    },
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
        "slides (array of 3..6 slide objects; slide.type MUST be strictly one of: "
        + ", ".join(sorted(SUPPORTED_IDEA_SLIDE_TYPES))
        + " — NEVER use genre names like 'versus_battle' as slide.type; "
        "EVERY slide MUST include non-empty strings 'tag', 'title', and 'voice_text' — never omit or leave empty even on quote/outro_3d; "
        "optional 'subtitle', and type-specific fields: kpis as [{'value':'<=12 chars','label':'...'}] for kpi, "
        "steps as [{'title':'...','desc':'...'}] for timeline, lines as [{'text':'...'}] for terminal). "
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

    if mode == "deepseek":
        api_key = os.environ.get("DEEPSEEK_API_KEY") or os.environ.get("DUP_LLM_API_KEY") or ""
        base_url = (
            os.environ.get("DEEPSEEK_BASE_URL")
            or os.environ.get("DUP_LLM_BASE_URL")
            or "https://api.deepseek.com/v1"
        ).rstrip("/")
        ds_model = model or os.environ.get("DEEPSEEK_MODEL") or os.environ.get("DUP_LLM_MODEL") or "deepseek-chat"
        if not api_key:
            raise IdeaEngineError("DeepSeek mode requires DEEPSEEK_API_KEY (or DUP_LLM_API_KEY)")
        payload = {
            "model": ds_model,
            "max_tokens": 8192,
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
            raise IdeaEngineError(f"DeepSeek request failed: {exc}") from exc
        choices = data.get("choices") or []
        content = ((choices[0].get("message") or {}).get("content")) if choices else ""
        return _extract_json_object(content)

    if mode == "cloud":
        api_key = (
            os.environ.get("DUP_LLM_API_KEY")
            or os.environ.get("DEEPSEEK_API_KEY")
            or os.environ.get("OPENAI_API_KEY")
            or ""
        )
        is_deepseek = bool(os.environ.get("DEEPSEEK_API_KEY") and not os.environ.get("DUP_LLM_API_KEY"))
        default_base = "https://api.deepseek.com/v1" if is_deepseek else "https://api.openai.com/v1"
        default_model = "deepseek-chat" if is_deepseek else "gpt-4o-mini"
        base_url = (os.environ.get("DUP_LLM_BASE_URL") or default_base).rstrip("/")
        cloud_model = model or os.environ.get("DUP_LLM_MODEL") or default_model
        if not api_key:
            raise IdeaEngineError("Cloud LLM mode requires DUP_LLM_API_KEY, DEEPSEEK_API_KEY, or OPENAI_API_KEY")
        payload = {
            "model": cloud_model,
            "max_tokens": 8192,
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


def assess_topic_complexity(
    topic: str,
    genre: str = "all",
    lang: str = "ru",
) -> dict[str, Any]:
    """Automatically classify topic complexity and select the best studio tools & preset."""
    low = str(topic or "").lower()
    words = [w for w in re.split(r"\s+", low) if w]
    is_en = lang == "en"

    has_versus = any(k in low for k in (" vs ", "против", "сравн", "compare", "versus", "или "))
    has_metrics = any(k in low for k in ("рынок", "market", "метрик", "chart", "график", "аналит", "дайджест", "digest", "%", "roi", "benchmark"))
    has_deep_tech = any(
        k in low
        for k in (
            "блокчейн", "blockchain", "protocol", "протокол", "rust", "python", "архитект", "architecture",
            "consensus", "консенсус", "libp2p", "merkle", "api", "evm", "ядро", "алгоритм", "квантов",
        )
    )
    has_short = genre == "short_60s" or any(k in low for k in ("short", "reels", "tiktok", "60 сек", "60s", "шорт"))

    score = 0
    if len(words) >= 6:
        score += 1
    if has_deep_tech:
        score += 2
    if has_versus:
        score += 1
    if has_metrics:
        score += 1

    if has_short and score <= 1:
        complexity = "simple"
    elif score >= 3:
        complexity = "deep"
    elif score >= 1:
        complexity = "medium"
    else:
        complexity = "simple"

    tools: list[str] = ["thumbnail_studio"]
    if has_short:
        preset = "fast_shorts"
        tools.extend(["stat_burst", "video_pack_short"])
    elif has_versus or genre == "versus_battle":
        preset = "cinema_cosmos" if has_deep_tech else "news_flash"
        tools.extend(["versus_split", "stat_burst", "podcast_voice"])
    elif has_metrics or genre == "news_digest":
        preset = "news_flash"
        tools.extend(["chart_story", "kpi"])
    elif genre == "investor_pitch":
        preset = "tech_pitch"
        tools.extend(["kpi", "chart_story", "timeline"])
    elif has_deep_tech or complexity == "deep":
        preset = "cinema_cosmos"
        tools.extend(["protocol_cosmos", "ledger_layers", "chart_story", "video_pack"])
    else:
        preset = "documentary"
        tools.extend(["broll_cinematic", "timeline", "quote"])

    # Deduplicate while preserving order
    unique_tools = list(dict.fromkeys(tools))
    voice_mode = "podcast" if (has_versus or genre == "versus_battle") else "single"

    if is_en:
        reason = (
            f"Complexity='{complexity}': selected preset '{preset}', voice='{voice_mode}', "
            f"and tools {', '.join(unique_tools)}."
        )
    else:
        reason = (
            f"Сложность='{complexity}': автоматически выбраны пресет '{preset}', голос='{voice_mode}' "
            f"и инструменты: {', '.join(unique_tools)}."
        )
    return {
        "complexity": complexity,
        "recommended_preset": preset,
        "recommended_voice_mode": voice_mode,
        "recommended_tools": unique_tools,
        "reasoning": reason,
    }


VISUAL_SLIDE_TYPES: frozenset[str] = frozenset(
    {
        "protocol_cosmos",
        "ledger_layers",
        "tx_journey",
        "mesh_network",
        "versus_split",
        "chart_story",
        "screen_split",
        "code_split",
        "ui_recording",
        "arch_flow",
        "broll_cinematic",
    }
)


def critique_deck(deck: dict[str, Any], lang: str = "") -> dict[str, Any]:
    """Analyze a deck and return concrete director suggestions: what to add, remove, or upgrade."""
    if not isinstance(deck, dict):
        raise IdeaEngineError("deck must be a JSON object")
    slides = deck.get("slides") or []
    if not isinstance(slides, list) or not slides:
        raise IdeaEngineError("deck.slides must be a non-empty list")

    effective_lang = (lang or str(deck.get("lang") or "ru")).lower()
    is_en = effective_lang == "en"

    add_tips: list[str] = []
    remove_tips: list[str] = []
    upgrade_tips: list[str] = []
    penalty = 0

    types = [str(s.get("type") or "") for s in slides]
    aspect = str(deck.get("aspect") or "16:9")
    caption_style = str(deck.get("caption_style") or "box")

    # 1. Opening hook check
    if types[0] not in {"hero_3d", "stat_burst"}:
        penalty += 12
        add_tips.append(
            "Add a 'stat_burst' or 'hero_3d' hook as slide 1 to lock viewer attention in the first 3 seconds."
            if is_en
            else "Добавь ударный хук 'stat_burst' или 'hero_3d' первым слайдом, чтобы удержать зрителя в первые 3 секунды."
        )

    # 2. Visual variety check
    if len(slides) >= 4 and not any(t in VISUAL_SLIDE_TYPES for t in types):
        penalty += 18
        add_tips.append(
            "No rich visual slide found: add 'chart_story', 'versus_split', 'broll_cinematic', or 'protocol_cosmos' to break up text."
            if is_en
            else "Нет ни одного сильного визуального слайда: добавь 'chart_story' (график), 'versus_split' (A vs B) или 'broll_cinematic' для динамики."
        )

    # 3. Outro check
    if types[-1] != "outro_3d":
        penalty += 8
        add_tips.append(
            "Add an 'outro_3d' closing slide with a clear link or call to action."
            if is_en
            else "Добавь финальный слайд 'outro_3d' со ссылкой или понятным итогом."
        )

    # 4. Consecutive duplicate slide types (monotony)
    for i in range(1, len(types)):
        if types[i] == types[i - 1]:
            penalty += 10
            sid_prev = slides[i - 1].get("id") or f"s{i}"
            sid_cur = slides[i].get("id") or f"s{i + 1}"
            remove_tips.append(
                f"Slides {sid_prev} and {sid_cur} repeat type '{types[i]}' back-to-back — vary or merge them."
                if is_en
                else f"Слайды {sid_prev} и {sid_cur} подряд повторяют тип '{types[i]}' — замени один из них или объедини."
            )

    # 5. Per-slide narration pacing check
    for idx, s in enumerate(slides, 1):
        sid = s.get("id") or f"s{idx}"
        words = [w for w in re.split(r"\s+", str(s.get("voice_text") or "").strip()) if w]
        if len(words) > 95:
            penalty += 8
            remove_tips.append(
                f"Slide {sid} narration is too dense ({len(words)} words) — trim or split into 2 slides for better pacing."
                if is_en
                else f"На слайде {sid} слишком длинная озвучка ({len(words)} слов) — сократи текст или разбей на 2 слайда."
            )
        elif len(words) < 6:
            penalty += 5
            upgrade_tips.append(
                f"Slide {sid} narration is very short ({len(words)} words) — expand with one clear takeaway."
                if is_en
                else f"На слайде {sid} очень короткая реплика ({len(words)} слов) — добавь одну чёткую мысль."
            )

    # 6. Aspect vs caption style check
    if aspect == "9:16" and caption_style == "box":
        penalty += 8
        upgrade_tips.append(
            "For 9:16 vertical Shorts, switch caption_style from 'box' to 'bold' or 'karaoke' for higher mobile readability."
            if is_en
            else "Для вертикального 9:16 Short переключи caption_style с 'box' на 'bold' или 'karaoke' — на телефоне читается намного лучше."
        )

    # 7. Director preset / thumbnail tip
    if not deck.get("director_preset"):
        upgrade_tips.append(
            "Tip: attach a director_preset ('cinema_cosmos', 'fast_shorts', 'news_flash', etc.) and render a 1280x720 cover via Thumbnail Studio."
            if is_en
            else "Совет: примени режиссёрский пресет ('cinema_cosmos', 'fast_shorts', 'news_flash') и сделай обложку 1280×720 в Thumbnail Studio."
        )

    score = max(0, min(100, 100 - penalty))
    return {
        "ok": True,
        "slug": str(deck.get("slug") or ""),
        "slide_count": len(slides),
        "score": score,
        "add": add_tips,
        "remove": remove_tips,
        "upgrade": upgrade_tips,
    }


def auto_fix_deck(deck: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    """Apply safe, deterministic director fixes to a deck without fabricating facts."""
    import copy
    from director_presets import apply_director_preset

    if not isinstance(deck, dict):
        raise IdeaEngineError("deck must be a JSON object")
    out = copy.deepcopy(deck)
    slides = list(out.get("slides") or [])
    if not slides:
        raise IdeaEngineError("deck.slides must be a non-empty list")

    lang = str(out.get("lang") or "ru").lower()
    is_en = lang == "en"
    changes: list[str] = []

    # 1. Upgrade 9:16 box captions -> bold
    if str(out.get("aspect") or "16:9") == "9:16" and str(out.get("caption_style") or "box") == "box":
        out["caption_style"] = "bold"
        changes.append("caption_style: box -> bold (9:16 vertical readability)")

    # 2. Attach default director_preset without overwriting explicit user fields
    if not out.get("director_preset"):
        preset_id = "fast_shorts" if str(out.get("aspect") or "16:9") == "9:16" else "cinema_cosmos"
        out = apply_director_preset(out, preset_id, override_existing=False)
        changes.append(f"director_preset: attached '{preset_id}' (preserving explicit deck settings)")

    # 3. Ensure closing outro_3d exists
    if str(slides[-1].get("type") or "") != "outro_3d":
        next_num = len(slides) + 1
        outro = {
            "id": f"s{next_num}",
            "tag": "FINALE" if is_en else "ФИНАЛ",
            "type": "outro_3d",
            "title": str(slides[0].get("title") or out.get("slug") or "Summary"),
            "subtitle": "Built with DUP Presenter" if is_en else "Собрано в DUP Presenter",
            "voice_text": (
                "Thank you for watching. Inspect the repository and verification artifacts directly."
                if is_en
                else "Спасибо за просмотр. Код и проверяемые артефакты открыты в репозитории."
            ),
            "url": "github.com/Gruver87/dup-presenter",
            "tagline": "DUP Labs · reproducible 3D presentations",
            "badges": [
                {"name": "DUP Labs", "color": "#00f0ff"},
                {"name": "Media QA Gate", "color": "#10ff88"},
            ],
            "cube_faces": ["DUP", "LABS", "3D", "TTS", "QA", "1080P"],
        }
        slides.append(outro)
        out["slides"] = slides
        changes.append(f"added closing outro_3d slide (s{next_num})")

    validate_deck(out)
    return out, changes


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
    """Generate structured video concepts with automatic complexity & tool selection."""
    clean_topic = str(topic or "").strip()
    if len(clean_topic) < 2:
        raise IdeaEngineError("Topic must be at least 2 characters long")
    clean_lang = str(lang or "ru").strip().lower()
    if clean_lang not in {"ru", "en"}:
        raise IdeaEngineError(f"Unsupported lang {lang!r}; expected 'ru' or 'en'")
    if not isinstance(count, int) or not (1 <= count <= 7):
        raise IdeaEngineError("count must be an integer between 1 and 7")
    clean_mode = str(mode or "template").strip().lower()
    if clean_mode not in {"template", "ollama", "cloud", "deepseek"}:
        raise IdeaEngineError(f"Unsupported mode {mode!r}; expected 'template', 'ollama', 'cloud', or 'deepseek'")

    assessment = assess_topic_complexity(clean_topic, genre=genre, lang=clean_lang)

    if clean_mode == "template":
        blueprints = _angle_blueprints(clean_topic, clean_lang, genre)[:count]
        ideas = []
        for i, bp in enumerate(blueprints):
            item = _normalize_idea(bp, i + 1, clean_topic, clean_lang)
            per_idea_assess = assess_topic_complexity(clean_topic, genre=item["genre"], lang=clean_lang)
            item["complexity"] = per_idea_assess["complexity"]
            item["recommended_preset"] = per_idea_assess["recommended_preset"]
            item["recommended_tools"] = per_idea_assess["recommended_tools"]
            ideas.append(item)
        return {
            "ok": True,
            "source": "template",
            "topic": clean_topic,
            "lang": clean_lang,
            "genre": genre,
            "assessment": assessment,
            "ideas": ideas,
        }

    raw_payload = _call_llm_ideas(clean_topic, clean_lang, genre, count, clean_mode, model, host)
    raw_ideas = raw_payload.get("ideas")
    if not isinstance(raw_ideas, list) or not raw_ideas:
        raise IdeaEngineError("LLM response JSON must contain a non-empty 'ideas' list")
    ideas = []
    for i, item in enumerate(raw_ideas[:count]):
        norm = _normalize_idea(item, i + 1, clean_topic, clean_lang)
        per_idea_assess = assess_topic_complexity(clean_topic, genre=norm["genre"], lang=clean_lang)
        norm["complexity"] = per_idea_assess["complexity"]
        norm["recommended_preset"] = per_idea_assess["recommended_preset"]
        norm["recommended_tools"] = per_idea_assess["recommended_tools"]
        ideas.append(norm)
    return {
        "ok": True,
        "source": clean_mode,
        "topic": clean_topic,
        "lang": clean_lang,
        "genre": genre,
        "assessment": assessment,
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
    voice_mode = "podcast" if idea.get("recommended_voice_mode") == "podcast" else "single"
    voice = (
        {
            "engine": "kokoro_v1",
            "lang": "en",
            "speaker": "am_michael",
            "rate": "96%",
            "ambient_volume": 0.08,
            "mode": voice_mode,
        }
        if lang == "en"
        else {
            "engine": "edge_tts",
            "lang": "ru",
            "speaker": "dmitry",
            "rate": "98%",
            "ambient_volume": 0.08,
            "mode": voice_mode,
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
            raw_kpis = src.get("kpis") or [{"value": "100%", "label": "reproducible build"}]
            norm_kpis: list[dict[str, str]] = []
            for item in raw_kpis[:4]:
                if isinstance(item, dict):
                    val = str(item.get("value") or item.get("metric") or "").strip()[:12].strip()
                    lbl = str(item.get("label") or item.get("title") or item.get("name") or "").strip()
                    if val and lbl:
                        norm_kpis.append({"value": val, "label": lbl})
                elif isinstance(item, str) and item.strip():
                    parts = re.split(r"\s*[—–:-]\s*", item.strip(), maxsplit=1)
                    if len(parts) == 2 and parts[0] and parts[1]:
                        norm_kpis.append({"value": parts[0][:12].strip(), "label": parts[1]})
                    else:
                        norm_kpis.append({"value": item.strip()[:12].strip(), "label": item.strip()})
            slide["kpis"] = norm_kpis or [{"value": "100%", "label": "reproducible build"}]
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
    parser.add_argument("--mode", choices=["template", "ollama", "cloud", "deepseek"], default="template")
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
