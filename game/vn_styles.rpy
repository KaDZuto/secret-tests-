## Living VN -- the look on top of the standard Ren'Py GUI.
##
## `gui.rpy` and `screens.rpy` are the stock Ren'Py 8.3.7 project, which is what makes
## save/load, preferences, history and the dialogue windows behave predictably. This
## file only changes how they look: a wider, higher textbox with outlined text, a name
## plate, a blinking continuation marker, and quick-menu buttons on the textbox edge.

## Plain store variables rather than attributes on a custom object, so every style
## statement resolves them no matter in which order the init blocks run.
define vn_panel_w = 1180
define vn_panel_h = 648
define vn_nav_w = 294
define vn_check_w = 384
define vn_box_w = 941
define vn_status_h = 112
define vn_section_h = 396
define vn_creator_scroll_h = 461

## The same numbers, taken from the window the game actually opened in. Priority 10 puts this
## after `gui.init`, which is what sets `config.screen_width`; the `define` block above gives
## every style something to resolve even if this never runs, which is the rule the rest of this
## file already follows for the same reason.
init 10 python:
    import store

    import vn_layout

    store.vn_panel_w = vn_layout.panel_width()
    store.vn_panel_h = vn_layout.panel_height()
    store.vn_nav_w = int(round(vn_layout.screen_width() * 0.23))
    store.vn_check_w = int(round(vn_layout.screen_width() * 0.30))
    store.vn_box_w = int(round(vn_layout.screen_width() * 0.735))
    store.vn_status_h = vn_layout.status_h()
    store.vn_section_h = vn_layout.section_h()
    store.vn_creator_scroll_h = vn_layout.creator_scroll_h()
define vn_namebox_pad_x = 52
define vn_accent = "#22773d"


## Dialogue window: a hairline on top, light text with a dark outline so it stays
## readable over a bright background.
##
## The geometry is written out literally rather than through `gui.*`. The stock styles
## put the box at `ysize 0` and let the text flow out of the window, which left the text
## on the bottom edge of the screen with no box behind it; explicit sizes make the box,
## the plate and the text agree with each other.

style window:
    xalign 0.5
    xfill True
    yalign 1.0
    ysize 236
    background Image("gui/textbox.png", xalign=0.5, yalign=1.0)

style say_dialogue:
    xpos 60
    ## Below the quick menu, which sits on the top edge of the same box.
    ypos 58
    xsize 1160
    size 30
    color "#14341f"
    line_spacing 3
    outlines [ (2, "#e9f4ecd8", 0, 0) ]

style say_thought is say_dialogue:
    italic True
    color "#2c5a3a"

style say_label:
    size 30
    color "#22773d"
    outlines [ (2, "#eaf4edd0", 0, 0) ]


## The name plate straddles the top edge of the textbox, like the reference VNs.

style namebox:
    xpos vn_namebox_pad_x
    xanchor 0.0
    ypos -52
    yanchor 1.0
    background Solid("#dbece0eb")
    padding (24, 7, 28, 9)

style namebox_label is say_label


## Continuation marker in the lower right corner of the textbox.

transform vn_ctc_blink:
    alpha 1.0
    linear 0.5 alpha 0.15
    linear 0.5 alpha 1.0
    repeat

screen ctc():
    pass

style vn_ctc is button:
    xalign 0.982
    yalign 0.86
    xsize 0
    ysize 0
    padding (0, 0)
    background None
    hover_background None
    hover_color gui.hover_color
    insensitive_background None

style vn_ctc_text is button_text:
    size 22
    color vn_accent
    xalign 0.5
    outlines [ (2, "#e9f4ecc0", 0, 0) ]


## Quick menu sitting on the textbox border. The stock quick_button style carries a 9-patch
## sized for a bottom bar, so it is restyled here for a horizontal row.

style quick_button:
    xsize None
    ysize None
    padding (14, 7)
    background Solid("#e3f0e7bb")
    hover_background Solid("#cbe4d3f2")
    insensitive_background Solid("#e3f0e788")

style quick_button_text:
    size 19
    color "#225a34"
    hover_color "#112c19"
    insensitive_color "#4f725a"
    xalign 0.5
    outlines [ (2, "#e9f4eca8", 0, 0) ]

## Choices.

style choice_button:
    xfill True
    padding (26, 14)
    background Solid("#f3fbf5f2")
    hover_background Solid("#69d38af0")

style choice_button_text:
    size 26
    color "#14341f"
    hover_color "#05180b"
    xalign 0.5
    bold True
    outlines [ (1, "#ffffffcc", 0, 0) ]


## Panels used by the creator, settings and codex screens.

style vn_panel is frame:
    ## Shares of the window, not pixels: the same panel has to fit 720p, 1080p and 1440p.
    xalign 0.5
    yalign 0.5
    xsize vn_panel_w
    ysize vn_panel_h
    background Solid("#e1efe5f2")
    padding (30, 26)

style vn_panel_title is default:
    size 36
    bold True
    color "#22773d"

style vn_section is default:
    size 28
    bold True
    color gui.accent_color

style vn_hint is default:
    size 21
    color "#4f725a"
    line_spacing 2

style vn_field is default:
    size 24
    color "#22773d"

style vn_tab is button:
    xsize None
    ysize None
    padding (18, 9)
    background Solid("#e1efe5cc")
    hover_background Solid("#cbe4d3f2")

style vn_tab_text is button_text:
    size 22
    color "#225933"
    hover_color "#112c19"
    xalign 0.5

style vn_tab_on is vn_tab:
    background Solid("#cbe4d3f2")

style vn_tab_on_text is vn_tab_text:
    color "#112c19"
    bold True

style vn_vscrollbar is gui_vscrollbar:
    unscrollable "hide"

## Text inputs in the settings screen need an input style, not a text style.

style vn_input is input:
    ## A field has to look like a field. The background used to be darker than the panel behind
    ## it, so every input read as a line of text and the only one that could be typed into was
    ## the one that happened to hold the cursor.
    size 24
    color "#22773d"
    xfill True
    background Frame("images/ui/input_field.png", 1, 1, 1, 1)
    hover_background Frame("images/ui/input_field_hover.png", 1, 1, 1, 1)
    padding (14, 9)


## The settings panel: a contents list on the left, one section on the right.
##
## The old panel was one column of everything, so the connection check shared a scroll
## area with the export path. A section is now reached in one click from a list that
## also says what that section currently does, so the player can see which part needs
## attention without opening it.

style vn_nav is frame:
    xsize vn_nav_w
    yfill True
    background Solid("#e3f1e8e6")
    padding (10, 12)

## The check button beside the proof strip: the one control that must be reachable from
## every section, so it gets its own frame rather than sharing the status block.

style vn_check_frame is frame:
    xsize vn_check_w
    yfill True
    background Solid("#e2f0e6e6")
    padding (16, 8)

style vn_nav_button is button:
    xfill True
    ysize None
    padding (12, 1)
    background None
    hover_background Solid("#d1e7d8f2")

style vn_nav_button_on is vn_nav_button:
    background Solid("#69d38a")
    hover_background Solid("#69d38a")

style vn_nav_title is default:
    size 19
    color "#22773d"
    xalign 0.0

style vn_nav_title_on is vn_nav_title:
    color "#112c19"
    bold True

style vn_nav_status is default:
    size 15
    color "#4f725a"
    xalign 0.0

style vn_nav_status_on is vn_nav_status:
    color "#22773d"


## One setting: name, what it means, the control, and the value the engine will get.

style vn_row is frame:
    xfill True
    background Solid("#e2f0e7d9")
    padding (16, 10)

style vn_value is default:
    size 22
    bold True
    color vn_accent
    xalign 1.0

## The "итог" strip under the section title: what this section currently does.

style vn_summary is frame:
    xfill True
    background Solid("#dfefe4e6")
    padding (16, 10)

style vn_sum_label is default:
    size 20
    color "#4f725a"
    xsize 160
    xalign 0.0

style vn_sum_value is default:
    size 21
    color "#22773d"
    xalign 0.0

## A nested box inside a row: the model list, the profile row.

style vn_box is frame:
    xfill True
    background Solid("#e6f2e9e6")
    padding (12, 10)

## A model name from the server list. Clipped rather than stretched, so a long id in the
## grid does not push the neighbouring names out of the panel.

style vn_chip is button:
    xfill True
    yfill False
    padding (10, 6)
    background Solid("#e3f0e7bb")
    hover_background Solid("#cbe4d3f2")

style vn_chip_text is button_text:
    size 19
    color "#225933"
    hover_color "#112c19"
    xalign 0.5

style vn_chip_on is vn_chip:
    background Solid("#69d38a")

style vn_chip_on_text is vn_chip_text:
    color "#112c19"
    bold True

## A slider in this panel: the stock bar with a thumb, so the value is visible while it
## is being dragged instead of only afterwards in the label above.

style vn_bar is bar:
    xfill True
    thumb "gui/slider/horizontal_[prefix_]thumb.png"

## A switch that reads as a switch: ВКЛ and ВЫКЛ are not two buttons but two states.

style vn_toggle is button:
    xsize None
    ysize None
    padding (18, 7)
    background Solid("#e3f0e7bb")
    hover_background Solid("#cbe4d3f2")

style vn_toggle_text is button_text:
    size 21
    color "#4f725a"
    xalign 0.5

style vn_toggle_on is vn_toggle:
    background Solid("#69d38a")

style vn_toggle_on_text is vn_toggle_text:
    color "#112c19"
    bold True


## Main menu: the title block, its accent bar and the version footer.

style vn_title is default:
    size 50
    bold True
    color "#22773d"
    outlines [ (3, "#eaf4edd8", 0, 0) ]
    xalign 0.0

style vn_subtitle is default:
    size 22
    color "#22773d"
    outlines [ (2, "#eaf4edb0", 0, 0) ]
    xalign 0.0

style vn_menu_panel is empty:
    background Solid("#f1faf3e6")
    padding (38, 24, 30, 24)

style vn_menu_button is button:
    xfill True
    background None
    hover_background Solid("#c7e2cfee")
    padding (18, 8)

style vn_menu_button_text is button_text:
    size 28
    xalign 0.0
    color "#14341f"
    hover_color "#1a8f48"
    outlines []

style vn_menu_button_small is vn_menu_button:
    padding (18, 4)

style vn_menu_button_small_text is vn_menu_button_text:
    size 20
    color "#4f725a"

style vn_footer is default:
    size 16
    color "#4f725a"
    outlines [ (2, "#eaf4eda8", 0, 0) ]


## The primary action of a panel, so "start" is never the quietest button on screen.

style vn_start_button is button:
    xsize None
    ysize None
    padding (28, 14)
    background Solid("#69d38a")
    hover_background Solid("#69d38a")

style vn_start_button_text is button_text:
    size 28
    bold True
    xalign 0.5
    color "#112c19"
    outlines [ (2, "#dfefe4b0", 0, 0) ]

## Text inputs, so a form field reads as a field instead of bare text.

style input:
    size 24
    color "#22773d"
    xfill True
    background Solid("#e6f2eae6")
    padding (14, 9)

style input_prompt:
    size 24
    color "#4f725a"


## A multiline text field: the description the creator writes is a paragraph, not a line.

style vn_input_multiline is vn_input:
    ysize 120
    padding (12, 9)

style vn_step_button is button:
    xsize 36
    ysize 36
    padding (0, 0)
    background Solid("#e3f0e7d0")
    hover_background Solid("#69d38ae0")

style vn_step_button_text is button_text:
    size 22
    bold True
    color "#112c19"
    xalign 0.5
    yalign 0.5

style vn_chip_small is button:
    padding (12, 5)
    background Solid("#e3f0e7bb")
    hover_background Solid("#69d38ae0")

style vn_chip_small_text is button_text:
    size 17
    color "#112c19"
    xalign 0.5

style vn_chip_small_on is vn_chip_small:
    background Solid("#69d38a")

style vn_chip_small_on_text is vn_chip_small_text:
    bold True
