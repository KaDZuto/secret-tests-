## The waiting screen, and the only place a request to the model is waited for.
##
## The request itself happens in a worker thread (`story_pipeline`), so this screen has nothing
## to block on: a `timer` reads the job's state a few times a second, and the game keeps
## drawing, the quick menu keeps working and ESC opens the save menu over it. A local 8B model
## on a laptop needs one to three minutes for a bundle, and a screen that could not be left for
## that long would not be a feature, it would be a bug.
##
## The failure case is the second half of the screen. When the model cannot be reached, or
## answers something unreadable, the reason and the next step are shown in full and the player
## decides: try again, play the hand-written chapter, or leave. Nothing here falls back to a
## silent stub -- a story the game made up behind the player's back is indistinguishable from a
## game that has no story at all.

default story_phase = "idle"
default story_title = "Модель пишет сюжет"
default story_error = ""
default story_advice = ""
default story_detail = ""
default story_kind = ""
default story_elapsed = 0.0
default story_attempt = 1
default story_progress = 0.0
default story_timeout = 120
default story_timeout_text = "120 с"
default story_elapsed_text = "0 с"
default story_payload = []


init python:
    class StoryPollAction(Action):
        """Poll the job and leave the screen only when there is something to return.

        The check is inside the action because a screen expression is evaluated while the screen
        is being built, so a `Return(story_wait_take())` written in the screen would take the
        result on the very first frame -- before the model has answered anything.
        """

        def __call__(self):
            ## The action has to be *called*. A `timer` hands the interaction whatever this
            ## returns, so returning the `Return` object itself passes the object upward and
            ## the screen closes with a value nobody can read: the request had answered, the
            ## answer was taken, and the game still reported "the request ended without an
            ## answer". `Return("done")()` evaluates to "done", which is what the caller wants.
            story_wait_tick()
            if store.story_phase == "done":
                return Return(story_wait_take())()
            return None

    story_poll = StoryPollAction()


screen story_generating():
    modal True

    timer 0.2 repeat True action story_poll

    ## The menu is the player's way out of a two-minute wait, so it is bound to the same key the
    ## rest of the game uses and it is not modal over the save screen itself.
    key "K_ESCAPE" action ShowMenu("save")

    add Solid("#e9f4ece6")

    frame:
        style "vn_box"
        xalign 0.5
        yalign 0.5
        xsize 940
        vbox:
            spacing 12

            text story_title style "vn_title" size 30

            if story_phase == "running":
                text "Игра не зависла: сцена будет показана, как только модель ответит. Можно открыть меню по ESC и вернуться." style "vn_hint"

                frame:
                    style "vn_summary"
                    vbox:
                        spacing 4
                        hbox:
                            spacing 16
                            text "Прошло" style "vn_sum_label" xsize 120
                            text "[story_elapsed_text]" style "vn_sum_value"
                            text "Попытка" style "vn_sum_label" xsize 120 xalign 1.0
                            text "[story_attempt]" style "vn_sum_value" xalign 1.0
                        bar:
                            style "vn_bar"
                            xfill True
                            ysize 10
                            value story_progress
                        text "Таймаут в настройках: [story_timeout_text]" style "vn_footer"

                textbutton "Не ждать — читать написанную главу" action [Function(story_job_cancel), Return("offline")]
                textbutton "В главное меню" action MainMenu()

            elif story_phase == "error":
                text "Модель не ответила или ответ не разобрался." style "vn_section"

                frame:
                    style "vn_summary"
                    vbox:
                        spacing 6
                        text story_error style "vn_sum_value" xalign 0.0
                        if story_advice:
                            text ("Что делать: " + story_advice) style "vn_sum_label" xalign 0.0

                textbutton "Повторить запрос" action Return("retry")
                textbutton "Читать написанную главу без ИИ" action Return("offline")
                textbutton "В главное меню" action MainMenu()

            elif story_phase == "done":
                ## The model answered and the steps are already in the buffer. The screen is on
                ## its way out; this is what the last frame before that looks like.
                text "Сцена готова." style "vn_sum_value" xalign 0.0

            else:
                ## No request is in flight and none was answered. This is the state the
                ## screen starts in, so it says what to do rather than accusing the model.
                text "Запрос не запущен." style "vn_sum_value" xalign 0.0
                text "Нажми «Повторить запрос», чтобы отправить его заново." style "vn_hint" xfill True
                textbutton "Повторить запрос" action Return("retry")
                textbutton "Читать написанную главу без ИИ" action Return("offline")
                textbutton "В главное меню" action MainMenu()


## The offer on first launch, for a player with no model running.
##
## A game that can only be played after an endpoint is configured is a demo of a setup wizard,
## so the written chapter is offered once at the start -- only while no model is configured,
## because a player who has a model does not need a fallback they never asked for.

screen story_offer_chapter():
    modal True
    add Solid("#e9f4ecec")
    frame:
        style "vn_box"
        xalign 0.5
        yalign 0.5
        xsize 860
        vbox:
            spacing 12
            text "Летний лагерь" style "vn_title" size 34
            text "Модель не настроена, но играть уже можно: есть написанная первая глава — около двух часов, все девять выражений Асуны, фоны из каталога и выборы, которые меняют ход истории." style "vn_hint"
            text "Если хочешь, чтобы сюжет писала нейросеть, поставь адрес и модель в настройках ИИ." style "vn_hint"
            textbutton "Играть первую главу" action Start("story_chapter_one")
            textbutton "В главное меню" action Return()
