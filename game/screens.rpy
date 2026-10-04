default creator_mode = "brief"
default creator_description = "Ты перевёлся в Академию в начале осени и встретил Асуну у старого корпуса. В её руках — запечатанный дневник, а в расписании занятий — аудитория, которой нет на плане здания."
default creator_json_path = ""
default creator_music_paths = ""
default creator_character_count = "3"
default creator_title = "Академия: Тайна старого корпуса"
default creator_genre = "мистика, школьная повседневность, детектив"
default creator_tone = "светлая осенняя атмосфера с нарастающей тайной"
default creator_player_name = "Игрок"
default persistent.vn_player_name = ""
default lore_edit_text = ""
default settings_tab = "ai"
default provider_models = []
default provider_models_note = "Модели не загружены"
default provider_test = ""
default asset_browser_tab = "backgrounds"
default asset_preview_id = ""
default profile_new_name = ""
default export_name = "my_world"
default import_world_path = ""
default cannibalism_source_path = ""
default cannibalism_source_name = ""
default cannibalism_scan_result = {}
default cannibalism_assessment = {}
default cannibalism_import_characters = True

init -20 python:
    import vn_settings_schema
    import vn_settings_layout
    import ai_provider
    import vn_assetbrowser
    import settings_status

default persistent.vn_settings = dict(vn_settings_schema.DEFAULTS)

init -10 python:
    # An older save file is missing keys this version added, and `default` cannot
    # repair that, so fill the gaps before any screen can ask for one. `sanitize` then
    # puts every declared key into its declared kind and range, so a hand-edited or
    # half-written save cannot hand a bar or a label a value it cannot use.
    vn_settings_schema.merge_into_persistent()
    vn_settings_schema.sanitize()
    vn_view = vn_settings_schema.view

    if not getattr(persistent, "vn_ai_profiles", None):
        persistent.vn_ai_profiles = {
            name: dict(values) for name, values in ai_provider.BUILTIN_PROFILES.items()
        }
    if not getattr(persistent, "vn_ai_profile", ""):
        persistent.vn_ai_profile = ai_provider.DEFAULT_PROFILE
        ai_provider.apply_profile(ai_provider.DEFAULT_PROFILE)

## The dialogue layer.
##
## This project had no `screen say` at all, so every spoken line was rendered by the
## built-in default with DejaVu Sans and no textbox. The screens below are the VN
## presentation: a translucent band, a name plate on its edge, outlined text, a blinking
## continuation marker and a quick menu on the box border.


################################################################################
## Initialization
################################################################################

init offset = -1


################################################################################
## Styles
################################################################################

style default:
    properties gui.text_properties()
    language gui.language

style input:
    properties gui.text_properties("input", accent=True)
    adjust_spacing False

style hyperlink_text:
    properties gui.text_properties("hyperlink", accent=True)
    hover_underline True

style gui_text:
    properties gui.text_properties("interface")


style button:
    properties gui.button_properties("button")

style button_text is gui_text:
    properties gui.text_properties("button")
    yalign 0.5


style label_text is gui_text:
    properties gui.text_properties("label", accent=True)

style prompt_text is gui_text:
    properties gui.text_properties("prompt")


style bar:
    ysize gui.bar_size
    left_bar Frame("gui/bar/left.png", gui.bar_borders, tile=gui.bar_tile)
    right_bar Frame("gui/bar/right.png", gui.bar_borders, tile=gui.bar_tile)

style vbar:
    xsize gui.bar_size
    top_bar Frame("gui/bar/top.png", gui.vbar_borders, tile=gui.bar_tile)
    bottom_bar Frame("gui/bar/bottom.png", gui.vbar_borders, tile=gui.bar_tile)

style scrollbar:
    ysize gui.scrollbar_size
    base_bar Frame("gui/scrollbar/horizontal_[prefix_]bar.png", gui.scrollbar_borders, tile=gui.scrollbar_tile)
    thumb Frame("gui/scrollbar/horizontal_[prefix_]thumb.png", gui.scrollbar_borders, tile=gui.scrollbar_tile)

style vscrollbar:
    xsize gui.scrollbar_size
    base_bar Frame("gui/scrollbar/vertical_[prefix_]bar.png", gui.vscrollbar_borders, tile=gui.scrollbar_tile)
    thumb Frame("gui/scrollbar/vertical_[prefix_]thumb.png", gui.vscrollbar_borders, tile=gui.scrollbar_tile)

style slider:
    ysize gui.slider_size
    base_bar Frame("gui/slider/horizontal_[prefix_]bar.png", gui.slider_borders, tile=gui.slider_tile)
    thumb "gui/slider/horizontal_[prefix_]thumb.png"

style vslider:
    xsize gui.slider_size
    base_bar Frame("gui/slider/vertical_[prefix_]bar.png", gui.vslider_borders, tile=gui.slider_tile)
    thumb "gui/slider/vertical_[prefix_]thumb.png"


style frame:
    padding gui.frame_borders.padding
    background Frame("gui/frame.png", gui.frame_borders, tile=gui.frame_tile)



################################################################################
## In-game screens
################################################################################


## Say screen ##################################################################
##
## The say screen is used to display dialogue to the player. It takes two
## parameters, who and what, which are the name of the speaking character and
## the text to be displayed, respectively. (The who parameter can be None if no
## name is given.)
##
## This screen must create a text displayable with id "what", as Ren'Py uses
## this to manage text display. It can also create displayables with id "who"
## and id "window" to apply style properties.
##
## https://www.renpy.org/doc/html/screen_special.html#say

screen say(who, what):

    window:
        id "window"

        if who is not None:

            window:
                style "namebox"
                text who id "who"

        text what id "what"

        ## Continuation marker, in the corner of the box.
        if renpy.get_screen("ctc"):
            textbutton "\u25bc":
                action Continue("ctc")
                style "vn_ctc"
                at vn_ctc_blink

        ## The quick menu rides on the textbox edge.
        use quick_menu


    ## If there's a side image, display it above the text. Do not display on the
    ## phone variant - there's no room.
    if not renpy.variant("small"):


screen player_name_input():
    modal True
    add Solid("#e9f4ecec")
    frame:
        style "vn_box"
        xalign 0.5
        yalign 0.5
        xsize 600
        vbox:
            spacing 16
            text "Как тебя зовут?" style "vn_title" size 30
            text "Имя будет использоваться в сценах. Можно пропустить." style "vn_hint"
            input value VariableInputValue("persistent.vn_player_name") length 24 style "vn_input"
            hbox:
                spacing 12
                textbutton "Пропустить" action Return("")
                textbutton "Сохранить" action Return(persistent.vn_player_name)
        add SideImage() xalign 0.0 yalign 1.0


style window is default
style say_label is default
style say_dialogue is default
style say_thought is say_dialogue

style namebox is default
style namebox_label is say_label


## (Dialogue and namebox styles consolidated in vn_styles.rpy)


## Input screen ################################################################
##
## This screen is used to display renpy.input. The prompt parameter is used to
## pass a text prompt in.
##
## This screen must create an input displayable with id "input" to accept the
## various input parameters.
##
## http://www.renpy.org/doc/html/screen_special.html#input

screen input(prompt):
    style_prefix "input"

    window:

        vbox:
            xalign gui.dialogue_text_xalign
            xpos gui.dialogue_xpos
            xsize gui.dialogue_width
            ypos gui.dialogue_ypos

            text prompt style "input_prompt"
            input id "input"

style input_prompt is default

style input_prompt:
    xalign gui.dialogue_text_xalign
    properties gui.text_properties("input_prompt")

style input:
    xalign gui.dialogue_text_xalign
    xmaximum gui.dialogue_width


## Choice screen ###############################################################
##
## This screen is used to display the in-game choices presented by the menu
## statement. The one parameter, items, is a list of objects, each with caption
## and action fields.
##
## http://www.renpy.org/doc/html/screen_special.html#choice

screen choice(items):
    style_prefix "choice"

    vbox:
        xalign 0.5
        yalign 0.52
        xsize min(int(config.screen_width * 0.76), 920)
        spacing 14

        for i in items:
            textbutton i.caption:
                style "choice_button"
                xfill True
                action i.action

    use quick_menu


style choice_vbox is vbox
style choice_button is button
style choice_button_text is button_text

style choice_vbox:
    xalign 0.5
    ypos 270
    yanchor 0.5

    spacing gui.choice_spacing

## (Choice styles consolidated in vn_styles.rpy)


## Quick Menu screen ###########################################################
##
## The quick menu is displayed in-game to provide easy access to the out-of-game
## menus.

screen quick_menu():

    ## Ensure this appears on top of other screens.
    zorder 100

    if quick_menu:

        hbox:
            style_prefix "quick"

            ## Inside the textbox, along its top edge: the usual VN placement.
            xalign 1.0
            ypos 8
            spacing 4

            textbutton _("Назад") action Rollback()
            textbutton _("Лог") action ShowMenu('history')
            textbutton _("Пропуск") action Skip() alternate Skip(fast=True, confirm=True)
            textbutton _("Авто") action Preference("auto-forward", "toggle")
            textbutton _("Скрыть") action Preference("display", "window", "hide")
            textbutton _("Сохр.") action ShowMenu('save')
            textbutton _("Загр.") action ShowMenu('load')
            textbutton _("Настр.") action ShowMenu('settings')


## The quick menu is used from the say and choice screens instead of being a global
## overlay: an overlay is also drawn over menus, so it covered the creator and the
## settings panel, and outside a dialogue it had nothing to sit on.

default quick_menu = True

style quick_button is default
style quick_button_text is button_text

## (Quick menu styles consolidated in vn_styles.rpy)


################################################################################
## Main and Game Menu Screens
################################################################################

## Navigation screen ###########################################################
##
## This screen is included in the main and game menus, and provides navigation
## to other menus, and to start the game.

screen navigation():

    vbox:
        style_prefix "navigation"

        xpos gui.navigation_xpos
        yalign 0.5

        spacing gui.navigation_spacing

        if main_menu:

            textbutton _("Начать") action Start()

        else:

            textbutton _("История") action ShowMenu("history")

            textbutton _("Сохранить") action ShowMenu("save")

        textbutton _("Загрузить") action ShowMenu("load")

        textbutton _("Настройки") action ShowMenu("settings")

        if _in_replay:

            textbutton _("Закончить повтор") action EndReplay(confirm=True)

        elif not main_menu:

            textbutton _("Главное меню") action MainMenu()

        textbutton _("Об игре") action ShowMenu("about")

        if renpy.variant("pc") or (renpy.variant("web") and not renpy.variant("mobile")):

            ## Help isn't necessary or relevant to mobile devices.
            textbutton _("Справка") action ShowMenu("help")

        if renpy.variant("pc"):

            ## The quit button is banned on iOS and unnecessary on Android and Web.
            textbutton _("Выход") action Quit(confirm=not main_menu)


style navigation_button is gui_button
style navigation_button_text is gui_button_text

style navigation_button:
    size_group "navigation"
    properties gui.button_properties("navigation_button")

style navigation_button_text:
    properties gui.text_properties("navigation_button")


## Main Menu screen ############################################################
##
## Used to display the main menu when Ren'Py starts.
##
## http://www.renpy.org/doc/html/screen_special.html#main-menu

screen main_menu():

    ## Replaces any other menu screen.
    tag menu

    add "images/menu_bg.png"

    ## The heroine stands on the right when her art is present; no art, no hole in the layout.
    if renpy.loadable("absorbed/SAO/character_art/asuna/base/pose_01_000_neutral.png"):
        add Transform("absorbed/SAO/character_art/asuna/base/pose_01_000_neutral.png", fit="contain", xysize=(int(config.screen_width * 0.46), config.screen_height - 20)) xalign 0.93 yalign 1.0

    ## Left panel in the Doki Doki manner: the whole height, the title on top, the buttons under it,
    ## all of it inside the screen at any window size (the menu is laid out in virtual pixels).
    frame:
        style "vn_menu_panel"
        xsize int(config.screen_width * 0.36)
        ysize config.screen_height

        vbox:
            xfill True
            yalign 0.5
            spacing 3

            text "[config.name!t]":
                style "vn_title"

            text _("Визуальная новелла, которая пишет себя в процессе игры"):
                style "vn_subtitle"

            null height 18

            textbutton _("Новая игра") action Start("creator") style "vn_menu_button"
            for _name, _title in story_ready_menu():
                textbutton _title action [SetVariable("story_ext_name", _name), Start("story_external_start")] style "vn_menu_button"
            textbutton _("Продолжить") action ShowMenu("load") style "vn_menu_button"
            textbutton _("Настройки") action ShowMenu("settings") style "vn_menu_button"
            textbutton "Проверка эмоций: Асуна" action Start("demo_expression_sheet") style "vn_menu_button_small"
            textbutton "Демо: Асуна" action Start("demo_start") style "vn_menu_button_small"
            textbutton _("Выход") action Quit(confirm=True) style "vn_menu_button"

    text "Ren'Py [renpy.version_only] · AI optional":
        style "vn_footer"
        xpos 24
        yalign 0.99

## Game Menu screen ############################################################
##
## This lays out the basic common structure of a game menu screen. It's called
## with the screen title, and displays the background, title, and navigation.
##
## The scroll parameter can be None, or one of "viewport" or "vpgrid". When
## this screen is intended to be used with one or more children, which are
## transcluded (placed) inside it.

screen game_menu(title, scroll=None):

    style_prefix "game_menu"

    if main_menu:
        add gui.main_menu_background
    else:
        add gui.game_menu_background

    frame:
        style "game_menu_outer_frame"

        hbox:

            ## Reserve space for the navigation section.
            frame:
                style "game_menu_navigation_frame"

            frame:
                style "game_menu_content_frame"

                if scroll == "viewport":

                    viewport:
                        scrollbars "vertical"
                        mousewheel True
                        draggable True
                        pagekeys True

                        side_yfill True

                        vbox:
                            transclude

                elif scroll == "vpgrid":

                    vpgrid:
                        cols 1
                        yinitial 1.0

                        scrollbars "vertical"
                        mousewheel True
                        draggable True
                        pagekeys True

                        side_yfill True

                        transclude

                else:

                    transclude

    use navigation

    textbutton _("Назад"):
        style "return_button"

        action Return()

    label title

    if main_menu:
        key "game_menu" action ShowMenu("main_menu")


style game_menu_outer_frame is empty
style game_menu_navigation_frame is empty
style game_menu_content_frame is empty
style game_menu_viewport is gui_viewport
style game_menu_side is gui_side
style game_menu_scrollbar is gui_vscrollbar

style game_menu_label is gui_label
style game_menu_label_text is gui_label_text

style return_button is navigation_button
style return_button_text is navigation_button_text

style game_menu_outer_frame:
    bottom_padding 30
    top_padding 120

    background "gui/overlay/game_menu.png"

style game_menu_navigation_frame:
    xsize 280
    yfill True

style game_menu_content_frame:
    left_margin 40
    right_margin 20
    top_margin 10

style game_menu_viewport:
    xsize 920

style game_menu_vscrollbar:
    unscrollable gui.unscrollable

style game_menu_side:
    spacing 10

style game_menu_label:
    xpos 50
    ysize 120

style game_menu_label_text:
    size gui.title_text_size
    color gui.accent_color
    yalign 0.5

style return_button:
    xpos gui.navigation_xpos
    yalign 1.0
    yoffset -30


## About screen ################################################################
##
## This screen gives credit and copyright information about the game and Ren'Py.
##
## There's nothing special about this screen, and hence it also serves as an
## example of how to make a custom screen.

screen about():

    tag menu

    predict False

    use game_menu(_("Об игре"), scroll="viewport"):

        style_prefix "about"

        vbox:

            label "[config.name!t]"
            text _("[config.version!t]\n")

            text _("Living VN — движок визуальной новеллы, который разворачивает сцены сам.\n"
                 + "Персонажи, фоны, музыка и Live2D берутся из локального каталога.\n"
                 + "Поглощённые извне ассеты помечены как сторонние и не входят в экспорт мира.")

            null height 15

            text _("\nСделано на {a=https://www.renpy.org/}Ren\u2019Py{/a} [renpy.version_only]")


style about_small:
    size 20
    minwidth 260
    textalign 1.0
    yalign 0.9


## Load and Save screens #######################################################
##
## These screens are responsible for letting the player save the game and load
## it again. Since they share nearly everything in common, both are implemented
## in terms of a third screen, file_slots.
##
## https://www.renpy.org/doc/html/screen_special.html#save https://
## www.renpy.org/doc/html/screen_special.html#load

screen save():

    tag menu

    use file_slots(_("Сохранить"))


screen load():

    tag menu

    use file_slots(_("Загрузить"))


screen file_slots(title):

    default page_name_value = FilePageNameInputValue(pattern=_("Страница {}"), auto=_("Автосохранения"), quick=_("Быстрые сохранения"))

    use game_menu(title):

        fixed:

            ## This ensures the input will get the enter event before any of the
            ## buttons do.
            order_reverse True

            ## The page name, which can be edited by clicking on a button.
            button:
                style "page_label"

                key_events True
                xalign 0.5
                action page_name_value.Toggle()

                input:
                    style "page_label_text"
                    value page_name_value

            ## The grid of file slots.
            grid gui.file_slot_cols gui.file_slot_rows:
                style_prefix "slot"

                xalign 0.5
                yalign 0.5

                spacing gui.slot_spacing

                for i in range(gui.file_slot_cols * gui.file_slot_rows):

                    $ slot = i + 1

                    button:
                        action FileAction(slot)

                        has vbox

                        add FileScreenshot(slot) xalign 0.5

                        text FileTime(slot, format=_("%d.%m.%Y %H:%M"), empty=_("пустой слот")):
                            style "slot_time_text"

                        text FileSaveName(slot):
                            style "slot_name_text"

                        key "save_delete" action FileDelete(slot)

            ## Buttons to access other pages.
            hbox:
                style_prefix "page"

                xalign 0.5
                yalign 1.0

                spacing gui.page_spacing

                textbutton _("<") action FilePagePrevious()
                key "save_page_prev" action FilePagePrevious()

                if config.has_autosave:
                    textbutton _("A") action FilePage("auto")

                if config.has_quicksave:
                    textbutton _("Q") action FilePage("quick")

                ## range(1, 10) gives the numbers from 1 to 9.
                for page in range(1, 10):
                    textbutton "[page]" action FilePage(page)

                textbutton _(">") action FilePageNext()
                key "save_page_next" action FilePageNext()


style page_label is gui_label
style page_label_text is gui_label_text
style page_button is gui_button
style page_button_text is gui_button_text

style slot_button is gui_button
style slot_button_text is gui_button_text
style slot_time_text is slot_button_text
style slot_name_text is slot_button_text

style page_label:
    xpadding 50
    ypadding 3

style page_label_text:
    textalign 0.5
    layout "subtitle"
    hover_color gui.hover_color

style page_button:
    properties gui.button_properties("page_button")

style page_button_text:
    properties gui.text_properties("page_button")

style slot_button:
    properties gui.button_properties("slot_button")

style slot_button_text:
    properties gui.text_properties("slot_button")


## Preferences screen ##########################################################
##
## The preferences screen allows the player to configure the game to better suit
## themselves.
##
## https://www.renpy.org/doc/html/screen_special.html#preferences

screen preferences():

    tag menu

    if renpy.mobile:
        $ cols = 2
    else:
        $ cols = 4

    use game_menu(_("Настройки"), scroll="viewport"):

        vbox:

            hbox:
                box_wrap True

                if renpy.variant("pc") or renpy.variant("web"):

                    vbox:
                        style_prefix "radio"
                        label _("Экран")
                        textbutton _("Окно") action Preference("display", "window")
                        textbutton _("Полный экран") action Preference("display", "fullscreen")

                vbox:
                    style_prefix "check"
                    label _("Пропуск")
                    textbutton _("Непрочитанный текст") action Preference("skip", "toggle")
                    textbutton _("После выбора") action Preference("after choices", "toggle")
                    textbutton _("Переходы") action InvertSelected(Preference("transitions", "toggle"))

                ## Additional vboxes of type "radio_pref" or "check_pref" can be
                ## added here, to add additional creator-defined preferences.

## No translations ship with this game, so the language picker is removed.

            null height (4 * gui.pref_spacing)

            hbox:
                style_prefix "slider"
                box_wrap True

                vbox:

                    label _("Скорость текста")

                    bar value Preference("text speed")

                    label _("Пауза автоперехода")

                    bar value Preference("auto-forward time")

                vbox:

                    if config.has_music:
                        label _("Громкость музыки")

                        hbox:
                            bar value Preference("music volume")

                    if config.has_sound:

                        label _("Громкость звуков")

                        hbox:
                            bar value Preference("sound volume")

                            if config.sample_sound:
                                textbutton _("Проверка") action Play("sound", config.sample_sound)


                    if config.has_voice:
                        label _("Громкость голоса")

                        hbox:
                            bar value Preference("voice volume")

                            if config.sample_voice:
                                textbutton _("Проверка") action Play("voice", config.sample_voice)

                    if config.has_music or config.has_sound or config.has_voice:
                        null height gui.pref_spacing

                        textbutton _("Выключить всё"):
                            action Preference("all mute", "toggle")
                            style "mute_all_button"


style pref_label is gui_label
style pref_label_text is gui_label_text
style pref_vbox is vbox

style radio_label is pref_label
style radio_label_text is pref_label_text
style radio_button is gui_button
style radio_button_text is gui_button_text
style radio_vbox is pref_vbox

style check_label is pref_label
style check_label_text is pref_label_text
style check_button is gui_button
style check_button_text is gui_button_text
style check_vbox is pref_vbox

style slider_label is pref_label
style slider_label_text is pref_label_text
style slider_slider is gui_slider
style slider_button is gui_button
style slider_button_text is gui_button_text
style slider_pref_vbox is pref_vbox

style mute_all_button is check_button
style mute_all_button_text is check_button_text

style pref_label:
    top_margin gui.pref_spacing
    bottom_margin 2

style pref_label_text:
    yalign 1.0

style pref_vbox:
    xsize 225

style radio_vbox:
    spacing gui.pref_button_spacing

style radio_button:
    properties gui.button_properties("radio_button")
    foreground "gui/button/radio_[prefix_]foreground.png"

style radio_button_text:
    properties gui.text_properties("radio_button")

style check_vbox:
    spacing gui.pref_button_spacing

style check_button:
    properties gui.button_properties("check_button")
    foreground "gui/button/check_[prefix_]foreground.png"

style check_button_text:
    properties gui.text_properties("check_button")

style slider_slider:
    xsize 350

style slider_button:
    properties gui.button_properties("slider_button")
    yalign 0.5
    left_margin 10

style slider_button_text:
    properties gui.text_properties("slider_button")

style slider_vbox:
    xsize 450


## History screen ##############################################################
##
## This is a screen that displays the dialogue history to the player. While
## there isn't anything special about this screen, it does have to access the
## dialogue history stored in _history_list.
##
## https://www.renpy.org/doc/html/history.html

screen history():

    tag menu

    ## Avoid predicting this screen, as it can be very large.
    predict False

    use game_menu(_("История"), scroll=("vpgrid" if gui.history_height else "viewport")):

        style_prefix "history"

        for h in _history_list:

            window:

                ## This lays things out properly if history_height is None.
                has fixed:
                    yfit True

                if h.who:

                    label h.who:
                        style "history_name"
                        substitute False

                        ## Take the color of the who text from the Character, if
                        ## set.
                        if "color" in h.who_args:
                            text_color h.who_args["color"]

                $ what = renpy.filter_text_tags(h.what, allow=gui.history_allow_tags)
                text what:
                    substitute False

        if not _history_list:
            label _("История диалогов пуста.")

define gui.history_allow_tags = { "alt", "noalt", "rt", "rb", "art" }

style history_window is empty

style history_name is gui_label
style history_name_text is gui_label_text
style history_text is gui_text

style history_text is gui_text

style history_label is gui_label
style history_label_text is gui_label_text

style history_window:
    xfill True
    ysize gui.history_height

style history_name:
    xpos gui.history_name_xpos
    xanchor gui.history_name_xalign
    ypos gui.history_name_ypos
    xsize gui.history_name_width

style history_name_text:
    min_width gui.history_name_width
    textalign gui.history_name_xalign

style history_text:
    xpos gui.history_text_xpos
    ypos gui.history_text_ypos
    xanchor gui.history_text_xalign
    xsize gui.history_text_width
    min_width gui.history_text_width
    textalign gui.history_text_xalign
    layout ("subtitle" if gui.history_text_xalign else "tex")

style history_label:
    xfill True

style history_label_text:
    xalign 0.5


## Help screen #################################################################
##
## A screen that gives information about key and mouse bindings. It uses other
## screens (keyboard_help, mouse_help, and gamepad_help) to display the actual
## help.

screen help():

    tag menu

    default device = "keyboard"

    use game_menu(_("Справка"), scroll="viewport"):

        style_prefix "help"

        vbox:
            spacing 15

            hbox:

                textbutton _("Клавиатура") action SetScreenVariable("device", "keyboard")
                textbutton _("Мышь") action SetScreenVariable("device", "mouse")

                if GamepadExists():
                    textbutton _("Геймпад") action SetScreenVariable("device", "gamepad")

            if device == "keyboard":
                use keyboard_help
            elif device == "mouse":
                use mouse_help
            elif device == "gamepad":
                use gamepad_help


screen keyboard_help():

    hbox:
        label _("Enter")
        text _("Advances dialogue and activates the interface.")

    hbox:
        label _("Space")
        text _("Advances dialogue without selecting choices.")

    hbox:
        label _("Arrow Keys")
        text _("Navigate the interface.")

    hbox:
        label _("Escape")
        text _("Accesses the game menu.")

    hbox:
        label _("Ctrl")
        text _("Skips dialogue while held down.")

    hbox:
        label _("Tab")
        text _("Toggles dialogue skipping.")

    hbox:
        label _("Page Up")
        text _("Rolls back to earlier dialogue.")

    hbox:
        label _("Page Down")
        text _("Rolls forward to later dialogue.")

    hbox:
        label "H"
        text _("Hides the user interface.")

    hbox:
        label "S"
        text _("Takes a screenshot.")

    hbox:
        label "V"
        text _("Toggles assistive {a=https://www.renpy.org/l/voicing}self-voicing{/a}.")

    hbox:
        label "Shift+A"
        text _("Opens the accessibility menu.")


screen mouse_help():

    hbox:
        label _("Left Click")
        text _("Advances dialogue and activates the interface.")

    hbox:
        label _("Middle Click")
        text _("Hides the user interface.")

    hbox:
        label _("Right Click")
        text _("Accesses the game menu.")

    hbox:
        label _("Mouse Wheel Up")
        text _("Rolls back to earlier dialogue.")

    hbox:
        label _("Mouse Wheel Down")
        text _("Rolls forward to later dialogue.")


screen gamepad_help():

    hbox:
        label _("Right Trigger\nA/Bottom Button")
        text _("Advances dialogue and activates the interface.")

    hbox:
        label _("Left Trigger\nLeft Shoulder")
        text _("Rolls back to earlier dialogue.")

    hbox:
        label _("Right Shoulder")
        text _("Rolls forward to later dialogue.")

    hbox:
        label _("D-Pad, Sticks")
        text _("Navigate the interface.")

    hbox:
        label _("Start, Guide")
        text _("Accesses the game menu.")

    hbox:
        label _("Y/Top Button")
        text _("Hides the user interface.")

    textbutton _("Откалибровать") action GamepadCalibrate()


style help_button is gui_button
style help_button_text is gui_button_text
style help_label is gui_label
style help_label_text is gui_label_text
style help_text is gui_text

style help_button:
    properties gui.button_properties("help_button")
    xmargin 8

style help_button_text:
    properties gui.text_properties("help_button")

style help_label:
    xsize 250
    right_padding 20

style help_label_text:
    size gui.text_size
    xalign 1.0
    textalign 1.0



################################################################################
## Additional screens
################################################################################


## Confirm screen ##############################################################
##
## The confirm screen is called when Ren'Py wants to ask the player a yes or no
## question.
##
## http://www.renpy.org/doc/html/screen_special.html#confirm

screen confirm(message, yes_action, no_action):

    ## Ensure other screens do not get input while this screen is displayed.
    modal True

    zorder 200

    style_prefix "confirm"

    add "gui/overlay/confirm.png"

    frame:

        vbox:
            xalign .5
            yalign .5
            spacing 30

            label _(message):
                style "confirm_prompt"
                xalign 0.5

            hbox:
                xalign 0.5
                spacing 100

                textbutton _("Да") action yes_action
                textbutton _("Нет") action no_action

    ## Right-click and escape answer "no".
    key "game_menu" action no_action


style confirm_frame is gui_frame
style confirm_prompt is gui_prompt
style confirm_prompt_text is gui_prompt_text
style confirm_button is gui_medium_button
style confirm_button_text is gui_medium_button_text

style confirm_frame:
    background Frame([ "gui/confirm_frame.png", "gui/frame.png"], gui.confirm_frame_borders, tile=gui.frame_tile)
    padding gui.confirm_frame_borders.padding
    xalign .5
    yalign .5

style confirm_prompt_text:
    textalign 0.5
    layout "subtitle"

style confirm_button:
    properties gui.button_properties("confirm_button")

style confirm_button_text:
    properties gui.text_properties("confirm_button")


## Skip indicator screen #######################################################
##
## The skip_indicator screen is displayed to indicate that skipping is in
## progress.
##
## https://www.renpy.org/doc/html/screen_special.html#skip-indicator

screen skip_indicator():

    zorder 100
    style_prefix "skip"

    frame:

        hbox:
            spacing 6

            text _("Пропуск")

            text "▸" at delayed_blink(0.0, 1.0) style "skip_triangle"
            text "▸" at delayed_blink(0.2, 1.0) style "skip_triangle"
            text "▸" at delayed_blink(0.4, 1.0) style "skip_triangle"


## This transform is used to blink the arrows one after another.
transform delayed_blink(delay, cycle):
    alpha .5

    pause delay

    block:
        linear .2 alpha 1.0
        pause .2
        linear .2 alpha 0.5
        pause (cycle - .4)
        repeat


style skip_frame is empty
style skip_text is gui_text
style skip_triangle is skip_text

style skip_frame:
    ypos gui.skip_ypos
    background Frame("gui/skip.png", gui.skip_frame_borders, tile=gui.frame_tile)
    padding gui.skip_frame_borders.padding

style skip_text:
    size gui.notify_text_size

style skip_triangle:
    ## We have to use a font that has the BLACK RIGHT-POINTING SMALL TRIANGLE
    ## glyph in it.
    font "DejaVuSans.ttf"


## Notify screen ###############################################################
##
## The notify screen is used to show the player a message. (For example, when
## the game is quicksaved or a screenshot has been taken.)
##
## https://www.renpy.org/doc/html/screen_special.html#notify-screen

screen notify(message):

    zorder 100
    style_prefix "notify"

    frame at notify_appear:
        text "[message!tq]"

    timer 3.25 action Hide('notify')


transform notify_appear:
    on show:
        alpha 0
        linear .25 alpha 1.0
    on hide:
        linear .5 alpha 0.0


style notify_frame is empty
style notify_text is gui_text

style notify_frame:
    ypos gui.notify_ypos

    background Frame("gui/notify.png", gui.notify_frame_borders, tile=gui.frame_tile)
    padding gui.notify_frame_borders.padding

style notify_text:
    properties gui.text_properties("notify")


## NVL screen ##################################################################
##
## This screen is used for NVL-mode dialogue and menus.
##
## http://www.renpy.org/doc/html/screen_special.html#nvl


screen nvl(dialogue, items=None):

    window:
        style "nvl_window"

        has vbox:
            spacing gui.nvl_spacing

        ## Displays dialogue in either a vpgrid or the vbox.
        if gui.nvl_height:

            vpgrid:
                cols 1
                yinitial 1.0

                use nvl_dialogue(dialogue)

        else:

            use nvl_dialogue(dialogue)

        ## Displays the menu, if given. The menu may be displayed incorrectly if
        ## config.narrator_menu is set to True.
        for i in items:

            textbutton i.caption:
                action i.action
                style "nvl_button"

    add SideImage() xalign 0.0 yalign 1.0


screen nvl_dialogue(dialogue):

    for d in dialogue:

        window:
            id d.window_id

            fixed:
                yfit gui.nvl_height is None

                if d.who is not None:

                    text d.who:
                        id d.who_id

                text d.what:
                    id d.what_id


## This controls the maximum number of NVL-mode entries that can be displayed at
## once.
define config.nvl_list_length = 6

style nvl_window is default
style nvl_entry is default

style nvl_label is say_label
style nvl_dialogue is say_dialogue

style nvl_button is button
style nvl_button_text is button_text

style nvl_window:
    xfill True
    yfill True

    background "gui/nvl.png"
    padding gui.nvl_borders.padding

style nvl_entry:
    xfill True
    ysize gui.nvl_height

style nvl_label:
    xpos gui.nvl_name_xpos
    xanchor gui.nvl_name_xalign
    ypos gui.nvl_name_ypos
    yanchor 0.0
    xsize gui.nvl_name_width
    min_width gui.nvl_name_width
    textalign gui.nvl_name_xalign

style nvl_dialogue:
    xpos gui.nvl_text_xpos
    xanchor gui.nvl_text_xalign
    ypos gui.nvl_text_ypos
    xsize gui.nvl_text_width
    min_width gui.nvl_text_width
    textalign gui.nvl_text_xalign
    layout ("subtitle" if gui.nvl_text_xalign else "tex")

style nvl_thought:
    xpos gui.nvl_thought_xpos
    xanchor gui.nvl_thought_xalign
    ypos gui.nvl_thought_ypos
    xsize gui.nvl_thought_width
    min_width gui.nvl_thought_width
    textalign gui.nvl_thought_xalign
    layout ("subtitle" if gui.nvl_text_xalign else "tex")

style nvl_button:
    properties gui.button_properties("nvl_button")
    xpos gui.nvl_button_xpos
    xanchor gui.nvl_button_xalign

style nvl_button_text:
    properties gui.text_properties("nvl_button")



################################################################################
## Mobile Variants
################################################################################

style pref_vbox:
    variant "medium"
    xsize 450

## Since a mouse may not be present, we replace the quick menu with a version
## that uses fewer and bigger buttons that are easier to touch.
screen quick_menu():
    variant "touch"

    zorder 100

    hbox:
        style_prefix "quick"

        xalign 0.5
        yalign 1.0

        textbutton _("Назад") action Rollback()
        textbutton _("Пропуск") action Skip() alternate Skip(fast=True, confirm=True)
        textbutton _("Авто") action Preference("auto-forward", "toggle")
        textbutton _("Меню") action ShowMenu()


style window:
    variant "small"
    background "gui/phone/textbox.png"

style nvl_window:
    variant "small"
    background "gui/phone/nvl.png"

style main_menu_frame:
    variant "small"
    background "gui/phone/overlay/main_menu.png"

style game_menu_outer_frame:
    variant "small"
    background "gui/phone/overlay/game_menu.png"

style game_menu_navigation_frame:
    variant "small"
    xsize 340

style game_menu_content_frame:
    variant "small"
    top_margin 0

style pref_vbox:
    variant "small"
    xsize 400

style slider_pref_vbox:
    variant "small"
    xsize None

style slider_pref_slider:
    variant "small"
    xsize 600

# Shrink the title.
style main_menu_vbox:
    variant "small"
    xsize 900


screen creator():
    tag menu
    add "gui/game_menu.png"

    frame:
        style "vn_panel"

        vbox:
            spacing 10
            text "Создание новой игры" style "vn_panel_title"
            text "Сначала задаём мир. ИИ потом разворачивает его в игровые сцены." style "vn_hint"

            hbox:
                spacing 8
                textbutton "Краткое описание" style "vn_tab" action SetScreenVariable("creator_mode", "brief")
                textbutton "Импорт JSON" style "vn_tab" action SetScreenVariable("creator_mode", "import")
                textbutton "Полный рандом" style "vn_tab" action SetScreenVariable("creator_mode", "random")

            viewport:
                id "creator_scroll"
                scrollbars "vertical"
                mousewheel True
                ## Not draggable on purpose. A draggable viewport turns a click on a field into
                ## the start of a drag, so the click never reaches the input and the form cannot
                ## be filled in past the first field. The wheel and the scrollbar still scroll it.
                pagekeys True
                ysize vn_creator_scroll_h
                xfill True

                vbox:
                    spacing 10
                    ysize 1.0

                    if creator_mode == "brief":
                        frame:
                            background Solid("#e1efe5")
                            padding (14, 12)
                            vbox:
                                spacing 6
                                text "Название"
                                input value VariableInputValue("creator_title") length 80 style "vn_input"
                                text "Жанры"
                                input value VariableInputValue("creator_genre") length 120 style "vn_input"
                                text "Тон"
                                input value VariableInputValue("creator_tone") length 120 style "vn_input"
                                text "Краткое описание сюжета"
                                input value VariableInputValue("creator_description") length 600 style "vn_input_multiline"
                                text "Количество персонажей"
                                input value VariableInputValue("creator_character_count") length 3 style "vn_input"
                                text "Музыкальные папки (desktop, через ; )"
                                input value VariableInputValue("creator_music_paths") length 500 style "vn_input"

                    elif creator_mode == "import":
                        frame:
                            background Solid("#e1efe5")
                            padding (18, 14)
                            vbox:
                                spacing 10
                                text "Путь к story.json / world.json"
                                input value VariableInputValue("creator_json_path") length 500 style "vn_input"
                                textbutton "Вставить JSON из буфера обмена" action Function(load_story_from_clipboard)
                                text "Совет: файл должен описывать title, genre, characters, locations и lore." color "#4f725a"

                    else:
                        frame:
                            background Solid("#e1efe5")
                            padding (18, 14)
                            vbox:
                                spacing 10
                                text "Будут случайно выбраны тема, жанр, персонажи, локации и стартовая тайна."
                                text "Количество персонажей: [creator_character_count]"
                                text "После создания можно вручную поправить лор и настройки AI."

            hbox:
                spacing 10
                yalign 1.0
                textbutton "Создать и начать игру" style "vn_start_button" action Function(create_game_from_creator)
                textbutton "Назад" style "vn_tab" action Return()
                text "ИИ необязателен: без него игра пишет сцены сама." style "vn_hint" xalign 1.0 yalign 0.5

screen dynamic_choices(choices):
    modal True
    zorder 100

    vbox:
        xalign 0.5
        yalign 0.52
        xsize min(int(config.screen_width * 0.76), 920)
        spacing 14

        for choice in choices:
            textbutton choice.get("text", "..."):
                style "choice_button"
                xfill True
                action Return(choice.get("id", choice.get("text", "")))

        if persistent.vn_settings.get("free_input", True):
            textbutton "✎ Сказать самому...":
                style "choice_button"
                xfill True
                action Return("__FREE__")

## The settings panel.
##
## It used to be one column of everything: the connection check, the model, twenty
## sliders, the export path and the asset browser, all inside one scroll area. Nothing
## had a place, so nothing had a name, and the thing the player actually came for -- does
## the model answer at all -- sat between the api key and the temperature.
##
## The panel is now a contents list on the left and one section on the right. The list
## shows each section's real current state, the section shows what it is for, an "итог"
## strip of the values the engine will use, and then its rows. A row is one setting: its
## name, what it means, the control, and the value as it is stored. Labels, hints,
## slider bounds and units come from `vn_settings_schema`, so the screen holds no number
## of its own; `vn_settings_layout` decides which rows live in which section.
##
## Two things stay outside the scroll area on purpose: the proof strip with the verdict of
## the last real check, and the check button itself. A verdict the player has to scroll to
## find is not a verdict.

screen settings():
    tag menu

    add Solid("#e7f3eb")

    frame:
        style "vn_panel_settings"

        vbox:
            spacing 8

            hbox:
                spacing 12
                text "Настройки" style "vn_panel_title" size 28 xalign 0.0
                text "Провайдер, генерация, ассеты, звук, интерфейс и данные — по одному разделу" style "vn_hint" xalign 1.0 yalign 0.5

            ## Fixed heights, so the panel never grows out of its box: the strip holds the
            ## verdict, the mode and the reason, and the section area takes the rest.
            hbox:
                spacing 10
                ysize vn_status_h

                frame:
                    style "vn_status_frame"
                    vbox:
                        spacing 2
                        xfill True
                        for tone, line in settings_status.status_lines():
                            text line style ("vn_status_none" if tone == "none" else "vn_status_" + tone) xalign 0.0

                frame:
                    style "vn_check_frame"
                    vbox:
                        spacing 4
                        button:
                            style "vn_primary"
                            action Function(settings_status.test_now)
                            text settings_status.test_label()
                        text settings_status.test_when_text() style ("vn_status_none" if settings_status.test_tone() == "none" else "vn_status_" + settings_status.test_tone()) xalign 0.0

            hbox:
                spacing 10
                ysize vn_section_h

                frame:
                    style "vn_nav"
                    viewport:
                        mousewheel True
                        scrollbars "vertical"
                        yfill True
                        xfill True
                        vbox:
                            spacing 2
                            xfill True
                            for item in vn_settings_layout.sections():
                                button:
                                    style ("vn_nav_button_on" if item.id == vn_settings_layout.current().id else "vn_nav_button")
                                    action Function(vn_settings_layout.select, item.id)
                                    vbox:
                                        spacing 0
                                        xfill True
                                        text item.title style ("vn_nav_title_on" if item.id == vn_settings_layout.current().id else "vn_nav_title") xalign 0.0
                                        text item.status() style ("vn_nav_status_on" if item.id == vn_settings_layout.current().id else "vn_nav_status") xalign 0.0

                viewport:
                    id "settings_scroll"
                    mousewheel True
                    ## Not draggable: a drag here is started by the same click that should focus
                    ## a field, and the field never receives it. The wheel and the scrollbar
                    ## scroll the section.
                    pagekeys True
                    scrollbars "vertical"
                    ysize vn_section_h
                    xfill True
                    use vn_settings_section()

            hbox:
                spacing 10
                textbutton "Закрыть" style "vn_tab" action Return() yalign 0.5
                if persistent.vn_ai_profile:
                    text "профиль: [persistent.vn_ai_profile]" style "vn_hint" yalign 0.5
                text "Сохраняется сразу: [settings_status.save_dir_short()]" style "vn_hint" xalign 1.0 yalign 0.5


## The right-hand column: what the section is, what it currently does, and its rows.

screen vn_settings_section():
    vbox:
        spacing 8
        xfill True

        text vn_settings_layout.current().title style "vn_section"
        text vn_settings_layout.current().help style "vn_hint"

        frame:
            style "vn_summary"
            grid 2 2:
                ## Ren'Py's `spacing` takes one value, not a pair. A tuple here is only a
                ## render-time crash, so lint stays silent and the screen is simply empty.
                xspacing 24
                yspacing 4
                xfill True
                for label, value in vn_settings_layout.current().summary_pairs():
                    hbox:
                        spacing 10
                        text label style "vn_sum_label"
                        text value style "vn_sum_value" xfill True

        if vn_settings_layout.current().id == "ai":
            use vn_settings_ai()
        elif vn_settings_layout.current().id == "ui":
            use vn_settings_ui()
        elif vn_settings_layout.current().id == "assets":
            use vn_settings_assets()
        elif vn_settings_layout.current().id == "data":
            use vn_settings_data()
        elif vn_settings_layout.current().id == "cannibalism":
            use vn_settings_cannibalism()
        else:
            use vn_settings_fields()


## The generic section: every declared row, in the order the layout lists them.

screen vn_settings_fields():
    vbox:
        spacing 8
        xfill True
        for row in vn_settings_layout.current().fields:
            use vn_setting_row(row)


## One setting. The control is chosen by the declared kind, so a field can never end up
## with the wrong widget: text in, number on a bar with the schema's bounds, or a switch.

screen vn_setting_row(row):
    frame:
        style "vn_row"

        vbox:
            spacing 4
            xfill True

            hbox:
                spacing 12
                text row.label style "vn_field" xfill True
                text row.value_text() style "vn_value" yalign 0.5

            if row.hint:
                text row.hint style "vn_hint"

            if row.kind == "text":
                ## `vn_view` is the attribute view over the settings dict, not the dict:
                ## Ren'Py's `FieldInputValue` walks the name with `getattr` only.
                input value FieldInputValue(vn_view, row.key) style "vn_input" length row.length
            elif row.kind == "number":
                ## The bounds and the step are the declared ones, so the bar cannot
                ## produce a value the schema would refuse to store.
                bar value FieldValue(vn_view, row.key, min=row.low, max=row.high, step=row.step) style "vn_bar"
            elif row.kind == "flag":
                textbutton ("ВКЛ" if vn_settings_schema.flag(row.key) else "ВЫКЛ") style ("vn_toggle_on" if vn_settings_schema.flag(row.key) else "vn_toggle") action Function(toggle_setting, row.key)


## The provider section: the check, the address, the model, the saved profiles.

screen vn_settings_ai():
    vbox:
        spacing 8
        xfill True

        use vn_check_card()
        use vn_effective_card()

        for row in vn_settings_layout.current().fields:
            if row.key == "model":
                use vn_model_card()
            else:
                use vn_setting_row(row)

        use vn_profile_card()


## The connection check, with an outcome the player can act on: what came back, how long
## it took, when it was, and what to do when it failed. A timeout is named as a timeout
## rather than folded into "не работает", because it is the one failure that is usually
## not a wrong address.

screen vn_check_card():
    frame:
        style "vn_row"
        vbox:
            spacing 6
            hbox:
                spacing 12
                text "Проверка соединения" style "vn_field" xfill True
                text settings_status.test_result_text() style ("vn_status_" + settings_status.test_tone()) yalign 0.5
            text settings_status.test_detail_text() style "vn_hint"
            if settings_status.fix_hint():
                text "Что делать: [settings_status.fix_hint()]" style "vn_status_warn"
            hbox:
                spacing 10
                button:
                    style "vn_primary"
                    action Function(settings_status.test_now)
                    text settings_status.test_label()
                if settings_status.has_test():
                    textbutton "Проверить заново" style "vn_tab" action Function(settings_status.test_now)
            ## Its own line: beside the buttons this sentence is wider than the card, and an
            ## hbox does not wrap, so the card grew past the panel instead of the text wrapping.
            text "Проверка отправляет один короткий запрос текущей моделью и ждёт не дольше 30 секунд." style "vn_hint" xfill True


## What the game will use, with the models it resolved: an empty supervisor model shows
## as "та же", an empty absorber as "основная", so nothing here needs a second thought.

screen vn_effective_card():
    frame:
        style "vn_effective"
        vbox:
            spacing 2
            xfill True
            text "Эффективные значения — то, что игра использует сейчас" style "vn_field"
            for line in settings_status.effective_lines():
                text line style "vn_mono" xalign 0.0


## The model: the server's own list when it gives one, the typed name when it does not,
## and always a line saying which of the two the current name came from. A local server
## that serves no /v1/models is the normal case, not an error, so the manual field is a
## first-class way to choose and not a fallback hidden behind a button.

screen vn_model_card():
    frame:
        style "vn_row"
        vbox:
            spacing 6
            hbox:
                spacing 12
                text "Модель" style "vn_field" xfill True
                text vn_settings_schema.display("model") style "vn_value" yalign 0.5
            text "[settings_status.model_source_text()]" style "vn_hint"

            hbox:
                spacing 8
                textbutton "Загрузить модели с сервера" style "vn_tab" action Function(settings_status.refresh_models)
                text "[settings_status.models_note()]" style "vn_hint" yalign 0.5

            if provider_models:
                frame:
                    style "vn_box"
                    vbox:
                        spacing 6
                        text settings_status.models_source_title() style "vn_hint"
                        grid 3 4:
                            spacing 6
                            xfill True
                            for m in provider_models[:12]:
                                textbutton m style ("vn_chip_on" if m == vn_view.model else "vn_chip") action SetField(vn_view, "model", m)
                        if len(provider_models) > 12:
                            text "Показаны первые 12 из [len(provider_models)] — остальные впишите вручную." style "vn_hint"

            text "Или впишите имя модели вручную:" style "vn_field"
            input value FieldInputValue(vn_view, "model") style "vn_input" length 300


## Saved provider sets. Switching a profile rewrites the fields above, which is why the
## active one is highlighted rather than merely listed.

screen vn_profile_card():
    frame:
        style "vn_row"
        vbox:
            spacing 6
            text "Профили подключения" style "vn_field"
            text "Профиль — сохранённый набор адреса, моделей и параметров. Переключение профиля перезаписывает их в полях выше." style "vn_hint"
            hbox:
                spacing 8
                for name in sorted((persistent.vn_ai_profiles or {}).keys()):
                    textbutton name style ("vn_tab_on" if name == persistent.vn_ai_profile else "vn_tab") action Function(ai_provider.set_active_profile, name)
            hbox:
                spacing 8
                text "Имя нового профиля" style "vn_field"
                input value VariableInputValue("profile_new_name") style "vn_input" length 200
                textbutton "Сохранить текущие" style "vn_tab" action Function(ai_provider.store_profile, profile_new_name)
                textbutton "Удалить активный" style "vn_tab" action Function(ai_provider.delete_profile, persistent.vn_ai_profile)
            hbox:
                spacing 8
                textbutton "Вернуть встроенный профиль по умолчанию" style "vn_tab" action Function(settings_status.apply_builtin_profile)
                text "• [provider_test]" style "vn_hint" yalign 0.5


## The interface section: the three switches, then where the standard Ren'Py settings
## actually live. A "настройки" button that opens another settings screen is only useful
## if it says what is inside.

screen vn_settings_ui():
    vbox:
        spacing 8
        xfill True
        for row in vn_settings_layout.current().fields:
            use vn_setting_row(row)
        frame:
            style "vn_row"
            vbox:
                spacing 6
                text "Стандартные настройки Ren'Py" style "vn_field"
                text "Окно или полный экран, скорость текста, громкости каналов, пропуск уже показанных строк." style "vn_hint"
                hbox:
                    spacing 8
                    textbutton "Открыть настройки Ren'Py" style "vn_tab" action ShowMenu("preferences")
                    textbutton "История диалогов" style "vn_tab" action ShowMenu("history")
                    textbutton "Справка по клавишам" style "vn_tab" action ShowMenu("help")
                    textbutton "Лор и сюжет" style "vn_tab" action ShowMenu("codex")


## The assets section: what was found, the bind report, and the browser itself.

screen vn_settings_assets():
    vbox:
        spacing 8
        xfill True

        text "[asset_catalog_summary()]" style "vn_hint"

        hbox:
            spacing 8
            textbutton "Фоны" style ("vn_tab_on" if asset_browser_tab == "backgrounds" else "vn_tab") action SetScreenVariable("asset_browser_tab", "backgrounds")
            textbutton "Персонажи" style ("vn_tab_on" if asset_browser_tab == "characters" else "vn_tab") action SetScreenVariable("asset_browser_tab", "characters")
            textbutton "Пересканировать" style "vn_tab" action Function(settings_status.rescan_assets)
            textbutton "Открыть папку игры" style "vn_tab" action Function(vn_assetbrowser.shell_open_gamedir)

        if asset_preview_id:
            frame:
                style "vn_box"
                vbox:
                    spacing 4
                    hbox:
                        spacing 12
                        if vn_assetbrowser.asset_preview_path():
                            add Image(vn_assetbrowser.asset_preview_path()) xalign 0.0 yalign 0.5 ysize 170
                        vbox:
                            spacing 4
                            xalign 0.0
                            yalign 0.5
                            text "[asset_preview_id]" style "vn_field"
                            text "[vn_assetbrowser.asset_preview_kind()]" style "vn_hint"
                            text "Выбери карточку ниже, чтобы сменить превью." style "vn_hint"
                    textbutton "Скрыть превью" style "vn_tab" action SetScreenVariable("asset_preview_id", "")

        viewport:
            scrollbars "vertical"
            mousewheel True
            draggable True
            ysize 200
            yfill False
            xfill True

            if asset_browser_tab == "backgrounds":
                grid 3 3:
                    spacing 8
                    for item in vn_assetbrowser.asset_background_cards():
                        button:
                            action SetScreenVariable("asset_preview_id", item["id"])
                            xfill True
                            yfill True
                            add Solid("#e1f0e6")
                            add Image(item["preview"]) xalign 0.5 yalign 0.5 ysize 180
                            text item["id"] style "vn_hint" xalign 0.0 yalign 1.0
            else:
                vpgrid:
                    cols 4
                    rows 2
                    spacing 8
                    xfill True
                    for item in vn_assetbrowser.asset_character_cards():
                        button:
                            action SetScreenVariable("asset_preview_id", item["id"])
                            xfill True
                            add Solid("#e1f0e6")
                            add Image(item["preview"]) xalign 0.5 yalign 0.5 ysize 150
                            text item["id"] style "vn_hint" xalign 0.5

        frame:
            style "vn_box"
            vbox:
                spacing 2
                text "Привязка персонажей мира к ассетам" style "vn_field"
                for line in asset_bind_report():
                    text "[line]" style "vn_hint"

        for row in vn_settings_layout.current().fields:
            use vn_setting_row(row)

        textbutton "Применить папки и пересканировать" style "vn_tab" action [Function(clear_asset_cache_action), Function(asset_rescan)]


## The data section: what an export file contains and where it goes.

screen vn_settings_data():
    vbox:
        spacing 8
        xfill True

        for row in vn_settings_layout.current().fields:
            use vn_setting_row(row)

        frame:
            style "vn_row"
            vbox:
                spacing 6
                text "Экспорт мира" style "vn_field"
                text "Обычный JSON, которым можно поделиться с другим игроком. Ключ доступа в него попадает только если это разрешено выше." style "vn_hint"
                hbox:
                    spacing 8
                    text "Имя файла" style "vn_field"
                    input value VariableInputValue("export_name") style "vn_input" length 120
                    textbutton "Экспортировать мир" style "vn_tab" action Function(export_current_world)
                text "Папка экспорта: [get_export_folder()]" style "vn_hint"

        frame:
            style "vn_row"
            vbox:
                spacing 6
                text "Импорт мира" style "vn_field"
                text "Путь к файлу, из которого игра заберёт мир. Текущий мир будет заменён." style "vn_hint"
                hbox:
                    spacing 8
                    input value VariableInputValue("import_world_path") style "vn_input" length 420
                    textbutton "Импортировать" style "vn_tab" action Function(import_world_from_path)


## Absorption: unchanged in behaviour, given the same frame and the same summary strip as
## every other section so it no longer looks like a page pasted from another program.

screen vn_settings_cannibalism():
    vbox:
        spacing 8
        xfill True

        text "Сюжет исходной игры не импортируется. Поглотитель отдельно оценивает персонажей, изображения, музыку, голос и Live2D." style "vn_hint"
        text "Поддерживаются обычные доступные папки, обычные ZIP и штатные контейнеры Ren'Py .rpa (только чтение). Защищённые/DRM-архивы и исполняемый код не обходятся и не запускаются." style "vn_status_bad"

        text "Путь к папке или ZIP" style "vn_field"
        input value VariableInputValue("cannibalism_source_path") style "vn_input" length 500
        text "Название источника (необязательно)" style "vn_field"
        input value VariableInputValue("cannibalism_source_name") style "vn_input" length 220

        hbox:
            spacing 8
            textbutton "Сканировать" style "vn_tab" action Function(cannibalism_scan)
            textbutton "AI-поглотитель" style "vn_tab" action Function(cannibalism_assess)
            textbutton "Выбрать всё" style "vn_tab" action Function(cannibalism_select_all, True)
            textbutton "Снять всё" style "vn_tab" action Function(cannibalism_select_all, False)

        text "Добавлять найденных персонажей в текущий мир: " + ("ДА" if cannibalism_import_characters else "НЕТ") style "vn_field"
        text "Найдено: [len(cannibalism_scan_result.get('files', []))] • Выбрано: [len(cannibalism_assessment.get('selected_ids', []))]" style "vn_hint"
        if cannibalism_scan_result.get("archives"):
            text "Открыто .rpa-архивов: [len(cannibalism_scan_result.get('archives', []))]" style "vn_hint"
            for archive in cannibalism_scan_result.get("archives", [])[:6]:
                text "  [archive.get('path', '')] — [archive.get('entries', 0)] записей, [archive.get('bytes', 0) / 1048576.0:.1f] МБ" style "vn_hint"
        for warning in cannibalism_scan_result.get("warnings", [])[:4]:
            text "  ! [warning]" style "vn_status_bad"
        if cannibalism_assessment.get("summary"):
            text cannibalism_assessment.get("summary") style "vn_field"
        if cannibalism_assessment.get("error"):
            text "Ошибка: [cannibalism_assessment.get('error')]" style "vn_status_bad"

        viewport:
            scrollbars "vertical"
            mousewheel True
            draggable True
            ysize 200
            xfill True
            vbox:
                spacing 4
                for item in cannibalism_scan_result.get("files", [])[:250]:
                    hbox:
                        spacing 8
                        textbutton (("☑ " if item.get("selected") else "☐ ") + item.get("path", "")) action Function(cannibalism_toggle, item.get("id")) xsize 660
                        text item.get("kind", "other") style "vn_hint"
                        if item.get("archive"):
                            text "из " + item.get("archive", "") style "vn_hint"

        textbutton "ПОГЛОТИТЬ В ИГРУ" style "vn_primary" action Function(cannibalism_absorb)
        text "Поглощённые ресурсы хранятся в game/absorbed/ и помечаются как third-party/unverified. Они не входят в обычный переносимый экспорт мира." style "vn_hint"


screen codex():
    tag menu
    add Solid("#e4f1e8")
    frame:
        xalign 0.5
        yalign 0.5
        xsize 1180
        ysize 660
        background Solid("#dbede1")
        padding (28, 26)
        vbox:
            spacing 10
            text "World Codex / Лор" size 34
            text "Изменение лора здесь не меняет только текстовый журнал — изменения попадают в world state и доступны будущим сценам." color "#4f725a"
            viewport:
                scrollbars "vertical"
                mousewheel True
                ## Not draggable: the lore field inside would never get the click.
                pagekeys True
                ysize 360
                vbox:
                    spacing 8
                    for item in game_state.get("lore", []):
                        text "• [item]"
                    for name, loc in game_state.get("locations", {}).items():
                        text "[name]: [loc.get('description', '')]" color "#1f522f"
            text "Добавить факт"
            input value VariableInputValue("lore_edit_text") style "vn_input" length 500
            hbox:
                spacing 10
                textbutton "Добавить" action Function(add_lore_from_input)
                textbutton "Назад" action Return()


## The settings panel: a taller box and the styles the status proof strip needs.
##
## The panel had room for 470 pixels of content; the always-visible status strip, the
## check button beside it and the contents list take the rest, so the box is grown to 690
## (the screen is 720 tall) and the section area keeps 420. Nothing was removed to make
## room, and everything still scrolls.

style vn_panel_settings is vn_panel:
    ## The panel has to be narrower than the window, or the status row lays itself out at its
    ## natural width and the connection button ends up half outside the screen. The size comes
    ## from `vn_panel`, so it follows the window; only the padding is local.
    padding (26, 20)

## The proof strip: what the game is using, and what the last real request returned.

style vn_status_frame is frame:
    xfill True
    ## Room for the verdict, the mode and the reason, and no more: without a maximum the text
    ## asks for its full natural width and pushes the button out of the panel.
    xmaximum 740
    background Solid("#e2f0e6e6")
    padding (16, 10)

style vn_status_none is default:
    size 20
    color "#22773d"
    line_spacing 1
    xalign 0.0

style vn_status_good is vn_status_none:
    color "#248542"

style vn_status_bad is vn_status_none:
    color "#972111"

style vn_status_warn is vn_status_none:
    color "#976c11"

## The read-only "what the game uses" block, and the path line in the footer.

style vn_effective is frame:
    xfill True
    background Solid("#e2f0e6b8")
    padding (16, 10)

style vn_mono is default:
    size 20
    color "#22773d"
    xalign 0.0

## The connection check is the one button whose outcome the player came for.

style vn_primary is button:
    xsize None
    ysize None
    padding (24, 11)
    background Solid("#69d38a")
    hover_background Solid("#69d38a")

style vn_primary_text is button_text:
    size 24
    bold True
    color "#112c19"
    xalign 0.5
