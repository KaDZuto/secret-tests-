## Living VN -- the look on top of the standard Ren'Py GUI.
##
## `gui.rpy` and `screens.rpy` are the stock Ren'Py 8.3.7 project, which is what makes
## save/load, preferences, history and the dialogue windows behave predictably. This
## file only changes how they look: a wider, higher textbox with outlined text, a name
## plate, a blinking continuation marker, and quick-menu buttons on the textbox edge.

## Plain store variables rather than attributes on a custom object, so every style
## statement resolves them no matter in which order the init blocks run.
define vn_textbox_pad_x = 48
define vn_namebox_pad_x = 52
define vn_namebox_rise = 54
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

style vn_quick_button is button:
    xsize None
    ysize None
    padding (16, 8)
    background Solid("#0b111cbb")
    hover_background Solid("#28344ef2")

style vn_quick_text is button_text:
    size 20
    color "#b0bccf"
    hover_color "#ffffff"
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
    xalign 0.5
    yalign 0.5
    xsize 1180
    ysize 660
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

style vn_check is button:
    xsize None
    ysize None
    padding (16, 8)
    background Solid("#0b111cbb")
    hover_background Solid("#28344ef2")

style vn_check_text is vn_quick_text:
    size 22
    xalign 0.0


## Text inputs in the settings screen need an input style, not a text style.

style vn_input is input:
    size 24
    color "#eef2f9"
    xfill True
    background Solid("#080b12e6")
    padding (14, 9)


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
