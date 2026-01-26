import json
import zipfile
import os
import hashlib
import shutil
import re
from typing import Dict, List, Any, Optional, Set, Tuple
from dataclasses import dataclass, field

from .lexer import Lexer
from .extensions import ExtensionLoader

# Get reserved keywords from lexer
RESERVED_WORDS = set(Lexer.KEYWORDS.keys())


@dataclass
class DecompilerContext:
    indent: int = 0
    variables: Dict[str, str] = field(default_factory=dict)  # id -> name
    lists: Dict[str, str] = field(default_factory=dict)  # id -> name
    broadcasts: Dict[str, str] = field(default_factory=dict)  # id -> name
    custom_blocks: Dict[str, dict] = field(default_factory=dict)  # id -> info (prototype_id -> info)
    called_proccodes: Set[str] = field(default_factory=set)  # proccodes called in current sprite
    defined_proccodes: Set[str] = field(default_factory=set)  # proccodes defined in current sprite
    current_sprite: str = ""
    unknown_blocks: Set[str] = field(default_factory=set)  # Set of unknown opcode names
    unknown_reporters: Set[str] = field(default_factory=set)  # Set of unknown reporter opcodes
    used_variables: Set[str] = field(default_factory=set)  # Variables referenced in current sprite
    declared_variables: Set[str] = field(default_factory=set)  # Variables declared in current sprite
    stage_variables: Set[str] = field(default_factory=set)  # Variables declared on stage (global)
    stage_lists: Set[str] = field(default_factory=set)  # Lists declared on stage (global)
    comments: Dict[str, dict] = field(default_factory=dict)  # comment_id -> comment data
    block_comments: Dict[str, str] = field(default_factory=dict)  # block_id -> comment_id
    extensions_used: Set[str] = field(default_factory=set)  # Track which extensions are used
    

class SB3Decompiler:
    MAX_INLINE_LIST_ITEMS = 20
    
    # TurboWarp/PenguinMod extension mappings (fallback for extensions without .felisx files)
    # Maps opcode to (felis_name, [input_names], [field_names], is_reporter)
    EXTENSION_BLOCKS = {
        # TurboWarp core
        'tw_isturbowarp': ('is_turbowarp', [], [], True),
        'tw_iscompiled': ('is_compiled', [], [], True),
        'tw_isfenced': ('is_fenced', [], [], True),
        'tw_getLastKeyPressed': ('last_key_pressed', [], [], True),
        'tw_getButtonIsDown': ('mouse_button_down', ['MOUSE_BUTTON'], [], True),
        
        # Runtime options
        'runtime_turboMode': ('turbo_mode', [], [], True),
        'runtime_setTurboMode': ('set_turbo_mode', ['ENABLED'], [], False),
        'runtime_framerate': ('framerate', [], [], True),
        'runtime_setFramerate': ('set_framerate', ['FPS'], [], False),
        'runtime_interpolation': ('interpolation', [], [], True),
        'runtime_setInterpolation': ('set_interpolation', ['ENABLED'], [], False),
        'runtime_cloneLimit': ('clone_limit', [], [], True),
        'runtime_setCloneLimit': ('set_clone_limit', ['LIMIT'], [], False),
        'runtime_stageWidth': ('stage_width', [], [], True),
        'runtime_stageHeight': ('stage_height', [], [], True),
        'runtime_setStageSize': ('set_stage_size', ['WIDTH', 'HEIGHT'], [], False),
        'runtime_greenFlag': ('runtime_green_flag', [], [], False),
        'runtime_stopAll': ('runtime_stop_all', [], [], False),
        
        # Files
        'files_open': ('open_file', [], [], True),
        'files_save': ('save_file', ['CONTENT', 'FILENAME'], [], False),
        'files_saveAs': ('save_file_as', ['CONTENT'], [], False),
        
        # Fetch
        'fetch_get': ('fetch_get', ['URL'], [], True),
        'fetch_post': ('fetch_post', ['URL', 'DATA'], [], True),
        
        # Clipboard
        'clipboard_getClipboard': ('get_clipboard', [], [], True),
        'clipboard_setClipboard': ('set_clipboard', ['TEXT'], [], False),
        
        # Local Storage
        'localStorage_get': ('local_storage_get', ['KEY'], [], True),
        'localStorage_set': ('local_storage_set', ['KEY', 'VALUE'], [], False),
        'localStorage_delete': ('local_storage_delete', ['KEY'], [], False),
        'localStorage_getAll': ('local_storage_all', [], [], True),
        
        # JSON
        'json_parse': ('json_parse', ['JSON'], [], True),
        'json_stringify': ('json_stringify', ['OBJECT'], [], True),
        'json_get': ('json_get', ['OBJECT', 'KEY'], [], True),
        'json_set': ('json_set', ['OBJECT', 'KEY', 'VALUE'], [], True),
        'json_delete': ('json_delete', ['OBJECT', 'KEY'], [], True),
        'json_isValid': ('json_is_valid', ['JSON'], [], True),
        'json_type': ('json_type', ['VALUE'], [], True),
        'json_length': ('json_length', ['OBJECT'], [], True),
        
        # Text manipulation
        'text_split': ('text_split', ['STRING', 'DELIMITER'], [], True),
        'text_join': ('text_join', ['ARRAY', 'DELIMITER'], [], True),
        'text_indexOf': ('text_index_of', ['STRING', 'SUBSTRING'], [], True),
        'text_replace': ('text_replace', ['STRING', 'OLD', 'NEW'], [], True),
        'text_replaceAll': ('text_replace_all', ['STRING', 'OLD', 'NEW'], [], True),
        'text_reverse': ('text_reverse', ['STRING'], [], True),
        'text_repeat': ('text_repeat', ['STRING', 'COUNT'], [], True),
        'text_trim': ('text_trim', ['STRING'], [], True),
        'text_lowercase': ('text_lowercase', ['STRING'], [], True),
        'text_uppercase': ('text_uppercase', ['STRING'], [], True),
        
        # Bitwise
        'bitwise_and': ('bitwise_and', ['A', 'B'], [], True),
        'bitwise_or': ('bitwise_or', ['A', 'B'], [], True),
        'bitwise_xor': ('bitwise_xor', ['A', 'B'], [], True),
        'bitwise_not': ('bitwise_not', ['A'], [], True),
        'bitwise_leftShift': ('bitwise_lshift', ['A', 'B'], [], True),
        'bitwise_rightShift': ('bitwise_rshift', ['A', 'B'], [], True),
        'bitwise_unsignedRightShift': ('bitwise_urshift', ['A', 'B'], [], True),
        
        # Clones Plus
        'clonesplus_getCloneCount': ('clone_count', [], [], True),
        'clonesplus_isClone': ('is_clone', [], [], True),
        'clonesplus_cloneIndex': ('clone_index', [], [], True),
        'clonesplus_setCloneIndex': ('set_clone_index', ['INDEX'], [], False),
        'clonesplus_deleteClones': ('delete_all_clones', [], [], False),
        'clonesplus_touchingClones': ('touching_clones', [], [], True),
        
        # Looks Plus  
        'looksplus_getEffectValue': ('get_effect', ['EFFECT'], [], True),
        'looksplus_setVisibility': ('set_visibility', ['VISIBLE'], [], False),
        'looksplus_getVisibility': ('get_visibility', [], [], True),
        'looksplus_hideSprite': ('hide_sprite', ['SPRITE'], [], False),
        'looksplus_showSprite': ('show_sprite', ['SPRITE'], [], False),
        
        # Sound expanded
        'soundexpanded_getVolume': ('get_sound_volume', ['SOUND'], [], True),
        'soundexpanded_setVolume': ('set_sound_volume', ['SOUND', 'VOLUME'], [], False),
        'soundexpanded_getSoundDuration': ('get_sound_duration', ['SOUND'], [], True),
        'soundexpanded_isSoundPlaying': ('is_sound_playing', ['SOUND'], [], True),
        'soundexpanded_stopSound': ('stop_sound', ['SOUND'], [], False),
        
        # More events hat blocks
        'moreevents_broadcast': ('broadcast', ['BROADCAST'], [], False),
        'moreevents_broadcastData': ('broadcast_with_data', ['BROADCAST', 'DATA'], [], False),
        'moreevents_broadcastDataWait': ('broadcast_with_data_and_wait', ['BROADCAST', 'DATA'], [], False),
        'moreevents_receivedData': ('received_data', [], [], True),
        
        # More motion
        'moremotion_changeDirection': ('change_direction', ['DIRECTION'], [], False),
        'moremotion_getXY': ('get_xy', [], [], True),
        'moremotion_stepTowards': ('step_towards', ['X', 'Y', 'STEP'], [], False),
        
        # Gamepad
        'gamepad_buttonDown': ('gamepad_button_down', ['BUTTON', 'PAD'], [], True),
        'gamepad_buttonAxis': ('gamepad_axis', ['AXIS', 'PAD'], [], True),
        'gamepad_connected': ('gamepad_connected', ['PAD'], [], True),
        
        # Pointer lock
        'pointerlock_lock': ('lock_pointer', [], [], False),
        'pointerlock_unlock': ('unlock_pointer', [], [], False),
        'pointerlock_locked': ('pointer_locked', [], [], True),
        
        # Stretch
        'stretch_getX': ('stretch_x', [], [], True),
        'stretch_getY': ('stretch_y', [], [], True),
        'stretch_setStretch': ('set_stretch', ['X', 'Y'], [], False),
        'stretch_changeStretch': ('change_stretch', ['DX', 'DY'], [], False),
        
        # Cursor
        'cursor_setCursor': ('set_cursor', ['CURSOR'], [], False),
        'cursor_hideCursor': ('hide_cursor', [], [], False),
        'cursor_showCursor': ('show_cursor', [], [], False),
        'cursor_setCostumeCursor': ('set_costume_cursor', ['COSTUME'], [], False),
        
        # Utilities
        'utilities_true': ('true', [], [], True),
        'utilities_false': ('false', [], [], True),
        'utilities_newline': ('newline', [], [], True),
        'utilities_pi': ('pi', [], [], True),
        'utilities_e': ('euler', [], [], True),
        'utilities_infinity': ('infinity', [], [], True),
        'utilities_isNumber': ('is_number', ['VALUE'], [], True),
        'utilities_isString': ('is_string', ['VALUE'], [], True),
        'utilities_isBoolean': ('is_boolean', ['VALUE'], [], True),
        'utilities_ternary': ('ternary', ['CONDITION', 'TRUE', 'FALSE'], [], True),
        
        # Encoding
        'encoding_encode': ('encode_text', ['TEXT', 'FORMAT'], [], True),
        'encoding_decode': ('decode_text', ['TEXT', 'FORMAT'], [], True),
        
        # RegExp
        'regexp_test': ('regexp_test', ['PATTERN', 'FLAGS', 'STRING'], [], True),
        'regexp_match': ('regexp_match', ['PATTERN', 'FLAGS', 'STRING'], [], True),
        'regexp_replace': ('regexp_replace', ['PATTERN', 'FLAGS', 'STRING', 'REPLACEMENT'], [], True),
        
        # More comparisons
        'morecomparisons_greaterOrEqual': ('greater_or_equal', ['A', 'B'], [], True),
        'morecomparisons_lessOrEqual': ('less_or_equal', ['A', 'B'], [], True),
        'morecomparisons_notEqual': ('not_equal', ['A', 'B'], [], True),
        'morecomparisons_strictlyEquals': ('strictly_equals', ['A', 'B'], [], True),
        'morecomparisons_between': ('between', ['A', 'LOW', 'HIGH'], [], True),
        'morecomparisons_almostEquals': ('almost_equals', ['A', 'B', 'TOLERANCE'], [], True),
        
        # Navigator
        'navigator_language': ('browser_language', [], [], True),
        'navigator_userAgent': ('user_agent', [], [], True),
        'navigator_online': ('is_online', [], [], True),
        'navigator_platform': ('browser_platform', [], [], True),
        
        # Window controls
        'windowcontrols_moveWindow': ('move_window', ['X', 'Y'], [], False),
        'windowcontrols_resizeWindow': ('resize_window', ['WIDTH', 'HEIGHT'], [], False),
        'windowcontrols_getWindowX': ('window_x', [], [], True),
        'windowcontrols_getWindowY': ('window_y', [], [], True),
        'windowcontrols_getWindowWidth': ('window_width', [], [], True),
        'windowcontrols_getWindowHeight': ('window_height', [], [], True),
        'windowcontrols_setTitle': ('set_window_title', ['TITLE'], [], False),
        'windowcontrols_getTitle': ('window_title', [], [], True),
        'windowcontrols_enterFullscreen': ('enter_fullscreen', [], [], False),
        'windowcontrols_exitFullscreen': ('exit_fullscreen', [], [], False),
        
        # Tween
        'tween_tweenValue': ('tween', ['START', 'END', 'AMOUNT', 'MODE'], [], True),
        
        # List tools
        'listtools_getValueIndex': ('list_index_of', ['LIST', 'VALUE'], [], True),
        'listtools_getLastIndex': ('list_last_index_of', ['LIST', 'VALUE'], [], True),
        'listtools_getValuesWithIndex': ('list_get_indices', ['LIST', 'VALUE'], [], True),
        'listtools_copyList': ('list_copy', ['SOURCE', 'DEST'], [], False),
        'listtools_reverse': ('list_reverse', ['LIST'], [], False),
        'listtools_sort': ('list_sort', ['LIST', 'ORDER'], [], False),
        'listtools_shuffle': ('list_shuffle', ['LIST'], [], False),
        
        # Temporary variables
        'tempvars2_set': ('temp_set', ['NAME', 'VALUE'], [], False),
        'tempvars2_change': ('temp_change', ['NAME', 'VALUE'], [], False),
        'tempvars2_get': ('temp_get', ['NAME'], [], True),
        'tempvars2_delete': ('temp_delete', ['NAME'], [], False),
        
        # Note: Simple3D blocks are loaded from felis/extensions/simple3d.felisx
        
        # PenguinMod specific
        'pmSensingExpansion_spriteTouchingXY': ('sprite_touching_xy', ['X', 'Y'], [], True),
        'pmSensingExpansion_mouseClick': ('mouse_clicked', [], [], True),
        'pmSensingExpansion_screenWidth': ('screen_width', [], [], True),
        'pmSensingExpansion_screenHeight': ('screen_height', [], [], True),
        'pmCamera_moveSteps': ('camera_move_steps', ['STEPS'], [], False),
        'pmCamera_setX': ('camera_set_x', ['X'], [], False),
        'pmCamera_setY': ('camera_set_y', ['Y'], [], False),
        'pmCamera_getX': ('camera_x', [], [], True),
        'pmCamera_getY': ('camera_y', [], [], True),
        'pmCamera_setZoom': ('camera_set_zoom', ['ZOOM'], [], False),
        'pmCamera_getZoom': ('camera_zoom', [], [], True),
        
        # Comment blocks (Lily/CommentBlocks)
        'lmscomments_comment': ('_comment_block', [], ['COMMENT'], False),
        'lmscomments_commentHat': ('_comment_hat', [], ['COMMENT'], True),
    }
    
    # Hat blocks specific to extensions
    EXTENSION_HATS = {
        'moreevents_whenValueChanged': ('on_value_changed', ['VALUE']),
        'moreevents_whenBooleanHat': ('on_boolean', ['CONDITION']),
        'moreevents_forever': ('on_forever', []),
        'moreevents_whenKeyAction': ('on_key_action', ['KEY', 'ACTION']),
        'moreevents_whileKeyPressed': ('while_key_pressed', ['KEY']),
        'moreevents_beforeSave': ('before_save', []),
        'moreevents_afterSave': ('after_save', []),
        'gamepad_whenButtonDown': ('on_gamepad_button', ['BUTTON', 'PAD']),
    }
    
    def __init__(self):
        self.ctx = DecompilerContext()
        self.output_lines: List[str] = []
        self.costumes_map: Dict[str, str] = {}  # md5ext -> new filename
        self.sounds_map: Dict[str, str] = {}  # md5ext -> new filename
        self.extracted_assets: Set[str] = set()
        self.list_files: Dict[str, str] = {}  # list_name -> filename for external list files
        self.output_dir: Optional[str] = None  # Store output directory for list file export
        self.project_extensions: List[str] = []  # Extensions declared in project
        
        # Load extensions from .felisx files
        self.ext_loader = ExtensionLoader()
        ext_dir = os.path.join(os.path.dirname(__file__), 'extensions')
        self.ext_loader.load_directory(ext_dir)
        
        # Build opcode -> (felis_name, inputs, fields, is_reporter) mapping from loaded extensions
        self._build_extension_block_map()
    
    def _build_extension_block_map(self):
        """Build additional extension block mappings from loaded .felisx files"""
        for ext_id, ext in self.ext_loader.extensions.items():
            for block in ext.blocks:
                # Skip if already in hardcoded mappings
                if block.opcode in self.EXTENSION_BLOCKS:
                    continue
                
                # Determine if reporter
                is_reporter = block.block_type in ('reporter', 'boolean')
                
                # Extract input names from arguments
                inputs = [arg.name for arg in block.arguments if arg.menu is None]
                fields = [arg.name for arg in block.arguments if arg.menu is not None]
                
                # Add to extension blocks dict
                self.EXTENSION_BLOCKS[block.opcode] = (
                    block.felis_name,
                    inputs,
                    fields,
                    is_reporter
                )
                
                # Also handle hat blocks
                if block.block_type == 'hat':
                    self.EXTENSION_HATS[block.opcode] = (
                        block.felis_name,
                        [arg.name for arg in block.arguments]
                    )
        
    def decompile(self, sb3_path: str, output_dir: Optional[str] = None) -> str:
        self.output_dir = output_dir
        
        with zipfile.ZipFile(sb3_path, 'r') as zf:
            project_json = json.loads(zf.read('project.json'))
            
            # Extract assets if output_dir specified
            if output_dir:
                self._extract_assets(zf, project_json, output_dir)
        
        self.output_lines = []
        
        # Track extensions from project
        self.project_extensions = project_json.get('extensions', [])
        
        # Build context from project
        self._build_context(project_json)
        
        # Emit file header with project info
        meta = project_json.get('meta', {})
        platform = meta.get('platform', {})
        platform_name = platform.get('name', 'Scratch')
        
        self._emit_raw(f"// Decompiled from {os.path.basename(sb3_path)}")
        if platform_name != 'Scratch':
            self._emit_raw(f"// Original platform: {platform_name}")
        if self.project_extensions:
            self._emit_raw(f"// Extensions used: {', '.join(self.project_extensions)}")
        self._emit_raw("")
        
        # Process targets
        for target in project_json['targets']:
            if target['isStage']:
                self._decompile_stage(target, output_dir)
            else:
                self._decompile_sprite(target, output_dir)
        
        # Report unknown blocks at the end
        self._report_unknown_blocks()
        
        return '\n'.join(self.output_lines)
    
    def _extract_assets(self, zf: zipfile.ZipFile, project: dict, output_dir: str):
        costumes_dir = os.path.join(output_dir, 'costumes')
        sounds_dir = os.path.join(output_dir, 'sounds')
        os.makedirs(costumes_dir, exist_ok=True)
        os.makedirs(sounds_dir, exist_ok=True)
        
        # Track used names to avoid collisions
        used_costume_names: Dict[str, int] = {}
        used_sound_names: Dict[str, int] = {}
        
        for target in project['targets']:
            target_name = self._sanitize_name(target['name']) if not target['isStage'] else 'stage'
            
            # Extract costumes
            for costume in target.get('costumes', []):
                md5ext = costume.get('md5ext', '')
                if not md5ext or md5ext in self.extracted_assets:
                    continue
                
                name = costume.get('name', 'costume')
                ext = os.path.splitext(md5ext)[1]
                
                # Generate unique filename
                base_name = f"{target_name}_{self._sanitize_name(name)}"
                if base_name in used_costume_names:
                    used_costume_names[base_name] += 1
                    filename = f"{base_name}_{used_costume_names[base_name]}{ext}"
                else:
                    used_costume_names[base_name] = 0
                    filename = f"{base_name}{ext}"
                
                # Extract file
                try:
                    data = zf.read(md5ext)
                    filepath = os.path.join(costumes_dir, filename)
                    with open(filepath, 'wb') as f:
                        f.write(data)
                    self.costumes_map[md5ext] = f"costumes/{filename}"
                    self.extracted_assets.add(md5ext)
                except KeyError:
                    pass
            
            # Extract sounds
            for sound in target.get('sounds', []):
                md5ext = sound.get('md5ext', '')
                if not md5ext or md5ext in self.extracted_assets:
                    continue
                
                name = sound.get('name', 'sound')
                ext = os.path.splitext(md5ext)[1]
                
                # Generate unique filename
                base_name = f"{target_name}_{self._sanitize_name(name)}"
                if base_name in used_sound_names:
                    used_sound_names[base_name] += 1
                    filename = f"{base_name}_{used_sound_names[base_name]}{ext}"
                else:
                    used_sound_names[base_name] = 0
                    filename = f"{base_name}{ext}"
                
                # Extract file
                try:
                    data = zf.read(md5ext)
                    filepath = os.path.join(sounds_dir, filename)
                    with open(filepath, 'wb') as f:
                        f.write(data)
                    self.sounds_map[md5ext] = f"sounds/{filename}"
                    self.extracted_assets.add(md5ext)
                except KeyError:
                    pass
    
    def _build_context(self, project: dict):
        for target in project['targets']:
            is_stage = target.get('isStage', False)
            # Variables
            for var_id, var_data in target.get('variables', {}).items():
                self.ctx.variables[var_id] = var_data[0]
                # Track stage variables (global scope)
                if is_stage:
                    self.ctx.stage_variables.add(self._sanitize_name(var_data[0]))
            # Lists
            for list_id, list_data in target.get('lists', {}).items():
                self.ctx.lists[list_id] = list_data[0]
                # Track stage lists (global scope)
                if is_stage:
                    self.ctx.stage_lists.add(self._sanitize_name(list_data[0]))
            # Broadcasts
            for bc_id, bc_name in target.get('broadcasts', {}).items():
                self.ctx.broadcasts[bc_id] = bc_name
    
    def _indent(self) -> str:
        return "    " * self.ctx.indent
    
    def _emit(self, line: str):
        self.output_lines.append(self._indent() + line)
    
    def _emit_raw(self, line: str):
        self.output_lines.append(line)
    
    def _load_comments(self, target: dict):
        """Load comments from target and build block->comment mapping"""
        self.ctx.comments.clear()
        self.ctx.block_comments.clear()
        
        for comment_id, comment_data in target.get('comments', {}).items():
            self.ctx.comments[comment_id] = comment_data
            block_id = comment_data.get('blockId')
            if block_id:
                self.ctx.block_comments[block_id] = comment_id
    
    def _emit_floating_comments(self, target: dict):
        """Emit comments that are not attached to any block"""
        floating_comments = []
        for comment_id, comment_data in self.ctx.comments.items():
            if comment_data.get('blockId') is None:
                text = comment_data.get('text', '')
                if text.strip():
                    floating_comments.append((comment_data.get('y', 0), text))
        
        # Sort by Y position (top to bottom)
        floating_comments.sort(key=lambda x: x[0])
        
        for _, text in floating_comments:
            for line in text.split('\n'):
                self._emit_raw(f"// {line}")
        
        if floating_comments:
            self._emit_raw("")
    
    def _get_block_comment(self, block_id: str) -> Optional[str]:
        """Get comment text attached to a block, if any"""
        comment_id = self.ctx.block_comments.get(block_id)
        if comment_id and comment_id in self.ctx.comments:
            return self.ctx.comments[comment_id].get('text', '')
        return None
    
    def _emit_with_comment(self, line: str, block_id: str):
        """Emit a line with inline comment if block has one attached"""
        comment = self._get_block_comment(block_id)
        if comment:
            # For multi-line comments, put them on their own line before
            if '\n' in comment:
                for cline in comment.split('\n'):
                    self._emit(f"// {cline}")
                self._emit(line)
            else:
                # Single line comment goes inline
                self._emit(f"{line}  // {comment}")
        else:
            self._emit(line)
    
    def _track_extension(self, opcode: str):
        """Track which extension an opcode belongs to"""
        if '_' in opcode:
            ext_prefix = opcode.split('_')[0]
            # Map common prefixes to extension names
            ext_map = {
                'tw': 'TurboWarp',
                'runtime': 'runtime-options',
                'files': 'files',
                'fetch': 'fetch',
                'clipboard': 'clipboard',
                'localStorage': 'local-storage',
                'json': 'Skyhigh173/json',
                'text': 'text',
                'bitwise': 'bitwise',
                'clonesplus': 'Lily/ClonesPlus',
                'looksplus': 'Lily/LooksPlus',
                'soundexpanded': 'Lily/SoundExpanded',
                'moreevents': 'Lily/MoreEvents',
                'moremotion': 'NexusKitten/moremotion',
                'gamepad': 'gamepad',
                'pointerlock': 'pointerlock',
                'stretch': 'stretch',
                'cursor': 'cursor',
                'utilities': 'utilities',
                'encoding': 'encoding',
                'regexp': 'true-fantom/regexp',
                'morecomparisons': 'NOname-awa/more-comparisons',
                'navigator': 'navigator',
                'windowcontrols': 'CubesterYT/WindowControls',
                'tween': 'JeremyGamer13/tween',
                'listtools': 'Lily/ListTools',
                'tempvars2': 'Lily/TempVariables2',
                'simple3D': 'Xeltalliv/simple3D',
                'pmSensingExpansion': 'PenguinMod Sensing',
                'pmCamera': 'PenguinMod Camera',
                'lmscomments': 'Lily/CommentBlocks',
            }
            if ext_prefix in ext_map:
                self.ctx.extensions_used.add(ext_map[ext_prefix])
            else:
                self.ctx.extensions_used.add(ext_prefix)
    
    def _sanitize_name(self, name: str) -> str:
        result = ""
        for c in name:
            if c.isalnum() or c == '_':
                result += c
            else:
                result += '_'
        if result and result[0].isdigit():
            result = '_' + result
        result = result or '_unnamed'
        
        # Check for reserved words (case-insensitive)
        if result.lower() in RESERVED_WORDS:
            result = result + '_'
        
        return result
    
    def _get_asset_path(self, md5ext: str, is_sound: bool = False) -> str:
        if is_sound:
            return self.sounds_map.get(md5ext, md5ext)
        return self.costumes_map.get(md5ext, md5ext)
    
    def _escape_string(self, s: str) -> str:
        return s.replace('\\', '\\\\').replace('"', '\\"').replace('\n', '\\n').replace('\r', '\\r')
    
    def _decompile_stage(self, target: dict, output_dir: Optional[str]):
        # Reset custom block tracking for this target
        self.ctx.custom_blocks.clear()
        self.ctx.called_proccodes.clear()
        self.ctx.defined_proccodes.clear()
        self.ctx.used_variables.clear()
        self.ctx.declared_variables.clear()
        
        # Load comments for this target
        self._load_comments(target)
        
        # Emit floating comments first (not attached to blocks)
        self._emit_floating_comments(target)
        
        self._emit_raw("stage {")
        self.ctx.indent = 1
        self.ctx.current_sprite = "Stage"
        
        # Costumes (backdrops)
        if target.get('costumes'):
            self._emit("costumes {")
            self.ctx.indent = 2
            used_names: Dict[str, int] = {}
            for costume in target['costumes']:
                base_name = self._sanitize_name(costume['name'])
                md5ext = costume.get('md5ext', 'backdrop.svg')
                path = self._get_asset_path(md5ext)
                # Ensure unique name
                if base_name in used_names:
                    used_names[base_name] += 1
                    name = f"{base_name}_{used_names[base_name]}"
                else:
                    used_names[base_name] = 0
                    name = base_name
                self._emit(f'{name}: "{path}"')
            self.ctx.indent = 1
            self._emit("}")
            self._emit("")
        
        # Sounds
        if target.get('sounds'):
            self._emit("sounds {")
            self.ctx.indent = 2
            for sound in target['sounds']:
                name = self._sanitize_name(sound['name'])
                md5ext = sound.get('md5ext', 'sound.wav')
                path = self._get_asset_path(md5ext, is_sound=True)
                self._emit(f'{name}: "{path}"')
            self.ctx.indent = 1
            self._emit("}")
            self._emit("")
        
        # Variables
        self._emit_variables(target)
        
        # Scripts
        self._decompile_scripts(target)
        
        self.ctx.indent = 0
        self._emit_raw("}")
        self._emit_raw("")
    
    def _decompile_sprite(self, target: dict, output_dir: Optional[str]):
        # Reset custom block tracking for this sprite
        self.ctx.custom_blocks.clear()
        self.ctx.called_proccodes.clear()
        self.ctx.defined_proccodes.clear()
        self.ctx.used_variables.clear()
        self.ctx.declared_variables.clear()
        
        # Load comments for this target
        self._load_comments(target)
        
        original_name = target['name']
        sprite_name = self._sanitize_name(original_name)
        
        # Emit floating comments first (not attached to blocks)
        self._emit_floating_comments(target)
        
        # Sprite attributes (before the brace)
        attrs = []
        
        # Display name if different from sanitized name
        if sprite_name != original_name:
            attrs.append(f'@name = "{self._escape_string(original_name)}"')
        
        # Position
        x = target.get('x', 0)
        y = target.get('y', 0)
        if x != 0:
            attrs.append(f'@x = {x}')
        if y != 0:
            attrs.append(f'@y = {y}')
        
        # Size
        size = target.get('size', 100)
        if size != 100:
            attrs.append(f'@size = {size}')
        
        # Direction
        direction = target.get('direction', 90)
        if direction != 90:
            attrs.append(f'@direction = {direction}')
        
        # Rotation style
        if target.get('rotationStyle') == 'left-right':
            attrs.append('@rotation = "left-right"')
        elif target.get('rotationStyle') == "don't rotate":
            attrs.append('@rotation = "none"')
        
        # Visibility
        if not target.get('visible', True):
            attrs.append('@visible = false')
        
        # Note: draggable not currently supported by parser
        # if target.get('draggable', False):
        #     attrs.append('@draggable = true')
        
        attr_str = ' ' + ' '.join(attrs) if attrs else ''
        self._emit_raw(f"sprite {sprite_name}{attr_str} {{")
        self.ctx.indent = 1
        self.ctx.current_sprite = target['name']
        
        # Costumes
        if target.get('costumes'):
            self._emit("costumes {")
            self.ctx.indent = 2
            used_names: Dict[str, int] = {}
            for costume in target['costumes']:
                base_name = self._sanitize_name(costume['name'])
                md5ext = costume.get('md5ext', 'costume.svg')
                path = self._get_asset_path(md5ext)
                # Ensure unique name
                if base_name in used_names:
                    used_names[base_name] += 1
                    name = f"{base_name}_{used_names[base_name]}"
                else:
                    used_names[base_name] = 0
                    name = base_name
                self._emit(f'{name}: "{path}"')
            self.ctx.indent = 1
            self._emit("}")
            self._emit("")
        
        # Sounds
        if target.get('sounds'):
            self._emit("sounds {")
            self.ctx.indent = 2
            for sound in target['sounds']:
                name = self._sanitize_name(sound['name'])
                md5ext = sound.get('md5ext', 'sound.wav')
                path = self._get_asset_path(md5ext, is_sound=True)
                self._emit(f'{name}: "{path}"')
            self.ctx.indent = 1
            self._emit("}")
            self._emit("")
        
        # First pass: collect used variables from scripts
        self.ctx.used_variables = set()
        self._collect_used_variables(target)
        
        # Variables (including auto-declared ones)
        self._emit_variables(target)
        
        # Scripts
        self._decompile_scripts(target)
        
        self.ctx.indent = 0
        self._emit_raw("}")
        self._emit_raw("")
    
    def _collect_used_variables(self, target: dict):
        """First pass to collect all variable names used in scripts."""
        blocks = target.get('blocks', {})
        for block_id, block in blocks.items():
            if isinstance(block, dict):
                self._collect_vars_from_block(block, blocks)
    
    def _collect_vars_from_block(self, block: dict, blocks: dict):
        """Recursively collect variable names from a block and its inputs."""
        opcode = block.get('opcode', '')
        
        # Variable setters/changers
        if opcode in ('data_setvariableto', 'data_changevariableby'):
            fields = block.get('fields', {})
            var_field = fields.get('VARIABLE', [])
            if var_field:
                var_name = self._sanitize_name(var_field[0])
                self.ctx.used_variables.add(var_name)
        
        # Check inputs for variable references
        for input_name, input_val in block.get('inputs', {}).items():
            if isinstance(input_val, list) and len(input_val) >= 2:
                inner = input_val[1]
                # Variable reference [12, "varname", "varid"]
                if isinstance(inner, list) and len(inner) >= 2 and inner[0] == 12:
                    var_name = self._sanitize_name(inner[1])
                    self.ctx.used_variables.add(var_name)
                # Block reference
                elif isinstance(inner, str) and inner in blocks:
                    self._collect_vars_from_block(blocks[inner], blocks)
        
        # Follow next block
        next_id = block.get('next')
        if next_id and next_id in blocks:
            self._collect_vars_from_block(blocks[next_id], blocks)
    
    def _emit_variables(self, target: dict):
        has_vars = False
        
        # Track declared variables
        self.ctx.declared_variables = set()
        
        for var_id, var_data in target.get('variables', {}).items():
            name = var_data[0]
            value = var_data[1]
            sanitized = self._sanitize_name(name)
            self.ctx.declared_variables.add(sanitized)
            
            # Check if name needed sanitization
            name_attr = ""
            if sanitized != name:
                name_attr = f' @name = "{self._escape_string(name)}"'
            
            if isinstance(value, str):
                escaped = self._escape_string(value)
                self._emit(f'var {sanitized}{name_attr} = "{escaped}"')
            else:
                self._emit(f'var {sanitized}{name_attr} = {value}')
            has_vars = True
        
        for list_id, list_data in target.get('lists', {}).items():
            name = list_data[0]
            values = list_data[1]
            sanitized_name = self._sanitize_name(name)
            
            # Check if name needed sanitization
            name_attr = ""
            if sanitized_name != name:
                name_attr = f' @name = "{self._escape_string(name)}"'
            
            # If list has many items, export to external file
            if values and len(values) > self.MAX_INLINE_LIST_ITEMS and self.output_dir:
                # Export to external .txt file
                list_filename = f"{sanitized_name}.txt"
                list_filepath = os.path.join(self.output_dir, list_filename)
                self._export_list_to_file(values, list_filepath)
                self.list_files[name] = list_filename
                # Emit empty list declaration - compiler will load from file
                self._emit(f'list {sanitized_name}{name_attr} = []  // values in {list_filename}')
            elif values:
                items = []
                for v in values:
                    if isinstance(v, str):
                        items.append(f'"{self._escape_string(v)}"')
                    else:
                        items.append(str(v))
                self._emit(f'list {sanitized_name}{name_attr} = [{", ".join(items)}]')
            else:
                self._emit(f'list {sanitized_name}{name_attr} = []')
            has_vars = True
        
        # Add auto-declared variables (used but not declared in original)
        # Exclude variables that are declared on the stage (global scope)
        undeclared = self.ctx.used_variables - self.ctx.declared_variables - self.ctx.stage_variables
        if undeclared:
            if has_vars:
                self._emit("")
            self._emit("// Auto-declared variables (used but not declared in original)")
            for var_name in sorted(undeclared):
                self._emit(f'var {var_name} = 0')
            has_vars = True
        
        if has_vars:
            self._emit("")
    
    def _export_list_to_file(self, values: List[Any], filepath: str):
        try:
            with open(filepath, 'w', encoding='utf-8') as f:
                for v in values:
                    f.write(str(v) + '\n')
            print(f"  Exported list to {filepath} ({len(values)} items)")
        except Exception as e:
            print(f"  Warning: Failed to export list to {filepath}: {e}")
    
    def _decompile_scripts(self, target: dict):
        blocks = target.get('blocks', {})
        
        # Find all top-level blocks (hat blocks)
        top_blocks = []
        for block_id, block in blocks.items():
            if isinstance(block, dict) and block.get('topLevel', False):
                top_blocks.append((block_id, block))
        
        # First pass: collect custom block definitions
        for block_id, block in top_blocks:
            if block.get('opcode') == 'procedures_definition':
                self._register_custom_block(block_id, block, blocks)
        
        # Decompile custom blocks first
        for block_id, block in top_blocks:
            if block.get('opcode') == 'procedures_definition':
                self._decompile_custom_block(block_id, block, blocks)
                self._emit("")
        
        # Valid hat block opcodes
        hat_opcodes = {
            'event_whenflagclicked',
            'event_whenkeypressed',
            'event_whenthisspriteclicked',
            'event_whenstageclicked',
            'event_whenbroadcastreceived',
            'control_start_as_clone',
            'event_whenbackdropswitchesto',
            'event_whengreaterthan',
        }
        
        # Add extension hat blocks
        hat_opcodes.update(self.EXTENSION_HATS.keys())
        
        # Decompile event handlers
        for block_id, block in top_blocks:
            opcode = block.get('opcode', '')
            if opcode != 'procedures_definition':
                if opcode in hat_opcodes or opcode.startswith(('event_', 'moreevents_', 'gamepad_when')):
                    self._decompile_hat_block(block_id, block, blocks)
                    self._emit("")
        
        # Decompile orphan blocks (top-level blocks that aren't hat blocks)
        # These are blocks that exist but aren't attached to any event - we comment them out
        orphan_blocks = []
        for block_id, block in top_blocks:
            opcode = block.get('opcode', '')
            if opcode != 'procedures_definition':
                if opcode not in hat_opcodes and not opcode.startswith(('event_', 'moreevents_', 'gamepad_when')):
                    # This is an orphan block - collect it
                    orphan_blocks.append((block_id, block))
        
        if orphan_blocks:
            self._emit("/*")
            self._emit("  === ORPHAN BLOCKS (not attached to any event) ===")
            self._emit("  These blocks existed in the original project but weren't connected to any hat block.")
            self._emit("  They have been commented out. To use them, move them into an event handler.")
            self._emit("")
            for block_id, block in orphan_blocks:
                self._decompile_orphan_block(block_id, block, blocks)
            self._emit("*/")
            self._emit("")
        
        # Generate stubs for undefined custom blocks
        self._generate_undefined_custom_block_stubs()
        
        # Note: undeclared variables are now handled in _emit_variables() 
        # after first pass collects used_variables
    
    def _register_custom_block(self, block_id: str, block: dict, blocks: dict):
        proto_id = block.get('inputs', {}).get('custom_block', [None, None])[1]
        if proto_id and proto_id in blocks:
            proto = blocks[proto_id]
            mutation = proto.get('mutation', {})
            proccode = mutation.get('proccode', 'unknown')
            arg_ids = json.loads(mutation.get('argumentids', '[]'))
            arg_names = json.loads(mutation.get('argumentnames', '[]'))
            warp = mutation.get('warp', 'false') == 'true' or mutation.get('warp') == True
            
            self.ctx.custom_blocks[proto_id] = {
                'proccode': proccode,
                'arg_ids': arg_ids,
                'arg_names': arg_names,
                'warp': warp
            }
            # Track defined proccodes
            self.ctx.defined_proccodes.add(proccode)
    
    def _generate_undefined_custom_block_stubs(self):
        undefined = self.ctx.called_proccodes - self.ctx.defined_proccodes
        if undefined:
            self._emit("    // === STUBS FOR UNDEFINED CUSTOM BLOCKS ===")
            for proccode in sorted(undefined):
                # Parse the proccode to extract function name and parameters
                func_name = proccode.split('%')[0].strip().replace(' ', '_').lower()
                func_name = self._sanitize_name(func_name) if func_name else "custom_block"
                
                # Count parameters by counting % placeholders
                import re
                params = re.findall(r'%[sbn]', proccode)
                param_names = [f"arg{i+1}" for i in range(len(params))]
                
                params_str = ', '.join(param_names)
                self._emit(f"    define {func_name}({params_str}) {{}} // stub")
            self._emit("")
    
    def _decompile_custom_block(self, block_id: str, block: dict, blocks: dict):
        proto_id = block.get('inputs', {}).get('custom_block', [None, None])[1]
        if not proto_id or proto_id not in self.ctx.custom_blocks:
            return
        
        info = self.ctx.custom_blocks[proto_id]
        proccode = info['proccode']
        arg_names = info['arg_names']
        warp = info['warp']
        
        # Extract function name from proccode (first part before any %)
        func_name_raw = proccode.split('%')[0].strip()
        func_name = func_name_raw.replace(' ', '_').lower()
        if not func_name:
            func_name = "custom_block"
        func_name = self._sanitize_name(func_name)
        
        # Check if we need @name attribute (if original proccode label differs from sanitized name)
        name_attr = ""
        # The proccode label might have spaces/special chars, so compare the sanitized version
        if func_name_raw and func_name_raw != func_name.replace('_', ' '):
            # Only add @name if the original label is meaningfully different
            # (not just snake_case vs spaces)
            normalized = func_name.replace('_', ' ').lower()
            if func_name_raw.lower() != normalized:
                name_attr = f' @name = "{self._escape_string(func_name_raw)}"'
        
        # Build parameter list with potential @name attributes for each param
        params_str_parts = []
        for name in arg_names:
            sanitized = self._sanitize_name(name)
            if sanitized != name:
                params_str_parts.append(f'{sanitized} @name = "{self._escape_string(name)}"')
            else:
                params_str_parts.append(sanitized)
        
        param_str = ', '.join(params_str_parts)
        warp_str = "warp " if warp else ""
        
        self._emit(f"define {warp_str}{func_name}{name_attr}({param_str}) {{")
        self.ctx.indent += 1
        
        next_id = block.get('next')
        self._decompile_block_chain(next_id, blocks)
        
        self.ctx.indent -= 1
        self._emit("}")
    
    def _decompile_hat_block(self, block_id: str, block: dict, blocks: dict):
        opcode = block.get('opcode', '')
        
        # Check for block comment
        comment = self._get_block_comment(block_id)
        if comment:
            for cline in comment.split('\n'):
                self._emit(f"// {cline}")
        
        if opcode == 'event_whenflagclicked':
            self._emit("on flag {")
        elif opcode == 'event_whenkeypressed':
            key = self._get_field_value(block, 'KEY_OPTION', 'space')
            self._emit(f'on key "{key}" {{')
        elif opcode == 'event_whenthisspriteclicked':
            self._emit("on clicked {")
        elif opcode == 'event_whenstageclicked':
            self._emit("on clicked {")
        elif opcode == 'event_whenbroadcastreceived':
            msg = self._get_field_value(block, 'BROADCAST_OPTION', 'message')
            self._emit(f'on message "{msg}" {{')
        elif opcode == 'control_start_as_clone':
            self._emit("on clone {")
        elif opcode == 'event_whenbackdropswitchesto':
            backdrop = self._get_field_value(block, 'BACKDROP', 'backdrop1')
            self._emit(f'on backdrop "{backdrop}" {{')
        elif opcode == 'event_whengreaterthan':
            what = self._get_field_value(block, 'WHENGREATERTHANMENU', 'LOUDNESS')
            value = self._decompile_input(block, 'VALUE', blocks)
            self._emit(f'on {what.lower()} > {value} {{')
        # Extension hat blocks
        elif opcode in self.EXTENSION_HATS:
            hat_name, inputs = self.EXTENSION_HATS[opcode]
            self._track_extension(opcode)
            args = [self._decompile_input(block, inp, blocks) for inp in inputs]
            args_str = ', '.join(args)
            if args_str:
                self._emit(f'{hat_name}({args_str}) {{')
            else:
                self._emit(f'{hat_name} {{')
        else:
            # Unknown hat - still emit something valid
            self._track_extension(opcode)
            self._emit(f'on flag {{ // unknown hat: {opcode}')
        
        self.ctx.indent += 1
        next_id = block.get('next')
        self._decompile_block_chain(next_id, blocks)
        self.ctx.indent -= 1
        self._emit("}")
    
    def _decompile_orphan_block(self, block_id: str, block: dict, blocks: dict):
        """Decompile an orphan block (top-level block that's not a hat block)"""
        opcode = block.get('opcode', '')
        
        # Check if it's a reporter/boolean block (single expression)
        if self._is_reporter_opcode(opcode):
            # Check for block comment
            comment = self._get_block_comment(block_id)
            if comment:
                for cline in comment.split('\n'):
                    self._emit(f"// {cline}")
            # Emit as a commented expression
            expr = self._decompile_expression(block_id, block, blocks)
            self._emit(f"// orphan reporter: {expr}")
        else:
            # It's a stack block - decompile the chain
            # _decompile_block will handle the comment
            self._decompile_block(block_id, block, blocks)
            # Continue with any connected blocks
            next_id = block.get('next')
            if next_id:
                self._decompile_block_chain(next_id, blocks)
    
    def _is_reporter_opcode(self, opcode: str) -> bool:
        """Check if an opcode is a reporter/boolean block"""
        reporter_prefixes = (
            'operator_', 'sensing_mouse', 'sensing_answer', 'sensing_timer',
            'sensing_loudness', 'sensing_username', 'sensing_current',
            'sensing_dayssince2000', 'sensing_of', 'sensing_distanceto',
            'sensing_keypressed', 'sensing_mousedown', 'sensing_touching',
            'sensing_coloristouchingcolor', 'data_variable', 'data_listcontents',
            'data_itemoflist', 'data_itemnumoflist', 'data_lengthoflist',
            'data_listcontainsitem', 'motion_xposition', 'motion_yposition',
            'motion_direction', 'looks_costumenumbername', 'looks_backdropnumbername',
            'looks_size', 'sound_volume', 'music_getTempo', 'argument_reporter',
            'tw_', 'sensing_isturbowarp'
        )
        # Check extension blocks
        if opcode in self.EXTENSION_BLOCKS:
            _, _, _, is_reporter = self.EXTENSION_BLOCKS[opcode]
            return is_reporter
        return opcode.startswith(reporter_prefixes)
    
    def _decompile_block_chain(self, block_id: Optional[str], blocks: dict):
        while block_id and block_id in blocks:
            block = blocks[block_id]
            if not isinstance(block, dict):
                break
            self._decompile_block(block_id, block, blocks)
            block_id = block.get('next')
    
    def _decompile_block(self, block_id: str, block: dict, blocks: dict):
        opcode = block.get('opcode', '')
        
        # Check for block comment first
        comment = self._get_block_comment(block_id)
        
        # Helper to emit with optional comment
        def emit(line: str):
            if comment:
                if '\n' in comment:
                    for cline in comment.split('\n'):
                        self._emit(f"// {cline}")
                    self._emit(line)
                else:
                    self._emit(f"{line}  // {comment}")
            else:
                self._emit(line)
        
        # Check if this is a known extension block first
        if opcode in self.EXTENSION_BLOCKS:
            self._track_extension(opcode)
            func_name, inputs, fields, is_reporter = self.EXTENSION_BLOCKS[opcode]
            
            # Skip reporter blocks in statement context (they're orphaned)
            if is_reporter:
                return
                
            args = []
            for inp in inputs:
                args.append(self._decompile_input(block, inp, blocks))
            for fld in fields:
                args.append(f'"{self._get_field_value(block, fld)}"')
            
            args_str = ', '.join(args)
            emit(f"{func_name}({args_str})")
            return
        
        # MOTION
        if opcode == 'motion_movesteps':
            steps = self._decompile_input(block, 'STEPS', blocks)
            emit(f"move({steps})")
        elif opcode == 'motion_turnright':
            deg = self._decompile_input(block, 'DEGREES', blocks)
            emit(f"turn_right({deg})")
        elif opcode == 'motion_turnleft':
            deg = self._decompile_input(block, 'DEGREES', blocks)
            emit(f"turn_left({deg})")
        elif opcode == 'motion_goto':
            target = self._decompile_input(block, 'TO', blocks)
            emit(f"goto({target})")
        elif opcode == 'motion_gotoxy':
            x = self._decompile_input(block, 'X', blocks)
            y = self._decompile_input(block, 'Y', blocks)
            emit(f"goto {x}, {y}")
        elif opcode == 'motion_glideto':
            secs = self._decompile_input(block, 'SECS', blocks)
            target = self._decompile_input(block, 'TO', blocks)
            emit(f"glide({secs}, {target})")
        elif opcode == 'motion_glidesecstoxy':
            secs = self._decompile_input(block, 'SECS', blocks)
            x = self._decompile_input(block, 'X', blocks)
            y = self._decompile_input(block, 'Y', blocks)
            emit(f"glide({secs}, {x}, {y})")
        elif opcode == 'motion_pointindirection':
            dir_val = self._decompile_input(block, 'DIRECTION', blocks)
            emit(f"point_in_direction({dir_val})")
        elif opcode == 'motion_pointtowards':
            target = self._decompile_input(block, 'TOWARDS', blocks)
            emit(f"point_towards({target})")
        elif opcode == 'motion_changexby':
            dx = self._decompile_input(block, 'DX', blocks)
            emit(f"change x by {dx}")
        elif opcode == 'motion_changeyby':
            dy = self._decompile_input(block, 'DY', blocks)
            emit(f"change y by {dy}")
        elif opcode == 'motion_setx':
            x = self._decompile_input(block, 'X', blocks)
            emit(f"set x = {x}")
        elif opcode == 'motion_sety':
            y = self._decompile_input(block, 'Y', blocks)
            emit(f"set y = {y}")
        elif opcode == 'motion_ifonedgebounce':
            emit("if_on_edge_bounce()")
        elif opcode == 'motion_setrotationstyle':
            style = self._get_field_value(block, 'STYLE', 'all around')
            emit(f'set_rotation_style("{style}")')
            
        # LOOKS
        elif opcode == 'looks_say':
            msg = self._decompile_input(block, 'MESSAGE', blocks)
            emit(f"say({msg})")
        elif opcode == 'looks_sayforsecs':
            msg = self._decompile_input(block, 'MESSAGE', blocks)
            secs = self._decompile_input(block, 'SECS', blocks)
            emit(f"say({msg}, {secs})")
        elif opcode == 'looks_think':
            msg = self._decompile_input(block, 'MESSAGE', blocks)
            emit(f"think({msg})")
        elif opcode == 'looks_thinkforsecs':
            msg = self._decompile_input(block, 'MESSAGE', blocks)
            secs = self._decompile_input(block, 'SECS', blocks)
            emit(f"think({msg}, {secs})")
        elif opcode == 'looks_show':
            emit("show")
        elif opcode == 'looks_hide':
            emit("hide")
        elif opcode == 'looks_switchcostumeto':
            costume = self._decompile_input(block, 'COSTUME', blocks)
            emit(f"switch costume to {costume}")
        elif opcode == 'looks_nextcostume':
            emit("next_costume()")
        elif opcode == 'looks_switchbackdropto':
            backdrop = self._decompile_input(block, 'BACKDROP', blocks)
            emit(f"switch backdrop to {backdrop}")
        elif opcode == 'looks_nextbackdrop':
            emit("next_backdrop()")
        elif opcode == 'looks_changesizeby':
            change = self._decompile_input(block, 'CHANGE', blocks)
            emit(f"change size by {change}")
        elif opcode == 'looks_setsizeto':
            size = self._decompile_input(block, 'SIZE', blocks)
            emit(f"size = {size}")
        elif opcode == 'looks_changeeffectby':
            effect = self._get_field_value(block, 'EFFECT', 'COLOR')
            change = self._decompile_input(block, 'CHANGE', blocks)
            emit(f'change_effect("{effect}", {change})')
        elif opcode == 'looks_seteffectto':
            effect = self._get_field_value(block, 'EFFECT', 'COLOR')
            value = self._decompile_input(block, 'VALUE', blocks)
            emit(f'set_effect("{effect}", {value})')
        elif opcode == 'looks_cleargraphiceffects':
            emit("clear_graphic_effects()")
        elif opcode == 'looks_gotofrontback':
            where = self._get_field_value(block, 'FRONT_BACK', 'front')
            emit(f'go_to_layer("{where}")')
        elif opcode == 'looks_goforwardbackwardlayers':
            direction = self._get_field_value(block, 'FORWARD_BACKWARD', 'forward')
            num = self._decompile_input(block, 'NUM', blocks)
            emit(f'go_layers("{direction}", {num})')
            
        # SOUND
        elif opcode == 'sound_play':
            sound = self._decompile_input(block, 'SOUND_MENU', blocks)
            emit(f"play_sound({sound})")
        elif opcode == 'sound_playuntildone':
            sound = self._decompile_input(block, 'SOUND_MENU', blocks)
            emit(f"play_sound_until_done({sound})")
        elif opcode == 'sound_stopallsounds':
            emit("stop_all_sounds()")
        elif opcode == 'sound_changevolumeby':
            vol = self._decompile_input(block, 'VOLUME', blocks)
            emit(f"change volume by {vol}")
        elif opcode == 'sound_setvolumeto':
            vol = self._decompile_input(block, 'VOLUME', blocks)
            emit(f"volume = {vol}")
        elif opcode == 'sound_changeeffectby':
            effect = self._get_field_value(block, 'EFFECT', 'PITCH')
            value = self._decompile_input(block, 'VALUE', blocks)
            emit(f'change_effect_sound("{effect}", {value})')
        elif opcode == 'sound_seteffectto':
            effect = self._get_field_value(block, 'EFFECT', 'PITCH')
            value = self._decompile_input(block, 'VALUE', blocks)
            emit(f'set_effect_sound("{effect}", {value})')
        elif opcode == 'sound_cleareffects':
            emit("clear_sound_effects()")
            
        # EVENTS
        elif opcode == 'event_broadcast':
            msg = self._decompile_input(block, 'BROADCAST_INPUT', blocks)
            emit(f"broadcast({msg})")
        elif opcode == 'event_broadcastandwait':
            msg = self._decompile_input(block, 'BROADCAST_INPUT', blocks)
            emit(f"broadcast_and_wait({msg})")
            
        # CONTROL
        elif opcode == 'control_wait':
            duration = self._decompile_input(block, 'DURATION', blocks)
            emit(f"wait({duration})")
        elif opcode == 'control_repeat':
            times = self._decompile_input(block, 'TIMES', blocks)
            emit(f"repeat {times} {{")
            self.ctx.indent += 1
            substack = self._get_substack(block, 'SUBSTACK', blocks)
            self._decompile_block_chain(substack, blocks)
            self.ctx.indent -= 1
            emit("}")
        elif opcode == 'control_forever':
            emit("forever {")
            self.ctx.indent += 1
            substack = self._get_substack(block, 'SUBSTACK', blocks)
            self._decompile_block_chain(substack, blocks)
            self.ctx.indent -= 1
            emit("}")
        elif opcode == 'control_if':
            cond = self._decompile_input(block, 'CONDITION', blocks)
            emit(f"if {cond} {{")
            self.ctx.indent += 1
            substack = self._get_substack(block, 'SUBSTACK', blocks)
            self._decompile_block_chain(substack, blocks)
            self.ctx.indent -= 1
            emit("}")
        elif opcode == 'control_if_else':
            cond = self._decompile_input(block, 'CONDITION', blocks)
            emit(f"if {cond} {{")
            self.ctx.indent += 1
            substack = self._get_substack(block, 'SUBSTACK', blocks)
            self._decompile_block_chain(substack, blocks)
            self.ctx.indent -= 1
            emit("} else {")
            self.ctx.indent += 1
            substack2 = self._get_substack(block, 'SUBSTACK2', blocks)
            self._decompile_block_chain(substack2, blocks)
            self.ctx.indent -= 1
            emit("}")
        elif opcode == 'control_wait_until':
            cond = self._decompile_input(block, 'CONDITION', blocks)
            emit(f"wait_until({cond})")
        elif opcode == 'control_repeat_until':
            cond = self._decompile_input(block, 'CONDITION', blocks)
            emit(f"until {cond} {{")
            self.ctx.indent += 1
            substack = self._get_substack(block, 'SUBSTACK', blocks)
            self._decompile_block_chain(substack, blocks)
            self.ctx.indent -= 1
            emit("}")
        elif opcode == 'control_while':  # TurboWarp extension
            cond = self._decompile_input(block, 'CONDITION', blocks)
            emit(f"while {cond} {{")
            self.ctx.indent += 1
            substack = self._get_substack(block, 'SUBSTACK', blocks)
            self._decompile_block_chain(substack, blocks)
            self.ctx.indent -= 1
            emit("}")
        elif opcode == 'control_for_each':  # TurboWarp extension
            var = self._get_field_value(block, 'VARIABLE', 'i')
            value = self._decompile_input(block, 'VALUE', blocks)
            var_name = self._sanitize_name(var)
            # Felis doesn't support for loops natively, use repeat with manual counter
            emit(f"set {var_name} = 0")
            emit(f"repeat {value} {{")
            self.ctx.indent += 1
            emit(f"change {var_name} by 1")
            substack = self._get_substack(block, 'SUBSTACK', blocks)
            self._decompile_block_chain(substack, blocks)
            self.ctx.indent -= 1
            emit("}")
        elif opcode == 'control_stop':
            option = self._get_field_value(block, 'STOP_OPTION', 'all')
            emit(f'stop "{option}"')
        elif opcode == 'control_create_clone_of':
            target = self._decompile_input(block, 'CLONE_OPTION', blocks)
            if target == '"_myself_"':
                emit("create clone of myself")
            else:
                emit(f"create clone of {target}")
        elif opcode == 'control_delete_this_clone':
            emit("delete_clone()")
        elif opcode == 'control_all_at_once':  # Experimental
            emit("all_at_once {")
            self.ctx.indent += 1
            substack = self._get_substack(block, 'SUBSTACK', blocks)
            self._decompile_block_chain(substack, blocks)
            self.ctx.indent -= 1
            emit("}")
            
        # SENSING
        elif opcode == 'sensing_askandwait':
            question = self._decompile_input(block, 'QUESTION', blocks)
            emit(f"ask({question})")
        elif opcode == 'sensing_resettimer':
            emit("reset_timer()")
        elif opcode == 'sensing_setdragmode':
            mode = self._get_field_value(block, 'DRAG_MODE', 'draggable')
            emit(f'set_drag_mode("{mode}")')
            
        # DATA
        elif opcode == 'data_setvariableto':
            var_name = self._get_field_value(block, 'VARIABLE', 'var')
            value = self._decompile_input(block, 'VALUE', blocks)
            sanitized = self._sanitize_name(var_name)
            self.ctx.used_variables.add(sanitized)
            emit(f"set {sanitized} = {value}")
        elif opcode == 'data_changevariableby':
            var_name = self._get_field_value(block, 'VARIABLE', 'var')
            value = self._decompile_input(block, 'VALUE', blocks)
            sanitized = self._sanitize_name(var_name)
            self.ctx.used_variables.add(sanitized)
            emit(f"change {sanitized} by {value}")
        elif opcode == 'data_showvariable':
            var_name = self._get_field_value(block, 'VARIABLE', 'var')
            emit(f'show_variable("{var_name}")')
        elif opcode == 'data_hidevariable':
            var_name = self._get_field_value(block, 'VARIABLE', 'var')
            emit(f'hide_variable("{var_name}")')
        elif opcode == 'data_showlist':
            list_name = self._get_field_value(block, 'LIST', 'list')
            emit(f'show_list("{list_name}")')
        elif opcode == 'data_hidelist':
            list_name = self._get_field_value(block, 'LIST', 'list')
            emit(f'hide_list("{list_name}")')
        elif opcode == 'data_addtolist':
            list_name = self._get_field_value(block, 'LIST', 'list')
            item = self._decompile_input(block, 'ITEM', blocks)
            emit(f"add {item} to {self._sanitize_name(list_name)}")
        elif opcode == 'data_deleteoflist':
            list_name = self._get_field_value(block, 'LIST', 'list')
            index = self._decompile_input(block, 'INDEX', blocks)
            emit(f"delete {index} from {self._sanitize_name(list_name)}")
        elif opcode == 'data_deletealloflist':
            list_name = self._get_field_value(block, 'LIST', 'list')
            emit(f"delete all from {self._sanitize_name(list_name)}")
        elif opcode == 'data_insertatlist':
            list_name = self._get_field_value(block, 'LIST', 'list')
            item = self._decompile_input(block, 'ITEM', blocks)
            index = self._decompile_input(block, 'INDEX', blocks)
            emit(f"insert {item} at {index} of {self._sanitize_name(list_name)}")
        elif opcode == 'data_replaceitemoflist':
            list_name = self._get_field_value(block, 'LIST', 'list')
            item = self._decompile_input(block, 'ITEM', blocks)
            index = self._decompile_input(block, 'INDEX', blocks)
            emit(f"replace {index} of {self._sanitize_name(list_name)} with {item}")
            
        # PEN
        elif opcode == 'pen_clear':
            emit("erase_all()")
        elif opcode == 'pen_stamp':
            emit("stamp")
        elif opcode == 'pen_penDown':
            emit("pen_down()")
        elif opcode == 'pen_penUp':
            emit("pen_up()")
        elif opcode == 'pen_setPenColorToColor':
            color = self._decompile_input(block, 'COLOR', blocks)
            emit(f"set_pen_color({color})")
        elif opcode == 'pen_changePenColorParamBy':
            param = self._get_field_value(block, 'COLOR_PARAM', 'color')
            value = self._decompile_input(block, 'VALUE', blocks)
            emit(f'change_pen_param("{param}", {value})')
        elif opcode == 'pen_setPenColorParamTo':
            param = self._get_field_value(block, 'COLOR_PARAM', 'color')
            value = self._decompile_input(block, 'VALUE', blocks)
            emit(f'set_pen_param("{param}", {value})')
        elif opcode == 'pen_setPenSizeTo':
            size = self._decompile_input(block, 'SIZE', blocks)
            emit(f"set_pen_size({size})")
        elif opcode == 'pen_changePenSizeBy':
            size = self._decompile_input(block, 'SIZE', blocks)
            emit(f"change_pen_size({size})")
        elif opcode == 'pen_setPenShadeToNumber':
            shade = self._decompile_input(block, 'SHADE', blocks)
            emit(f"set_pen_shade({shade})")
        elif opcode == 'pen_changePenShadeBy':
            shade = self._decompile_input(block, 'SHADE', blocks)
            emit(f"change_pen_shade({shade})")
        elif opcode == 'pen_setPenHueToNumber':
            hue = self._decompile_input(block, 'HUE', blocks)
            emit(f"set_pen_hue({hue})")
        elif opcode == 'pen_changePenHueBy':
            hue = self._decompile_input(block, 'HUE', blocks)
            emit(f"change_pen_hue({hue})")
            
        # MUSIC
        elif opcode == 'music_playDrumForBeats':
            drum = self._decompile_input(block, 'DRUM', blocks)
            beats = self._decompile_input(block, 'BEATS', blocks)
            emit(f"play_drum({drum}, {beats})")
        elif opcode == 'music_restForBeats':
            beats = self._decompile_input(block, 'BEATS', blocks)
            emit(f"rest({beats})")
        elif opcode == 'music_playNoteForBeats':
            note = self._decompile_input(block, 'NOTE', blocks)
            beats = self._decompile_input(block, 'BEATS', blocks)
            emit(f"play_note({note}, {beats})")
        elif opcode == 'music_setInstrument':
            instrument = self._decompile_input(block, 'INSTRUMENT', blocks)
            emit(f"set_instrument({instrument})")
        elif opcode == 'music_setTempo':
            tempo = self._decompile_input(block, 'TEMPO', blocks)
            emit(f"set_tempo({tempo})")
        elif opcode == 'music_changeTempo':
            tempo = self._decompile_input(block, 'TEMPO', blocks)
            emit(f"change_tempo({tempo})")
            
        # custom block call
        elif opcode == 'procedures_call':
            mutation = block.get('mutation', {})
            proccode = mutation.get('proccode', 'unknown')
            arg_ids = json.loads(mutation.get('argumentids', '[]'))
            arg_names = json.loads(mutation.get('argumentnames', '[]'))
            
            # Track this call
            self.ctx.called_proccodes.add(proccode)
            
            func_name = proccode.split('%')[0].strip().replace(' ', '_').lower()
            func_name = self._sanitize_name(func_name) if func_name else "custom_block"
            
            args = []
            for arg_id in arg_ids:
                arg_val = self._decompile_input(block, arg_id, blocks)
                args.append(arg_val)
            
            args_str = ', '.join(args)
            emit(f"{func_name}({args_str})")
        
        # Skip procedure prototypes and definitions (handled separately)
        elif opcode in ('procedures_prototype', 'procedures_definition'):
            pass
        
        # extensions / unknown
        else:
            # Track unknown block and its extension for later reporting
            self._track_extension(opcode)
            self.ctx.unknown_blocks.add(opcode)
            
            # Generate a function-style call for unknown opcodes
            inputs_parts = []
            input_names = []
            for k in block.get('inputs', {}).keys():
                inputs_parts.append(self._decompile_input(block, k, blocks))
                input_names.append(k.lower())
            for k in block.get('fields', {}).keys():
                val = self._get_field_value(block, k)
                inputs_parts.append(f'"{val}"')
                input_names.append(k.lower())
            
            args_str = ', '.join(inputs_parts)
            # Convert opcode to snake_case function name
            func_name = self._opcode_to_func_name(opcode)
            emit(f"// [UNKNOWN BLOCK: {opcode}]")
            emit(f"{func_name}({args_str})")
    
    def _decompile_input(self, block: dict, input_name: str, blocks: dict) -> str:
        inputs = block.get('inputs', {})
        if input_name not in inputs:
            # Check fields as fallback
            field_val = self._get_field_value(block, input_name)
            if field_val:
                return f'"{self._escape_string(field_val)}"'
            return "0"
        
        input_data = inputs[input_name]
        if not input_data or len(input_data) < 2:
            return "0"
        
        value = input_data[1]
        
        if value is None:
            return "0"
        
        if isinstance(value, str):
            if value in blocks:
                return self._decompile_expression(value, blocks[value], blocks)
            return "0"
        
        if isinstance(value, list):
            if len(value) >= 2:
                lit_type = value[0]
                lit_value = value[1]
                
                if lit_type in (4, 5, 6, 7, 8):  # Numbers
                    # Handle empty string or None as 0
                    if lit_value == '' or lit_value is None:
                        return "0"
                    # Ensure floats like .5 are formatted as 0.5
                    s = str(lit_value)
                    if s.startswith('.'):
                        s = '0' + s
                    elif s.startswith('-.'):
                        s = '-0' + s[1:]
                    return s
                elif lit_type == 9:  # Color
                    return f'"{lit_value}"'
                elif lit_type == 10:  # String
                    escaped = self._escape_string(str(lit_value))
                    return f'"{escaped}"'
                elif lit_type == 11:  # Broadcast
                    escaped = self._escape_string(str(lit_value))
                    return f'"{escaped}"'
                elif lit_type == 12:  # Variable
                    sanitized = self._sanitize_name(lit_value)
                    self.ctx.used_variables.add(sanitized)
                    return sanitized
                elif lit_type == 13:  # List
                    return self._sanitize_name(lit_value)
        
        return "0"
    
    def _decompile_expression(self, block_id: str, block: dict, blocks: dict) -> str:
        opcode = block.get('opcode', '')
        
        # Check if this is a known extension reporter block first
        if opcode in self.EXTENSION_BLOCKS:
            func_name, inputs, fields, is_reporter = self.EXTENSION_BLOCKS[opcode]
            if is_reporter:
                self._track_extension(opcode)
                args = []
                for inp in inputs:
                    args.append(self._decompile_input(block, inp, blocks))
                for fld in fields:
                    args.append(f'"{self._get_field_value(block, fld)}"')
                
                args_str = ', '.join(args)
                if args_str:
                    return f"{func_name}({args_str})"
                else:
                    return func_name
        
        # OPERATORS
        if opcode == 'operator_add':
            a = self._decompile_input(block, 'NUM1', blocks)
            b = self._decompile_input(block, 'NUM2', blocks)
            return f"({a} + {b})"
        elif opcode == 'operator_subtract':
            a = self._decompile_input(block, 'NUM1', blocks)
            b = self._decompile_input(block, 'NUM2', blocks)
            return f"({a} - {b})"
        elif opcode == 'operator_multiply':
            a = self._decompile_input(block, 'NUM1', blocks)
            b = self._decompile_input(block, 'NUM2', blocks)
            return f"({a} * {b})"
        elif opcode == 'operator_divide':
            a = self._decompile_input(block, 'NUM1', blocks)
            b = self._decompile_input(block, 'NUM2', blocks)
            return f"({a} / {b})"
        elif opcode == 'operator_mod':
            a = self._decompile_input(block, 'NUM1', blocks)
            b = self._decompile_input(block, 'NUM2', blocks)
            return f"({a} mod {b})"
        elif opcode == 'operator_random':
            a = self._decompile_input(block, 'FROM', blocks)
            b = self._decompile_input(block, 'TO', blocks)
            return f"random({a}, {b})"
        elif opcode == 'operator_gt':
            a = self._decompile_input(block, 'OPERAND1', blocks)
            b = self._decompile_input(block, 'OPERAND2', blocks)
            return f"({a} > {b})"
        elif opcode == 'operator_lt':
            a = self._decompile_input(block, 'OPERAND1', blocks)
            b = self._decompile_input(block, 'OPERAND2', blocks)
            return f"({a} < {b})"
        elif opcode == 'operator_equals':
            a = self._decompile_input(block, 'OPERAND1', blocks)
            b = self._decompile_input(block, 'OPERAND2', blocks)
            return f"({a} == {b})"
        elif opcode == 'operator_and':
            a = self._decompile_input(block, 'OPERAND1', blocks)
            b = self._decompile_input(block, 'OPERAND2', blocks)
            return f"({a} and {b})"
        elif opcode == 'operator_or':
            a = self._decompile_input(block, 'OPERAND1', blocks)
            b = self._decompile_input(block, 'OPERAND2', blocks)
            return f"({a} or {b})"
        elif opcode == 'operator_not':
            a = self._decompile_input(block, 'OPERAND', blocks)
            return f"(not {a})"
        elif opcode == 'operator_join':
            a = self._decompile_input(block, 'STRING1', blocks)
            b = self._decompile_input(block, 'STRING2', blocks)
            return f"join({a}, {b})"
        elif opcode == 'operator_letter_of':
            idx = self._decompile_input(block, 'LETTER', blocks)
            s = self._decompile_input(block, 'STRING', blocks)
            return f"letter({idx}, {s})"
        elif opcode == 'operator_length':
            s = self._decompile_input(block, 'STRING', blocks)
            return f"length({s})"
        elif opcode == 'operator_contains':
            s1 = self._decompile_input(block, 'STRING1', blocks)
            s2 = self._decompile_input(block, 'STRING2', blocks)
            return f"contains({s1}, {s2})"
        elif opcode == 'operator_round':
            val = self._decompile_input(block, 'NUM', blocks)
            return f"round({val})"
        elif opcode == 'operator_mathop':
            op = self._get_field_value(block, 'OPERATOR', 'abs')
            val = self._decompile_input(block, 'NUM', blocks)
            return f"{op}({val})"
        
        # SENSING
        elif opcode == 'sensing_touchingobject':
            obj = self._decompile_input(block, 'TOUCHINGOBJECTMENU', blocks)
            return f"touching({obj})"
        elif opcode == 'sensing_touchingcolor':
            color = self._decompile_input(block, 'COLOR', blocks)
            return f"touching_color({color})"
        elif opcode == 'sensing_coloristouchingcolor':
            c1 = self._decompile_input(block, 'COLOR', blocks)
            c2 = self._decompile_input(block, 'COLOR2', blocks)
            return f"color_touching_color({c1}, {c2})"
        elif opcode == 'sensing_keypressed':
            key = self._decompile_input(block, 'KEY_OPTION', blocks)
            return f"key_pressed({key})"
        elif opcode == 'sensing_mousedown':
            return "mouse_down()"
        elif opcode == 'sensing_mousex':
            return "mouse_x"
        elif opcode == 'sensing_mousey':
            return "mouse_y"
        elif opcode == 'sensing_distanceto':
            obj = self._decompile_input(block, 'DISTANCETOMENU', blocks)
            return f"distance_to({obj})"
        elif opcode == 'sensing_answer':
            return "answer"
        elif opcode == 'sensing_timer':
            return "timer"
        elif opcode == 'sensing_loudness':
            return "loudness"
        elif opcode == 'sensing_loud':
            return "loud()"
        elif opcode == 'sensing_dayssince2000':
            return "days_since_2000"
        elif opcode == 'sensing_username':
            return "username"
        elif opcode == 'sensing_current':
            what = self._get_field_value(block, 'CURRENTMENU', 'YEAR')
            return f'current("{what.lower()}")'
        elif opcode == 'sensing_of':
            prop = self._get_field_value(block, 'PROPERTY', 'x position')
            obj = self._decompile_input(block, 'OBJECT', blocks)
            return f'attribute_of("{prop}", {obj})'
        
        # motion reporters
        elif opcode == 'motion_xposition':
            return "x"
        elif opcode == 'motion_yposition':
            return "y"
        elif opcode == 'motion_direction':
            return "direction"
        
        # looks reporters
        elif opcode == 'looks_costumenumbername':
            what = self._get_field_value(block, 'NUMBER_NAME', 'number')
            if what == 'name':
                return "costume_name"
            return "costume_number"
        elif opcode == 'looks_backdropnumbername':
            what = self._get_field_value(block, 'NUMBER_NAME', 'number')
            if what == 'name':
                return "backdrop_name"
            return "backdrop_number"
        elif opcode == 'looks_size':
            return "size"
        
        # sound reporters
        elif opcode == 'sound_volume':
            return "volume"
        elif opcode == 'music_getTempo':
            return "tempo"
        
        # data reporters
        elif opcode == 'data_variable':
            var_name = self._get_field_value(block, 'VARIABLE', 'var')
            sanitized = self._sanitize_name(var_name)
            self.ctx.used_variables.add(sanitized)
            return sanitized
        elif opcode == 'data_listcontents':
            list_name = self._get_field_value(block, 'LIST', 'list')
            return self._sanitize_name(list_name)
        elif opcode == 'data_itemoflist':
            list_name = self._get_field_value(block, 'LIST', 'list')
            index = self._decompile_input(block, 'INDEX', blocks)
            return f"item({index}, {self._sanitize_name(list_name)})"
        elif opcode == 'data_itemnumoflist':
            list_name = self._get_field_value(block, 'LIST', 'list')
            item = self._decompile_input(block, 'ITEM', blocks)
            return f"item_index({item}, {self._sanitize_name(list_name)})"
        elif opcode == 'data_lengthoflist':
            list_name = self._get_field_value(block, 'LIST', 'list')
            return f"length({self._sanitize_name(list_name)})"
        elif opcode == 'data_listcontainsitem':
            list_name = self._get_field_value(block, 'LIST', 'list')
            item = self._decompile_input(block, 'ITEM', blocks)
            return f"list_contains({self._sanitize_name(list_name)}, {item})"
        
        # argument reporters
        elif opcode == 'argument_reporter_string_number':
            arg_name = self._get_field_value(block, 'VALUE', 'arg')
            return self._sanitize_name(arg_name)
        elif opcode == 'argument_reporter_boolean':
            arg_name = self._get_field_value(block, 'VALUE', 'arg')
            # TurboWarp special argument reporters
            if arg_name == 'is TurboWarp?':
                return 'is_turbowarp'
            elif arg_name == 'is compiled?':
                return 'is_compiled'
            elif arg_name == 'is fenced?':
                return 'is_fenced'
            return self._sanitize_name(arg_name)
        
        # menu blocks
        elif opcode == 'sensing_keyoptions':
            key = self._get_field_value(block, 'KEY_OPTION', 'space')
            return f'"{key}"'
        elif opcode == 'sensing_touchingobjectmenu':
            obj = self._get_field_value(block, 'TOUCHINGOBJECTMENU', '_mouse_')
            return f'"{obj}"'
        elif opcode == 'sensing_distancetomenu':
            obj = self._get_field_value(block, 'DISTANCETOMENU', '_mouse_')
            return f'"{obj}"'
        elif opcode == 'sensing_of_object_menu':
            obj = self._get_field_value(block, 'OBJECT', '_stage_')
            return f'"{obj}"'
        elif opcode == 'looks_costume':
            costume = self._get_field_value(block, 'COSTUME', 'costume1')
            return f'"{costume}"'
        elif opcode == 'looks_backdrops':
            backdrop = self._get_field_value(block, 'BACKDROP', 'backdrop1')
            return f'"{backdrop}"'
        elif opcode == 'sound_sounds_menu':
            sound = self._get_field_value(block, 'SOUND_MENU', 'pop')
            return f'"{sound}"'
        elif opcode == 'control_create_clone_of_menu':
            option = self._get_field_value(block, 'CLONE_OPTION', '_myself_')
            return f'"{option}"'
        elif opcode == 'motion_goto_menu':
            target = self._get_field_value(block, 'TO', '_random_')
            return f'"{target}"'
        elif opcode == 'motion_glideto_menu':
            target = self._get_field_value(block, 'TO', '_random_')
            return f'"{target}"'
        elif opcode == 'motion_pointtowards_menu':
            target = self._get_field_value(block, 'TOWARDS', '_mouse_')
            return f'"{target}"'
        elif opcode == 'pen_menu_colorParam':
            param = self._get_field_value(block, 'colorParam', 'color')
            return f'"{param}"'
        elif opcode == 'music_menu_DRUM':
            drum = self._get_field_value(block, 'DRUM', '1')
            return drum
        elif opcode == 'music_menu_INSTRUMENT':
            inst = self._get_field_value(block, 'INSTRUMENT', '1')
            return inst
        elif opcode == 'note':
            note = self._get_field_value(block, 'NOTE', '60')
            return note
        
        # TurboWarp menu blocks
        elif opcode == 'tw_menu_mouseButton':
            button = self._get_field_value(block, 'mouseButton', '0')
            return button
        elif opcode.endswith('_menu') or '_menu_' in opcode:
            # Generic menu handling - extract first field value
            fields = block.get('fields', {})
            for key, val in fields.items():
                if val and len(val) >= 1:
                    return f'"{val[0]}"'
            return '"default"'
        
        # turbowarp extensions
        elif opcode in ('tw_isturbowarp', 'sensing_isturbowarp', 'runtime_isturbowarp'):
            return "is_turbowarp"
        elif opcode in ('tw_iscompiled', 'runtime_iscompiled'):
            return "is_compiled"
        elif opcode in ('tw_isfenced', 'runtime_isfenced'):
            return "is_fenced"
        
        # Unknown expression - track it and generate function call style
        self._track_extension(opcode)
        self.ctx.unknown_reporters.add(opcode)
        
        inputs_parts = []
        for k in block.get('inputs', {}).keys():
            inputs_parts.append(self._decompile_input(block, k, blocks))
        for k in block.get('fields', {}).keys():
            val = self._get_field_value(block, k)
            inputs_parts.append(f'"{self._escape_string(val)}"')
        
        args_str = ', '.join(inputs_parts) if inputs_parts else ''
        func_name = self._opcode_to_func_name(opcode)
        return f'{func_name}({args_str})'
    
    def _opcode_to_func_name(self, opcode: str) -> str:
        return opcode.replace('_', '__').lower()
    
    def _report_unknown_blocks(self):
        # Report detected extensions
        if self.ctx.extensions_used:
            print(f"\n  Detected extensions: {', '.join(sorted(self.ctx.extensions_used))}")
        
        if self.ctx.unknown_blocks:
            print(f"\n  Warning: {len(self.ctx.unknown_blocks)} unknown statement block(s) encountered:")
            for opcode in sorted(self.ctx.unknown_blocks):
                print(f"    - {opcode}")
            print("  These have been decompiled as function calls. You may need to create stubs.")
        
        if self.ctx.unknown_reporters:
            print(f"\n  Warning: {len(self.ctx.unknown_reporters)} unknown reporter block(s) encountered:")
            for opcode in sorted(self.ctx.unknown_reporters):
                print(f"    - {opcode}")
            print("  These have been decompiled as function calls. You may need to create stubs.")
    
    def _get_field_value(self, block: dict, field_name: str, default: str = "") -> str:
        fields = block.get('fields', {})
        if field_name in fields:
            field_data = fields[field_name]
            if field_data and len(field_data) >= 1:
                return str(field_data[0])
        return default
    
    def _get_substack(self, block: dict, input_name: str, blocks: dict) -> Optional[str]:
        inputs = block.get('inputs', {})
        if input_name in inputs:
            input_data = inputs[input_name]
            if input_data and len(input_data) >= 2:
                return input_data[1]
        return None


def decompile_sb3(sb3_path: str, output_path: Optional[str] = None, 
                  output_dir: Optional[str] = None) -> str:
    if output_dir is None and output_path:
        output_dir = os.path.dirname(os.path.abspath(output_path))
    
    decompiler = SB3Decompiler()
    source = decompiler.decompile(sb3_path, output_dir)
    
    if output_path:
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(source)
    
    return source


if __name__ == '__main__':
    import sys
    if len(sys.argv) < 2:
        print("Usage: python decompiler.py <input.sb3> [output.felis]")
        sys.exit(1)
    
    input_path = sys.argv[1]
    output_path = sys.argv[2] if len(sys.argv) > 2 else None
    
    source = decompile_sb3(input_path, output_path)
    
    if not output_path:
        print(source)
    else:
        print(f"Decompiled to {output_path}")
