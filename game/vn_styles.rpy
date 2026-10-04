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
define vn_cyan = "#8fb8ff"


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
    color "#f2f5fa"
    line_spacing 3
    outlines [ (2, "#05070cd8", 0, 0) ]

style say_thought is say_dialogue:
    italic True
    color "#d5deeb"

style say_label:
    size 30
    color "#8fb8ff"
    outlines [ (2, "#04060ad0", 0, 0) ]


## The name plate straddles the top edge of the textbox, like the reference VNs.

style namebox:
    xpos vn_namebox_pad_x
    xanchor 0.0
    ypos -52
    yanchor 1.0
    background Solid("#151d2ceb")
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
    color vn_cyan
    xalign 0.5
    outlines [ (2, "#05070cc0", 0, 0) ]


## Quick menu sitting on the textbox border. The stock quick_button style carries a 9-patch
## sized for a bottom bar, so it is restyled here for a horizontal row.

style quick_button:
    xsize None
    ysize None
    padding (14, 7)
    background Solid("#0b111cbb")
    hover_background Solid("#28344ef2")
    insensitive_background Solid("#0b111c88")

style quick_button_text:
    size 19
    color "#b0bccf"
    hover_color "#ffffff"
    insensitive_color "#6f7d92"
    xalign 0.5
    outlines [ (2, "#05070ca8", 0, 0) ]

## Choices.

style choice_button:
    background Solid("#0e1421e0")
    hover_background Solid("#2f3d5aee")

style choice_button_text:
    size 30
    xalign 0.5
    outlines [ (2, "#05070cbc", 0, 0) ]


## Panels used by the creator, settings and codex screens.

style vn_panel is frame:
    ## Shares of the window, not pixels: the same panel has to fit 720p, 1080p and 1440p.
    xalign 0.5
    yalign 0.5
    xsize vn_panel_w
    ysize vn_panel_h
    background Solid("#0e1220f2")
    padding (30, 26)

style vn_panel_title is default:
    size 36
    bold True
    color "#f4f7ff"

style vn_section is default:
    size 28
    bold True
    color gui.accent_color

style vn_hint is default:
    size 21
    color "#8b98ad"
    line_spacing 2

style vn_field is default:
    size 24
    color "#eef2f9"

style vn_tab is button:
    xsize None
    ysize None
    padding (18, 9)
    background Solid("#0e1420cc")
    hover_background Solid("#28344ef2")

style vn_tab_text is button_text:
    size 22
    color "#b3bed0"
    hover_color "#ffffff"
    xalign 0.5

style vn_tab_on is vn_tab:
    background Solid("#28344ef2")

style vn_tab_on_text is vn_tab_text:
    color "#ffffff"
    bold True

style vn_vscrollbar is gui_vscrollbar:
    unscrollable "hide"

## Text inputs in the settings screen need an input style, not a text style.

style vn_input is input:
    ## A field has to look like a field. The background used to be darker than the panel behind
    ## it, so every input read as a line of text and the only one that could be typed into was
    ## the one that happened to hold the cursor.
    size 24
    color "#eef2f9"
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
    background Solid("#0a0f1ae6")
    padding (10, 12)

## The check button beside the proof strip: the one control that must be reachable from
## every section, so it gets its own frame rather than sharing the status block.

style vn_check_frame is frame:
    xsize vn_check_w
    yfill True
    background Solid("#0a1120e6")
    padding (16, 8)

style vn_nav_button is button:
    xfill True
    ysize None
    padding (12, 1)
    background None
    hover_background Solid("#1d2a45f2")

style vn_nav_button_on is vn_nav_button:
    background Solid("#2f6bd8")
    hover_background Solid("#3f7ce8")

style vn_nav_title is default:
    size 19
    color "#cfd8e6"
    xalign 0.0

style vn_nav_title_on is vn_nav_title:
    color "#ffffff"
    bold True

style vn_nav_status is default:
    size 15
    color "#8b98ad"
    xalign 0.0

style vn_nav_status_on is vn_nav_status:
    color "#d7e4fa"


## One setting: name, what it means, the control, and the value the engine will get.

style vn_row is frame:
    xfill True
    background Solid("#0c111cd9")
    padding (16, 10)

style vn_value is default:
    size 22
    bold True
    color vn_cyan
    xalign 1.0

## The "итог" strip under the section title: what this section currently does.

style vn_summary is frame:
    xfill True
    background Solid("#0c1526e6")
    padding (16, 10)

style vn_sum_label is default:
    size 20
    color "#8b98ad"
    xsize 160
    xalign 0.0

style vn_sum_value is default:
    size 21
    color "#eaf0fb"
    xalign 0.0

## A nested box inside a row: the model list, the profile row.

style vn_box is frame:
    xfill True
    background Solid("#080c15e6")
    padding (12, 10)

## A model name from the server list. Clipped rather than stretched, so a long id in the
## grid does not push the neighbouring names out of the panel.

style vn_chip is button:
    xfill True
    yfill False
    padding (10, 6)
    background Solid("#0b111cbb")
    hover_background Solid("#28344ef2")

style vn_chip_text is button_text:
    size 19
    color "#b3bed0"
    hover_color "#ffffff"
    xalign 0.5

style vn_chip_on is vn_chip:
    background Solid("#2f6bd8")

style vn_chip_on_text is vn_chip_text:
    color "#ffffff"
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
    background Solid("#0b111cbb")
    hover_background Solid("#28344ef2")

style vn_toggle_text is button_text:
    size 21
    color "#8b98ad"
    xalign 0.5

style vn_toggle_on is vn_toggle:
    background Solid("#2f6bd8")

style vn_toggle_on_text is vn_toggle_text:
    color "#ffffff"
    bold True


## Main menu: the title block, its accent bar and the version footer.

style vn_title is default:
    size 58
    bold True
    color "#f4f7ff"
    outlines [ (3, "#04060ad8", 0, 0) ]
    xalign 0.0

style vn_subtitle is default:
    size 22
    color "#9fb0c9"
    outlines [ (2, "#04060ab0", 0, 0) ]
    xalign 0.0

style vn_menu_button is button:
    xsize 340
    xalign 0.0
    background Solid("#111826d9")
    hover_background Solid("#2b3a5aee")
    padding (26, 14)

style vn_menu_button_text is button_text:
    size 30
    xalign 0.0
    outlines [ (2, "#05070cb0", 0, 0) ]

style vn_footer is default:
    size 16
    color "#6f7d92"
    outlines [ (2, "#04060aa8", 0, 0) ]


## The primary action of a panel, so "start" is never the quietest button on screen.

style vn_start_button is button:
    xsize None
    ysize None
    padding (28, 14)
    background Solid("#2f6bd8")
    hover_background Solid("#4b8bf0")

style vn_start_button_text is button_text:
    size 28
    bold True
    xalign 0.5
    color "#ffffff"
    outlines [ (2, "#0a1428b0", 0, 0) ]

## Text inputs, so a form field reads as a field instead of bare text.

style input:
    size 24
    color "#eef2f9"
    xfill True
    background Solid("#080b12e6")
    padding (14, 9)

style input_prompt:
    size 24
    color "#8b98ad"


## A multiline text field: the description the creator writes is a paragraph, not a line.

style vn_input_multiline is vn_input:
    multiline True
    ysize 120
    padding (12, 9)
