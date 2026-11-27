"""Generate & render all 8 vertical 9:16 TikTok chapter teasers for DUP Labs via dup-presenter."""
import json
import subprocess
import sys
from pathlib import Path
import imageio_ffmpeg

REPO = Path(r"C:\Users\vovun\Desktop\DUP_Projects\dup-presenter")
DECKS = REPO / "decks"
OUT = REPO / "out"
FFMPEG = imageio_ffmpeg.get_ffmpeg_exe()

REELS = [
    {
        "ep": "01",
        "slug": "dup-tiktok-01-protocol",
        "repo": "dup-protocol",
        "tag": "ГЛАВА 01 / 08 · DUP-PROTOCOL",
        "title": "Гибридный L1: Rust + Python",
        "badge": "ГЛАВА 01 / 08 · DUP-PROTOCOL · RUST + LIBP2P",
        "shot1": "cinema/dup_01_protocol_hd.mp4",
        "shot2": "cinema/u_01_protocol_action.mp4",
        "voice1": "Как устроен блокчейн первого уровня, который не врёт? Знакомьтесь — дап протокол. Внутри горячий путь на языке Раст мгновенно проверяет криптографию и запаковывает состояние в Рокс Ди Би, а Питон строго оркестрирует правила. Три независимых узла в сети либ-пи-ту-пи: любой поддельный блок разбивается о барьер, не попадая в цепь.",
        "voice2": "Исходный код открыт на Гитхаб. Ссылка прямо на экране. Смотри все восемь глав Вселенной ДАП Лабс.",
    },
    {
        "ep": "02",
        "slug": "dup-tiktok-02-presenter",
        "repo": "dup-presenter",
        "tag": "ГЛАВА 02 / 08 · DUP-PRESENTER",
        "title": "Автономная киностудия",
        "badge": "ГЛАВА 02 / 08 · DUP-PRESENTER · 3D & CINEMA",
        "shot1": "cinema/dup_02_presenter_hd.mp4",
        "shot2": "cinema/u_02_presenter_action.mp4",
        "voice1": "Этот ролик смонтирован без единого клика в видеоредакторе. Второе ядро Вселенной ДАП Лабс — дап презентер. Гранёный золотой кристалл работает как автономная киностудия: речевая дорожка, синхронизация субтитров по словам, трёхмерные сцены, переходы и мастеринг минус шестнадцать люфс собираются из одного сценария в готовый фильм.",
        "voice2": "Попробуй сам — репозиторий дап презентер открыт на Гитхаб. Ссылка перед тобой.",
    },
    {
        "ep": "03",
        "slug": "dup-tiktok-03-market-radar",
        "repo": "dup-market-radar",
        "tag": "ГЛАВА 03 / 08 · DUP-MARKET-RADAR",
        "title": "Спотовый кокпит и телеметрия",
        "badge": "ГЛАВА 03 / 08 · DUP-MARKET-RADAR · SPOT COCKPIT",
        "shot1": "cinema/dup_03_market_radar_hd.mp4",
        "shot2": "cinema/u_03_radar_action.mp4",
        "voice1": "Почему торговые боты сливают депозиты? Из-за слепых фьючерсов с плечом. Третье ядро ДАП Лабс — маркет радар. Его лазерный луч в реальном времени сканирует спотовый рынок, ловит часовые импульсы и экстремумы фандинга и шлёт честные дайджесты в Телеграм и мобильный кокпит. Авто-торговля фьючерсами заблокирована в архитектуре навсегда.",
        "voice2": "Весь код маркет радара открыт на Гитхаб. Ссылка на экране. Впереди четвёртая глава.",
    },
    {
        "ep": "04",
        "slug": "dup-tiktok-04-skill-trust-plane",
        "repo": "dup-skill-trust-plane",
        "tag": "ГЛАВА 04 / 08 · DUP-SKILL-TRUST-PLANE",
        "title": "Zero-Key доверие для ИИ",
        "badge": "ГЛАВА 04 / 08 · SKILL TRUST PLANE · ZERO-KEY AI",
        "shot1": "cinema/dup_04_trust_plane_hd.mp4",
        "shot2": "cinema/u_04_trust_action.mp4",
        "voice1": "Ты запускаешь чужие навыки для ИИ-агентов вслепую? Это главная дыра безопасности сегодня. Четвёртое ядро ДАП Лабс — скилл траст плэйн. Каждый навык проходит криптографическую аттестацию: проверенный паспорт с подписью издателя работает локально без секретных ключей, а любой поддельный или вредоносный осколок мгновенно блокируется на входе.",
        "voice2": "Проверяй код скилл траст плэйн на Гитхаб. Ссылка перед тобой.",
    },
    {
        "ep": "05",
        "slug": "dup-tiktok-05-dup-lab",
        "repo": "dup-lab",
        "tag": "ГЛАВА 05 / 08 · DUP-LAB",
        "title": "Портал запуска одной командой",
        "badge": "ГЛАВА 05 / 08 · DUP-LAB · ONE-COMMAND PORTAL",
        "shot1": "cinema/dup_05_dup_lab_hd.mp4",
        "shot2": "cinema/u_05_lab_action.mp4",
        "voice1": "Дни ручной настройки окружения сжимаются в секунды. Пятое ядро Вселенной ДАП Лабс — дап лаб. Одна команда в терминале запускает цепную реакцию на Windows, Linux и macOS: автоматически разворачивается рабочая среда, подключаются проверенные навыки и оживает локальный Эм Си Пи узел без утечки секретов.",
        "voice2": "Единый вход во всю экосистему — на Гитхаб. Ссылка на экране.",
    },
    {
        "ep": "06",
        "slug": "dup-tiktok-06-policy-gate",
        "repo": "dup-policy-gate",
        "tag": "ГЛАВА 06 / 08 · DUP-POLICY-GATE",
        "title": "Детерминированный фаервол",
        "badge": "ГЛАВА 06 / 08 · DUP-POLICY-GATE · HARD FIREWALL",
        "shot1": "cinema/dup_06_policy_gate_hd.mp4",
        "shot2": "cinema/u_06_policy_action.mp4",
        "voice1": "Последний рубеж защиты реального капитала — шестое ядро полиси гейт. Когда поток рискованных ордеров с плечом и фьючерсами несётся к рынку, титановый замок захлопывается и гасит каждую опасную попытку. Проходит только выверенный спотовый луч в пределах жёстких лимитов, оставляя неизменяемую печать аудита.",
        "voice2": "Правила сильнее эмоций. Исходный код полиси гейт открыт на Гитхаб.",
    },
    {
        "ep": "07",
        "slug": "dup-tiktok-07-experimental",
        "repo": "dup-protocol-experimental",
        "tag": "ГЛАВА 07 / 08 · DUP-PROTOCOL-EXPERIMENTAL",
        "title": "Изолированный R&D реактор",
        "badge": "ГЛАВА 07 / 08 · EXPERIMENTAL · R&D SANDBOX",
        "shot1": "cinema/dup_07_experimental_hd.mp4",
        "shot2": "cinema/u_07_experimental_action.mp4",
        "voice1": "Никаких экспериментов на живой сети. Седьмое ядро ДАП Лабс — протокол экспериментал, изолированный реактор будущего. Внутри защитного купола смарт-контракты И Ви Эм выдерживают ураган нативного фаззинга и реоргов, а опытная защита от дальних атак доказывает свою прочность прежде, чем попадёт в промышленную основу.",
        "voice2": "Открытая лаборатория будущего — ссылка на Гитхаб прямо на экране.",
    },
    {
        "ep": "08",
        "slug": "dup-tiktok-08-evidence-graph",
        "repo": "dup-evidence-graph",
        "tag": "ГЛАВА 08 / 08 · DUP-EVIDENCE-GRAPH",
        "title": "Машинная честность на диске",
        "badge": "ГЛАВА 08 / 08 · EVIDENCE GRAPH · DISK PROOF",
        "shot1": "cinema/dup_08_evidence_graph_hd.mp4",
        "shot2": "cinema/u_08_evidence_action.mp4",
        "voice1": "Сколько проектов обещают готовность без единого доказательства? Восьмое ядро ДАП Лабс — эвиденс граф, верховный судья инженерной честности. Золотой сканер сверяет каждое заявление с запечатанным паком тестов и сорокавосьмичасового прогона на диске. Пустой зелёный пузырь без фактов разбивается в пыль за долю секунды.",
        "voice2": "Все восемь глав и пятнадцать репозиториев ждут тебя на Гитхаб Грювер восемьдесят семь.",
    },
]


def write_deck(r: dict) -> Path:
    deck = {
        "slug": r["slug"],
        "lang": "ru",
        "brand": "DUP LABS",
        "director_preset": "cinema_cosmos",
        "theme": "quantum_ledger",
        "aspect": "9:16",
        "width": 1080,
        "height": 1920,
        "burn_captions": True,
        "caption_style": "karaoke",
        "transition_style": "fade",
        "transition_frames": 15,
        "sfx_enabled": True,
        "sfx_volume": 0.16,
        "background": {"enabled": False, "provider": "pixabay"},
        "music": {
            "enabled": True,
            "file": "atlasaudio-epic-emotional-640150.mp3",
            "volume": 0.12,
            "duck_db": -10.5,
        },
        "voice": {"lang": "ru", "speaker": "eugene", "rate": "86%", "mode": "single"},
        "slides": [
            {
                "id": f"tt{r['ep']}_main",
                "type": "cinema_clip",
                "tag": r["tag"],
                "title": r["title"],
                "cinema": {
                    "badge": r["badge"],
                    "grade": "vivid",
                    "crossfade_frames": 15,
                    "loop": True,
                    "shots": [
                        {"src": r["shot1"], "duration_sec": 10.5, "playback_rate": 1.0, "zoom": 1.03},
                        {"src": r["shot2"], "duration_sec": 12.0, "playback_rate": 1.0, "zoom": 1.03},
                    ],
                },
                "voice_text": r["voice1"],
            },
            {
                "id": f"tt{r['ep']}_outro",
                "type": "cinema_clip",
                "tag": f"GITHUB.COM/GRUVER87/{r['repo'].upper()}",
                "title": r["repo"],
                "cinema": {
                    "badge": "",
                    "grade": "none",
                    "crossfade_frames": 12,
                    "loop": True,
                    "shots": [
                        {"src": f"cinema/tt_outro_{r['ep']}.mp4", "duration_sec": 6.0, "playback_rate": 1.0, "zoom": 1.0},
                    ],
                },
                "voice_text": r["voice2"],
            },
        ],
    }
    p = DECKS / f"{r['slug']}.json"
    p.write_text(json.dumps(deck, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return p


def smooth_pass(mp4: Path) -> None:
    """Broadcast profile for vertical teasers (shared with build_deck; item 3). Fail-closed on error."""
    from broadcast_encode import broadcast_encode  # noqa: E402

    broadcast_encode(mp4, maxrate="10M", bufsize="20M")


def main():
    only = set(sys.argv[1:])
    for r in REELS:
        if only and r["ep"] not in only:
            continue
        deck_path = write_deck(r)
        print(f"\n=== [{r['ep']}/08] Building {r['slug']} ===", flush=True)
        res = subprocess.run(
            [sys.executable, "scripts/build_deck.py", str(deck_path), "--render", "--offline-only", "--overwrite", "--crf", "19"],
            cwd=str(REPO),
        )
        if res.returncode != 0:
            raise SystemExit(f"build_deck failed on {r['slug']} (rc={res.returncode})")
        mp4 = OUT / f"{r['slug']}.mp4"
        raw_mb = mp4.stat().st_size / (1024 * 1024)
        smooth_pass(mp4)
        new_mb = mp4.stat().st_size / (1024 * 1024)
        print(f"=== [{r['ep']}/08] DONE {mp4.name}: {raw_mb:.1f} MB -> {new_mb:.1f} MB (9:16 smooth H.264 High@L4.1) ===", flush=True)


if __name__ == "__main__":
    main()
