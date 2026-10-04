## Первая глава, написанная руками: то, что играется без модели вообще.
##
## Метка `story_chapter_one` ставит рукописный мир и отдаёт его движку. Дальше всё происходит
## в обычном `play`: тот же буфер, та же отрисовка, те же ассеты. Отдельного пути отрисовки
## у рукописи нет, и это не экономия, а проверка: если сгенерированная сцена ломает игру,
## ломает и эта.
##
## Спрос на запуск главы стоит один раз за установку, и только когда модель не настроена.
## У кого модель есть, тот её и запускает; показывать ему кнопку «а вдруг без модели»
## значит предлагать отказ от того, что работает.

default persistent.story_chapter_offered = False
default story_ext_name = ""


label story_chapter_one:
    $ story_start_chapter()
    jump play


## Глава кончилась: сцена остановилась, сюжет писать некому и нечем. Это не ошибка и не
## заглушка -- это конец текста, и он должен выглядеть как конец текста, а не как зависшая
## игра.
label story_chapter_finished:
    $ renpy.hide_screen("story_generating")
    scene
    $ renpy.notify("Первая глава окончена")
    $ renpy.say(None, "Письмо без адреса лежит в кармане, и двадцатое число уже позади.")
    $ renpy.say(None, "Дальше сюжет продолжит модель — если она настроена. Иначе эту главу "
                      "можно перечитать: она никуда не делась.")

    menu:
        "Начать первую главу заново":
            jump story_chapter_one
        "В главное меню":
            $ renpy.full_restart()

    return


## Один раз за установку, и только без модели: игроку предлагают то, что уже работает.
label splashscreen:
    if not ai_configured() and not persistent.story_chapter_offered:
        $ persistent.story_chapter_offered = True
        $ renpy.call_screen("story_offer_chapter")
    return


## Готовая история из data/story_*.json (Сосны, SAO). Файл проверяется до запуска: нет файла или он
## сломан -- игра честно говорит об этом и предлагает написанную главу, а не падает.
label story_external_start:
    $ story_ext_ok = store.story_start_external(story_ext_name)
    if not story_ext_ok:
        $ renpy.notify("История не найдена или повреждена")
        jump story_chapter_one
    jump play

label story_external_finished:
    $ renpy.hide_screen("story_generating")
    scene
    $ renpy.say(None, "История окончена.")
    menu:
        "В главное меню":
            $ renpy.full_restart()
    return
