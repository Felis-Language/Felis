# Scratch block mappings

from typing import Dict, List, Any, Optional
from dataclasses import dataclass


@dataclass
class BlockDefinition:
    opcode: str
    inputs: List[str] = None
    fields: List[str] = None
    is_reporter: bool = False
    is_boolean: bool = False
    is_hat: bool = False
    is_cap: bool = False
    
    def __post_init__(self):
        self.inputs = self.inputs or []
        self.fields = self.fields or []


# Motion
MOTION_BLOCKS = {
    'move': BlockDefinition('motion_movesteps', ['STEPS']),
    'turn_right': BlockDefinition('motion_turnright', ['DEGREES']),
    'turn_left': BlockDefinition('motion_turnleft', ['DEGREES']),
    'goto': BlockDefinition('motion_goto', inputs=['TO']),
    'goto_xy': BlockDefinition('motion_gotoxy', ['X', 'Y']),
    'glide_to': BlockDefinition('motion_glideto', ['SECS', 'TO']),  # TO needs menu shadow
    'glide_xy': BlockDefinition('motion_glidesecstoxy', ['SECS', 'X', 'Y']),
    'point_direction': BlockDefinition('motion_pointindirection', ['DIRECTION']),
    'point_in_direction': BlockDefinition('motion_pointindirection', ['DIRECTION']),
    'point_towards': BlockDefinition('motion_pointtowards', inputs=['TOWARDS']),
    'change_x': BlockDefinition('motion_changexby', ['DX']),
    'set_x': BlockDefinition('motion_setx', ['X']),
    'change_y': BlockDefinition('motion_changeyby', ['DY']),
    'set_y': BlockDefinition('motion_sety', ['Y']),
    'bounce_on_edge': BlockDefinition('motion_ifonedgebounce'),
    'set_rotation_style': BlockDefinition('motion_setrotationstyle', fields=['STYLE']),
    'x_position': BlockDefinition('motion_xposition', is_reporter=True),
    'y_position': BlockDefinition('motion_yposition', is_reporter=True),
    'direction': BlockDefinition('motion_direction', is_reporter=True),
}

# Looks
LOOKS_BLOCKS = {
    'say': BlockDefinition('looks_say', ['MESSAGE']),
    'say_for': BlockDefinition('looks_sayforsecs', ['MESSAGE', 'SECS']),
    'think': BlockDefinition('looks_think', ['MESSAGE']),
    'think_for': BlockDefinition('looks_thinkforsecs', ['MESSAGE', 'SECS']),
    'switch_costume': BlockDefinition('looks_switchcostumeto', ['COSTUME']),
    'next_costume': BlockDefinition('looks_nextcostume'),
    'switch_backdrop': BlockDefinition('looks_switchbackdropto', ['BACKDROP']),
    'switch_backdrop_and_wait': BlockDefinition('looks_switchbackdroptoandwait', ['BACKDROP']),
    'next_backdrop': BlockDefinition('looks_nextbackdrop'),
    'change_size': BlockDefinition('looks_changesizeby', ['CHANGE']),
    'set_size': BlockDefinition('looks_setsizeto', ['SIZE']),
    # Note: Args order is (effect, change) to match natural reading: "change GHOST effect by 10"
    # Compiler has special handling to put effect in EFFECT field and change in CHANGE input
    'change_effect': BlockDefinition('looks_changeeffectby', ['CHANGE'], ['EFFECT']),
    # Note: Args order is (effect, value) to match natural reading: "set GHOST effect to 100"  
    'set_effect': BlockDefinition('looks_seteffectto', ['VALUE'], ['EFFECT']),
    'clear_effects': BlockDefinition('looks_cleargraphiceffects'),
    'clear_graphic_effects': BlockDefinition('looks_cleargraphiceffects'),
    'show': BlockDefinition('looks_show'),
    'hide': BlockDefinition('looks_hide'),
    'go_to_front': BlockDefinition('looks_gotofrontback', fields=['FRONT_BACK']),
    'go_to_back': BlockDefinition('looks_gotofrontback', fields=['FRONT_BACK']),
    'go_forward_layers': BlockDefinition('looks_goforwardbackwardlayers', ['NUM'], ['FORWARD_BACKWARD']),
    'go_backward_layers': BlockDefinition('looks_goforwardbackwardlayers', ['NUM'], ['FORWARD_BACKWARD']),
    'costume_number': BlockDefinition('looks_costumenumbername', fields=['NUMBER_NAME'], is_reporter=True),
    'costume_name': BlockDefinition('looks_costumenumbername', fields=['NUMBER_NAME'], is_reporter=True),
    'backdrop_number': BlockDefinition('looks_backdropnumbername', fields=['NUMBER_NAME'], is_reporter=True),
    'backdrop_name': BlockDefinition('looks_backdropnumbername', fields=['NUMBER_NAME'], is_reporter=True),
    'size': BlockDefinition('looks_size', is_reporter=True),
}

# Sound
SOUND_BLOCKS = {
    'play_sound_until_done': BlockDefinition('sound_playuntildone', ['SOUND_MENU']),
    'start_sound': BlockDefinition('sound_play', ['SOUND_MENU']),
    'play_sound': BlockDefinition('sound_play', ['SOUND_MENU']),
    'stop_all_sounds': BlockDefinition('sound_stopallsounds'),
    'change_effect_sound': BlockDefinition('sound_changeeffectby', ['VALUE'], ['EFFECT']),
    'set_effect_sound': BlockDefinition('sound_seteffectto', ['VALUE'], ['EFFECT']),
    'clear_sound_effects': BlockDefinition('sound_cleareffects'),
    'change_volume': BlockDefinition('sound_changevolumeby', ['VOLUME']),
    'set_volume': BlockDefinition('sound_setvolumeto', ['VOLUME']),
    'volume': BlockDefinition('sound_volume', is_reporter=True),
}

# Events
EVENT_BLOCKS = {
    'flag_clicked': BlockDefinition('event_whenflagclicked', is_hat=True),
    'key_pressed': BlockDefinition('event_whenkeypressed', fields=['KEY_OPTION'], is_hat=True),
    'sprite_clicked': BlockDefinition('event_whenthisspriteclicked', is_hat=True),
    'stage_clicked': BlockDefinition('event_whenstageclicked', is_hat=True),
    'backdrop_switches': BlockDefinition('event_whenbackdropswitchesto', fields=['BACKDROP'], is_hat=True),
    'loudness_greater': BlockDefinition('event_whengreaterthan', ['VALUE'], ['WHENGREATERTHANMENU'], is_hat=True),
    'timer_greater': BlockDefinition('event_whengreaterthan', ['VALUE'], ['WHENGREATERTHANMENU'], is_hat=True),
    'message_received': BlockDefinition('event_whenbroadcastreceived', fields=['BROADCAST_OPTION'], is_hat=True),
    'broadcast': BlockDefinition('event_broadcast', ['BROADCAST_INPUT']),
    'broadcast_and_wait': BlockDefinition('event_broadcastandwait', ['BROADCAST_INPUT']),
}

# Control
CONTROL_BLOCKS = {
    'wait': BlockDefinition('control_wait', ['DURATION']),
    'repeat': BlockDefinition('control_repeat', ['TIMES']),
    'forever': BlockDefinition('control_forever'),
    'if': BlockDefinition('control_if', ['CONDITION']),
    'if_else': BlockDefinition('control_if_else', ['CONDITION']),
    'wait_until': BlockDefinition('control_wait_until', ['CONDITION']),
    'repeat_until': BlockDefinition('control_repeat_until', ['CONDITION']),
    'stop': BlockDefinition('control_stop', fields=['STOP_OPTION'], is_cap=True),
    'clone_start': BlockDefinition('control_start_as_clone', is_hat=True),
    'create_clone': BlockDefinition('control_create_clone_of', fields=['CLONE_OPTION']),
    'delete_clone': BlockDefinition('control_delete_this_clone', is_cap=True),
}

# Sensing
SENSING_BLOCKS = {
    'touching': BlockDefinition('sensing_touchingobject', inputs=['TOUCHINGOBJECTMENU'], is_boolean=True),
    'touching_color': BlockDefinition('sensing_touchingcolor', ['COLOR'], is_boolean=True),
    'color_touching': BlockDefinition('sensing_coloristouchingcolor', ['COLOR', 'COLOR2'], is_boolean=True),
    'distance_to': BlockDefinition('sensing_distanceto', fields=['DISTANCETOMENU'], is_reporter=True),
    'ask_and_wait': BlockDefinition('sensing_askandwait', ['QUESTION']),
    'answer': BlockDefinition('sensing_answer', is_reporter=True),
    'key_pressed_sensing': BlockDefinition('sensing_keypressed', fields=['KEY_OPTION'], is_boolean=True),
    'mouse_down': BlockDefinition('sensing_mousedown', is_boolean=True),
    'mouse_x': BlockDefinition('sensing_mousex', is_reporter=True),
    'mouse_y': BlockDefinition('sensing_mousey', is_reporter=True),
    'set_drag_mode': BlockDefinition('sensing_setdragmode', fields=['DRAG_MODE']),
    'loudness': BlockDefinition('sensing_loudness', is_reporter=True),
    'timer': BlockDefinition('sensing_timer', is_reporter=True),
    'reset_timer': BlockDefinition('sensing_resettimer'),
    'attribute_of': BlockDefinition('sensing_of', inputs=['OBJECT'], fields=['PROPERTY'], is_reporter=True),
    'current': BlockDefinition('sensing_current', fields=['CURRENTMENU'], is_reporter=True),
    'days_since_2000': BlockDefinition('sensing_dayssince2000', is_reporter=True),
    'username': BlockDefinition('sensing_username', is_reporter=True),
    # turbowarp
    'is_turbowarp': BlockDefinition('tw_isturbowarp', is_boolean=True),
    'is_compiled': BlockDefinition('tw_iscompiled', is_boolean=True),
    'is_fenced': BlockDefinition('tw_isfenced', is_boolean=True),
}

# Operators
OPERATOR_BLOCKS = {
    'add': BlockDefinition('operator_add', ['NUM1', 'NUM2'], is_reporter=True),
    'subtract': BlockDefinition('operator_subtract', ['NUM1', 'NUM2'], is_reporter=True),
    'multiply': BlockDefinition('operator_multiply', ['NUM1', 'NUM2'], is_reporter=True),
    'divide': BlockDefinition('operator_divide', ['NUM1', 'NUM2'], is_reporter=True),
    'random': BlockDefinition('operator_random', ['FROM', 'TO'], is_reporter=True),
    'greater_than': BlockDefinition('operator_gt', ['OPERAND1', 'OPERAND2'], is_boolean=True),
    'less_than': BlockDefinition('operator_lt', ['OPERAND1', 'OPERAND2'], is_boolean=True),
    'equals': BlockDefinition('operator_equals', ['OPERAND1', 'OPERAND2'], is_boolean=True),
    'and': BlockDefinition('operator_and', ['OPERAND1', 'OPERAND2'], is_boolean=True),
    'or': BlockDefinition('operator_or', ['OPERAND1', 'OPERAND2'], is_boolean=True),
    'not': BlockDefinition('operator_not', ['OPERAND'], is_boolean=True),
    'join': BlockDefinition('operator_join', ['STRING1', 'STRING2'], is_reporter=True),
    'letter': BlockDefinition('operator_letter_of', ['LETTER', 'STRING'], is_reporter=True),
    'length': BlockDefinition('operator_length', ['STRING'], is_reporter=True),
    'contains': BlockDefinition('operator_contains', ['STRING1', 'STRING2'], is_boolean=True),
    'mod': BlockDefinition('operator_mod', ['NUM1', 'NUM2'], is_reporter=True),
    'round': BlockDefinition('operator_round', ['NUM'], is_reporter=True),
    'mathop': BlockDefinition('operator_mathop', ['NUM'], ['OPERATOR'], is_reporter=True),
}

# Variables
VARIABLE_BLOCKS = {
    'set_variable': BlockDefinition('data_setvariableto', ['VALUE']),
    'change_variable': BlockDefinition('data_changevariableby', ['VALUE']),
    'show_variable': BlockDefinition('data_showvariable'),
    'hide_variable': BlockDefinition('data_hidevariable'),
    'variable': BlockDefinition('data_variable', is_reporter=True),
}

# Lists
LIST_BLOCKS = {
    'add_to_list': BlockDefinition('data_addtolist', ['ITEM']),
    'delete_from_list': BlockDefinition('data_deleteoflist', ['INDEX']),
    'delete_all_list': BlockDefinition('data_deletealloflist'),
    'insert_in_list': BlockDefinition('data_insertatlist', ['ITEM', 'INDEX']),
    'replace_in_list': BlockDefinition('data_replaceitemoflist', ['INDEX', 'ITEM']),
    'item_of_list': BlockDefinition('data_itemoflist', ['INDEX'], is_reporter=True),
    'index_in_list': BlockDefinition('data_itemnumoflist', ['ITEM'], is_reporter=True),
    'length_of_list': BlockDefinition('data_lengthoflist', is_reporter=True),
    'list_contains': BlockDefinition('data_listcontainsitem', ['ITEM'], is_boolean=True),
    'show_list': BlockDefinition('data_showlist'),
    'hide_list': BlockDefinition('data_hidelist'),
    'list': BlockDefinition('data_listcontents', is_reporter=True),
}

# Pen
PEN_BLOCKS = {
    'erase_all': BlockDefinition('pen_clear'),
    'stamp': BlockDefinition('pen_stamp'),
    'pen_down': BlockDefinition('pen_penDown'),
    'pen_up': BlockDefinition('pen_penUp'),
    'set_pen_color': BlockDefinition('pen_setPenColorToColor', ['COLOR']),
    'change_pen_param': BlockDefinition('pen_changePenColorParamBy', ['VALUE'], ['colorParam']),
    'set_pen_param': BlockDefinition('pen_setPenColorParamTo', ['VALUE'], ['colorParam']),
    'change_pen_size': BlockDefinition('pen_changePenSizeBy', ['SIZE']),
    'set_pen_size': BlockDefinition('pen_setPenSizeTo', ['SIZE']),
}

# Music
MUSIC_BLOCKS = {
    'play_drum': BlockDefinition('music_playDrumForBeats', ['DRUM', 'BEATS']),
    'rest_for_beats': BlockDefinition('music_restForBeats', ['BEATS']),
    'play_note': BlockDefinition('music_playNoteForBeats', ['NOTE', 'BEATS']),
    'set_instrument': BlockDefinition('music_setInstrument', ['INSTRUMENT']),
    'set_tempo': BlockDefinition('music_setTempo', ['TEMPO']),
    'change_tempo': BlockDefinition('music_changeTempo', ['TEMPO']),
    'get_tempo': BlockDefinition('music_getTempo', is_reporter=True),
}

# Procedures
PROCEDURE_BLOCKS = {
    'definition': BlockDefinition('procedures_definition', is_hat=True),
    'prototype': BlockDefinition('procedures_prototype'),
    'call': BlockDefinition('procedures_call'),
    'argument_reporter_string': BlockDefinition('argument_reporter_string_number', is_reporter=True),
    'argument_reporter_boolean': BlockDefinition('argument_reporter_boolean', is_boolean=True),
}

ALL_BLOCKS: Dict[str, BlockDefinition] = {
    **MOTION_BLOCKS,
    **LOOKS_BLOCKS,
    **SOUND_BLOCKS,
    **EVENT_BLOCKS,
    **CONTROL_BLOCKS,
    **SENSING_BLOCKS,
    **OPERATOR_BLOCKS,
    **VARIABLE_BLOCKS,
    **LIST_BLOCKS,
    **PEN_BLOCKS,
    **MUSIC_BLOCKS,
    **PROCEDURE_BLOCKS,
}


def get_block_definition(name: str) -> Optional[BlockDefinition]:
    return ALL_BLOCKS.get(name)


# mathop field values
MATH_OPERATIONS = {
    'abs': 'abs',
    'floor': 'floor',
    'ceil': 'ceiling',
    'sqrt': 'sqrt',
    'sin': 'sin',
    'cos': 'cos',
    'tan': 'tan',
    'asin': 'asin',
    'acos': 'acos',
    'atan': 'atan',
    'ln': 'ln',
    'log': 'log',
    'antiln': 'e ^',
    'antilog': '10 ^',
}


# key field values
KEY_MAPPINGS = {
    'space': 'space',
    'up': 'up arrow',
    'down': 'down arrow',
    'left': 'left arrow',
    'right': 'right arrow',
    'enter': 'enter',
    'any': 'any',
}

# effect field values
EFFECT_MAPPINGS = {
    'color': 'COLOR',
    'fisheye': 'FISHEYE',
    'whirl': 'WHIRL',
    'pixelate': 'PIXELATE',
    'mosaic': 'MOSAIC',
    'brightness': 'BRIGHTNESS',
    'ghost': 'GHOST',
}
