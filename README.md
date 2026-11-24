# DUP Presenter

**Declarative 3D Product Presentation Engine** (JSON deck → local offline Silero v4 Russian TTS → 3D Remotion slides → 1080p MP4).

Создаёт полноценные продуктовые 3D-презентации с кодом, живыми скриншотами, вращающимся 3D-кубом, локальной нейроозвучкой (48 кГц) и фоновой подложкой — **без редактирования React-кода**.

## Как это работает

```text
decks/dup_labs.json
   │
   ▼  python scripts/build_deck.py decks/dup_labs.json --render
1. Fail-closed валидация (схема, speaker, наличие всех скриншотов)
2. Локальный Silero v4 TTS (48 кГц, SSML) + 4-аккордная ambient-подложка
3. Авторасчёт длительности каждого слайда → src/generated/deck_resolved.json
4. Проверка типов (tsc --noEmit) + рендер 1080p MP4 → out/<slug>.mp4
```

## Поддерживаемые шаблоны слайдов (`type`)

- `hero_3d` — титульный слайд с градиентом, бейджами и вращающимся 3D-кубом.
- `code_split` — split-screen: слева тезисы, справа 3D-окно кода с построчной анимацией.
- `screen_split` — split-screen: слева тезисы, справа 3D-слайдшоу реальных скриншотов.
- `outro_3d` — финальный слайд со ссылкой, бейджами репозиториев и 3D-кубом.

## Быстрый старт

```powershell
# Собрать озвучку + отрендерить MP4 одной командой
python scripts/build_deck.py decks/dup_labs.json --render

# Открыть интерактивный предпросмотр
npm run dev
```

## Лицензии сторонних компонентов

- **Remotion**: бесплатная лицензия для физлиц и команд до 3 человек ([remotion.dev/docs/license/pricing](https://www.remotion.dev/docs/license/pricing)).
- **Silero TTS v4**: локальная офлайн-модель (скачивается автоматически в `models/silero/v4_ru.pt`).
