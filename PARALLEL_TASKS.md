# Параллельные задачи — Living VN

Подготовлено 2026-09-28. Две задачи, две непересекающиеся группы файлов, чтобы агенты
работали одновременно без конфликтов.

---

## Общие правила для обоих агентов

**Единственный технический запрет — одновременный запуск Ren'Py.** Один `renpy.sh` пишет
`.rpyc` и `log.txt` общей директории: два процесса портят друг другу компиляцию.

```
# перед запуском любой команды с renpy.sh:
if [ -e /tmp/livingvn.lock ]; then sleep 15; fi   # ждать, пока не освободится
touch /tmp/livingvn.lock
trap 'rm -f /tmp/livingvn.lock' EXIT
timeout 600 /home/alexius/.local/share/renpy/renpy-8.3.7-sdk/renpy.sh . lint
rm -f /tmp/livingvn.lock
```

Команды проверки (общие):

```bash
python3 tools/validate_project.py
python3 tools/smoke_test_layout.py
python3 tools/smoke_test_assets.py
python3 tools/smoke_test_cannibalism.py
python3 tools/smoke_test_logic.py
python3 tools/smoke_test_importer.py
python3 tools/smoke_test_story_parser.py
python3 tools/smoke_test_story_flow.py
bash tools/build_release.sh          # только если задача требует пересборки
```

**Что нельзя трогать ни одному агенту** — это только что исправлено и проверяется прямо
сейчас основной линией:

- `game/story_generating.rpy` (класс `StoryPollAction`) — там была найдена и исправлена
  ошибка: `timer action` возвращал объект `Return` вместо его значения, из-за чего игра
  получала `"wait"` вместо `"done"` и **выбрасывала ответ DeepSeek в мусор**, хотя модель
  отвечала корректно. Строка 42 теперь `return Return(story_wait_take())()`.
- `game/engine.py` — функции `_call_story_screen`, `_wait_for_story_screen`,
  `story_world_request`, `story_wait_take`, `story_wait_tick`.
- `game/story_pipeline.py`, `game/story_chapter.py`, `game/prompts_story.py`,
  `game/ai_client.py`, `game/ai_provider.py`.

Если задача требует правки в этих файлах — остановись и сообщи, не чини молча.

**Контекст состояния:**
- Lint чистый, все smoke-тесты зелёные.
- Прокси DeepSeek работает: `http://127.0.0.1:9655/v1`, модель `deepseek-chat`
  (DeepSeek-V4-Flash, non-thinking). Проверено: возвращает корректный мир
  (персонажи с характером/целями/секретами) примерно за 3–4 секунды.
- Локальная модель: `http://localhost:1234/v1`, модель `qwen/qwen3-8b` — **медленная**,
  использовать только точечно, не подряд и не в циклах.
- Импортированные SAO/DDLC-ассеты помечены `third_party=true`, `redistributable=false` —
  это локальная сборка, публично распространять нельзя.

---

## Агент ОГУРЕЦ — окно и интерфейс под 720p / 1080p / 1440p

### Файлы (только эти)

- `game/options.rpy`
- `game/vn_layout.py`
- `game/vn_styles.rpy`
- `tools/smoke_test_layout.py`
- при необходимости: `game/screens.rpy` — **только** блоки с `vn_panel*` / авторазмеры

### Текущее состояние

- `config.screen_width = 1280`, `config.screen_height = 720` в `game/options.rpy`.
- Блок настройки `config.window` был **удалён** — эксперимент с `config.window = (1920, 1080)`
  на init дал окно 1229×691 (артефакт масштабирования), поэтому его откатили.
- `renpy.get_display_info()` на init возвращает `None` (видно в `log.txt`: `Display Info: None`),
  то есть на этапе разбора скрипта физический экран ещё не известен.
- `game/vn_layout.py` уже считает пропорции от `config.screen_width/height` и содержит
  `fit_window()` — но этот вызов **никуда не подключён**.
- `game/vn_styles.rpy` на init вычисляет store-переменные из размеров конфига.
- `tools/smoke_test_layout.py` проходит для 1024×600, 1280×720, 1366×768, 1920×1080,
  2560×1440, 3440×1440 — это проверка **математики вёрстки**, а не реального окна.

### Задача

Сделать, чтобы игра реально открывалась и выглядела правильно на трёх разрешениях:
1280×720, 1920×1080, 2560×1440.

1. Найти поддерживаемый Ren'Py 8.3.7 способ подстроить окно под реальный экран.
   Варианты, которые стоит проверить в этом порядке:
   - запрос экрана после инициализации дисплея (`renpy.get_screen_size()` /
     `renpy.get_physical_size()` в лейбле при старте) и `renpy.set_physical_size()` /
     `renpy.set_window_size()`;
   - `config.window` в правильном месте (не на init) и с учётом DPI/масштабирования;
   - переключение виртуального разрешения под экран, если UI от этого не ломается.
   Решение не предопределено — нужно проверить, что реально открывается.
2. Сохранить фирменный VN-стиль: тёмные панели, золотые акценты, шрифт Noto, полноэкранные
   сцены без чёрных полей и без обрезанных кнопок.
3. Текст и кнопки не должны «уезжать» из панелей на 1440p.

### Проверка

В каждом разрешении — не только числа:

```bash
touch /tmp/livingvn.lock
timeout 600 /home/alexius/.local/share/renpy/renpy-8.3.7-sdk/renpy.sh . lint
grep -E "Screen sizes|primary display" log.txt
rm -f /tmp/livingvn.lock
python3 tools/smoke_test_layout.py
python3 tools/validate_project.py
```

Для визуальной проверки: сними экран (`renpy.screenshot("/tmp/ogurec_NNNx.png")` из
временного лейбла) и посмотри на картинку глазами — панели, поля, кнопки, диалог.

### Критерий готовности

- `renpy.sh . lint` без ошибок.
- Все три разрешения дают корректное окно и не ломают вёрстку (есть скриншоты).
- `smoke_test_layout.py` зелёный, `validate_project.py` зелёный.
- В `game/options.rpy` не осталось закомментированного мёртвого кода экспериментов.

---

## Агент НИМЫЙ — чёрный placeholder неизвестного персонажа

### Файлы (только эти)

- `game/world.py`
- `game/assets.py`
- `game/images/char_demo.png` (заменить) и новые файлы `game/images/char_*.png`
- `game/engine.py` — **только строка с `fallback = "images/char_demo.png"` (≈615)**
- `BUILD_STATUS.md`
- при необходимости: `tools/smoke_test_assets.py`

### Текущее состояние

- `game/images/char_demo.png` — чёрный квадрат-заглушка для персонажа, у которого нет
  спрайта.
- Подстановки:
  - `game/engine.py:615` — `fallback = "images/char_demo.png"`;
  - `game/world.py:29-31` — эмоции демо-персонажей (`neutral/happy/sad`);
  - `game/world.py:43`, `game/world.py:53` — `visual.states`;
  - `game/assets.py:54` — `DEMO_SPRITE = "images/char_demo.png"`.
- Когда персонажа не находит каталог, игрок видит чёрный прямоугольник в кадре —
  это визуальный брак, а не «работает как задумано».

### Задача

Убрать чёрный квадрат из игры. Два допустимых результата (выбери сам, аргументируй):

1. Нарисовать приличную заглушку силуэта/карточки персонажа и положить её на место;
2. Сделать корректное поведение без картинки: имя персонажа, нейтральная подложка,
   никакой пустоты — то есть unknown-персонаж рисуется оформленно, а не квадратом.

Обязательно:

- демо-мир в `game/world.py` не должен содержать ссылок на отсутствующие/пустые файлы;
- если меняешь формат записей — обнови `tools/smoke_test_assets.py`, чтобы тест это ловил;
- эмоции у демо-персонажа (`neutral/happy/sad`) должны давать визуально различимый
  результат или честно показывать одну и ту же заглушку, но не чёрный прямоугольник.

### Проверка

```bash
touch /tmp/livingvn.lock
timeout 600 /home/alexius/.local/share/renpy/renpy-8.3.7-sdk/renpy.sh . lint
rm -f /tmp/livingvn.lock
python3 tools/smoke_test_assets.py
python3 tools/validate_project.py
python3 tools/smoke_test_logic.py
```

Визуально: запусти игру, дойди до реплики с неизвестным персонажем, сними экран и
посмотри глазами.

### Документация

Допиши в `BUILD_STATUS.md`:

- что сделано по placeholder'у (и что именно заменено);
- что линия story/AI получила фикс возврата с экрана: `StoryPollAction` теперь возвращает
  значение, а не объект `Return`; до этого игра отбрасывала ответ модели, хотя DeepSeek
  отвечал корректно (проверено на прокси `127.0.0.1:9655`);
- что окно под 720p/1080p/1440p делает Огурец — отрази статус честно, без приукрашивания.

Пиши только то, что подтверждено запуском или тестом. Непроверенное помечай явно.

### Критерий готовности

- Чёрного квадрата в игре больше нет (есть скриншот).
- Все перечисленные тесты зелёные, lint чистый.
- `BUILD_STATUS.md` обновлён и не содержит утверждений, которых нет в коде.

---

## Порядок согласования

1. Каждый агент берёт **свою** группу файлов и не выходит за неё.
2. Запуск `renpy.sh` только под lock-файлом — по одному.
3. Финальный общий прогон всех тестов и пересборку дистрибутива делает основная линия,
   после того как оба агента сообщат о готовности.
