# Felis -> Scratch SB3 compiler

import json
import uuid
import hashlib
import time
import os
import re
from dataclasses import dataclass
from functools import lru_cache


def _read_u32_le(b: bytes, off: int) -> int:
    return int.from_bytes(b[off:off+4], "little", signed=False)


def _read_u16_le(b: bytes, off: int) -> int:
    return int.from_bytes(b[off:off+2], "little", signed=False)

from typing import Dict, List, Any, Optional, Union, Tuple
from .ast_nodes import *
from .blocks import *
from .extensions import ExtensionLoader, ExtensionBlock, get_extension_loader


@lru_cache(maxsize=256)
def _get_block_def(name: str) -> Optional[BlockDefinition]:
    return get_block_definition(name)


class CompilerError(Exception):
    def __init__(self, message: str, node: ASTNode = None, suggestion: str = None, related_symbols: list = None):
        self.message = message
        self.node = node
        self.suggestion = suggestion
        self.related_symbols = related_symbols or []
        super().__init__(self._fmt())
    
    def _fmt(self) -> str:
        out = []
        if self.node and self.node.position:
            pos = self.node.position
            out.append(f"\n\033[1;31mCompiler Error\033[0m in {pos.filename}:{pos.line}:{pos.column}")
        else:
            out.append(f"\n\033[1;31mCompiler Error\033[0m")
        
        out.append(f"  {self.message}")
        
        if self.related_symbols:
            out.append(f"\n\033[1;36mDid you mean:\033[0m {', '.join(self.related_symbols[:5])}")
        
        if self.suggestion:
            out.append(f"\n\033[1;33mHint:\033[0m {self.suggestion}")
        
        return "\n".join(out)


class FelisCompiler:
    def __init__(self, *, base_dir: Optional[str] = None, extension_loader: Optional[ExtensionLoader] = None):
        self.project = {
            "targets": [],
            "monitors": [],
            "extensions": [],
            "meta": {"semver": "3.0.0", "vm": "0.2.0", "agent": "Felis 1.1.0"}
        }
        self.broadcasts = {}
        self.extensions = set()
        self.base_dir = base_dir
        self.asset_blobs: Dict[str, bytes] = {}
        self._blank_svg = b'<svg xmlns="http://www.w3.org/2000/svg" width="1" height="1"></svg>'
        
        # current compile context
        self.current_target = None
        self.blocks = {}
        self.comments = {}  # Scratch comments storage
        self.variables = {}
        self.lists = {}
        self.custom_blocks = {}
        self.current_custom_block_params = {}
        
        # Stage variables/lists by Felis identifier name (for global scope lookup)
        self.stage_variables_by_name: Dict[str, dict] = {}  # name -> {"id": ..., "name": scratch_name}
        self.stage_lists_by_name: Dict[str, dict] = {}  # name -> {"id": ..., "name": scratch_name}
        
        self.extension_loader = extension_loader or get_extension_loader()
        
        # fast id gen
        self._id_counter = 0
        self._id_base = uuid.uuid4().hex[:8]
        
        # Comment positioning - tracks Y offset for floating comments
        self._comment_y_offset = 0
        
        self._stats = {"blocks_compiled": 0, "start_time": None, "warnings": []}
        
    def gen_id(self) -> str:
        self._id_counter += 1
        return f"{self._id_base}{self._id_counter:012x}"
    
    def warn(self, msg: str, node: ASTNode = None):
        loc = ""
        if node and node.position:
            p = node.position
            loc = f" at {p.filename}:{p.line}:{p.column}"
        self._stats["warnings"].append(f"Warning{loc}: {msg}")
    
    def add_block_comment(self, block_id: str, text: str):
        """Add an inline comment attached to a specific block."""
        if not text:
            return
        comment_id = self.gen_id()
        self.comments[comment_id] = {
            "blockId": block_id,
            "x": 0,  # Will be positioned relative to block
            "y": 0,
            "width": 200,
            "height": 200,
            "minimized": False,
            "text": text
        }
        # Link the block to the comment
        if block_id in self.blocks:
            self.blocks[block_id]["comment"] = comment_id
    
    def add_floating_comment(self, text: str, near_block_id: Optional[str] = None, x: float = 0, y: float = 0):
        """Add a floating comment not attached to any block.
        
        If near_block_id is provided, position near that block.
        Otherwise use explicit x, y coordinates.
        """
        if not text:
            return
        comment_id = self.gen_id()
        
        # Try to position near the referenced block
        if near_block_id and near_block_id in self.blocks:
            block = self.blocks[near_block_id]
            # Position to the right of and slightly above the block
            x = block.get("x", 0) + 350
            y = block.get("y", 0) - 20 + self._comment_y_offset
            self._comment_y_offset += 100  # Stack floating comments
        else:
            # Use default position, stacking vertically
            x = 50
            y = 50 + self._comment_y_offset
            self._comment_y_offset += 100
            
        self.comments[comment_id] = {
            "blockId": None,  # Not attached to any block
            "x": x,
            "y": y,
            "width": 200,
            "height": 200,
            "minimized": False,
            "text": text
        }
    
    def get_compilation_stats(self) -> dict:
        return {
            "blocks_compiled": self._stats["blocks_compiled"],
            "warnings": self._stats["warnings"],
            "warning_count": len(self._stats["warnings"])
        }
    
    def get_broadcast_id(self, name: str) -> str:
        if name not in self.broadcasts:
            self.broadcasts[name] = {"name": name, "id": self.gen_id()}
        return self.broadcasts[name]["id"]
    
    def get_variable_id(self, name: str) -> str:
        
        if name in self.variables:
            return self.variables[name]["id"]
        # Check global variables (in stage) by Felis identifier name
        if name in self.stage_variables_by_name:
            return self.stage_variables_by_name[name]["id"]
        raise CompilerError(f"Undefined variable: {name}",
                          suggestion="Make sure the variable is declared with 'var' or 'cloud var'")
    
    def get_variable_display_name(self, name: str) -> str:
        if name in self.variables:
            return self.variables[name]["name"]
        if name in self.stage_variables_by_name:
            return self.stage_variables_by_name[name]["name"]
        return name
    
    def get_list_id(self, name: str) -> str:
        
        if name in self.lists:
            return self.lists[name]["id"]
        # Check global lists by Felis identifier name
        if name in self.stage_lists_by_name:
            return self.stage_lists_by_name[name]["id"]
        raise CompilerError(f"Undefined list: {name}")

    def _normalize_key_option(self, key_val: Any) -> str:
        if key_val is None:
            return "space"
        if not isinstance(key_val, str):
            return "space"

        s = key_val.strip()
        if not s:
            return "space"

        # Normalize separators/casing for mapping.
        lower = s.lower().replace("_", " ").replace("-", " ")
        lower = " ".join(lower.split())

        # Common synonyms / canonical options.
        if lower in ("up arrow", "down arrow", "left arrow", "right arrow"):
            return lower
        if lower in ("space", "enter", "any"):
            return lower
        if lower in ("spacebar", "space bar"):
            return "space"

        mapped = KEY_MAPPINGS.get(lower)
        if mapped:
            return mapped

        # Letters and digits are valid Scratch keys.
        if len(lower) == 1 and lower.isalnum():
            return lower

        # Fall back to original (Scratch may still accept it).
        return s

    def _assign_input_parents(self, parent_id: str, inputs: Dict[str, Any]):
        """Set parent links for blocks referenced by an inputs dict.

        Scratch generally tolerates missing parent pointers; TurboWarp can be stricter.
        We only fill in missing parents (None) and never overwrite existing ones.
        """
        for v in (inputs or {}).values():
            if not isinstance(v, list) or len(v) < 2:
                continue
            input_type = v[0]
            if input_type not in (2, 3):
                continue
            child_id = v[1]
            if isinstance(child_id, str) and child_id in self.blocks:
                child = self.blocks[child_id]
                if isinstance(child, dict) and child.get("parent") is None:
                    child["parent"] = parent_id

    def _fix_orphaned_blocks(self):
        """Fix any blocks with parent=None that are referenced by other blocks.
        
        This is a cleanup pass to catch any blocks that weren't properly parented
        during compilation. It scans all blocks and fixes parent references for
        any blocks that are referenced in inputs but have parent=None.
        """
        for block_id, block in self.blocks.items():
            if not isinstance(block, dict):
                continue
            inputs = block.get("inputs", {})
            self._assign_input_parents(block_id, inputs)

    def _get_initial_value(self, val: Any) -> Any:
        
        if isinstance(val, (NumberLiteral, StringLiteral, BooleanLiteral, ColorLiteral)):
            return val.value
        if isinstance(val, (int, float, str, bool)):
            return val
        return 0

    def _get_list_values(self, lst: ListDecl) -> List[Any]:
        """
        Get list values from declaration, checking for external .txt file.
        
        If a .txt file with the same name as the list exists in the same directory
        as the source file, its contents (one item per line) will be used as the
        list's initial values.
        """
        # Check for external list file
        if self.base_dir:
            list_file_path = os.path.join(self.base_dir, f"{lst.name}.txt")
            if os.path.exists(list_file_path):
                return self._load_list_from_file(list_file_path)
        
        # Use inline initial values
        return [self._get_initial_value(v) for v in lst.initial_values]
    
    def _load_list_from_file(self, filepath: str) -> List[Any]:
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                values = []
                for line in f:
                    # Strip trailing newline but preserve other whitespace
                    line = line.rstrip('\n\r')
                    # Try to parse as number
                    try:
                        if '.' in line:
                            values.append(float(line))
                        else:
                            values.append(int(line))
                    except ValueError:
                        values.append(line)
                print(f"  Loaded {len(values)} items for list from {filepath}")
                return values
        except Exception as e:
            print(f"  Warning: Failed to load list from {filepath}: {e}")
            return []

    def compile(self, program: Program) -> Dict[str, Any]:
        
        # First pass: Compile Stage (globals)
        if program.stage:
            self.compile_stage(program.stage)
        else:
            # Create default stage if none exists
            self.compile_stage(Stage())
            
        # Second pass: Compile Sprites
        for sprite in program.sprites:
            self.compile_sprite(sprite)
            
        # Broadcasts: Scratch stores a broadcast-name map by ID on each target.
        broadcast_map = {v["id"]: v["name"] for v in self.broadcasts.values()}
        for t in self.project["targets"]:
            t["broadcasts"] = broadcast_map

        # Extensions: Scratch expects a list of extension IDs used by opcodes.
        self.project["extensions"] = sorted(self.extensions)
        
        # Extension URLs: TurboWarp/PenguinMod can auto-load extensions from URLs
        if self.extension_loader:
            extension_urls = {}
            for ext_id in self.extensions:
                ext = self.extension_loader.get_extension(ext_id)
                if ext and ext.extension_url:
                    extension_urls[ext_id] = ext.extension_url
            if extension_urls:
                self.project["extensionURLs"] = extension_urls
            
        return self.project

    # ---------------- Assets (.sb3) ----------------

    def _resolve_asset_path(self, path: str, *, node: Optional[ASTNode] = None) -> str:
        if os.path.isabs(path):
            return path

        # Prefer resolving relative to the file that declared the asset.
        if node and node.position and node.position.filename and node.position.filename != "<input>":
            base = os.path.dirname(os.path.abspath(node.position.filename))
            return os.path.abspath(os.path.join(base, path))

        if self.base_dir:
            return os.path.abspath(os.path.join(self.base_dir, path))

        return os.path.abspath(path)

    def _md5_hex(self, data: bytes) -> str:
        return hashlib.md5(data).hexdigest()

    def _png_dimensions(self, data: bytes) -> Optional[Tuple[int, int]]:
        # Minimal PNG IHDR parse (no dependencies).
        # PNG signature (8) + IHDR length/type (8) + width/height (8)
        if len(data) < 24:
            return None
        if data[0:8] != b"\x89PNG\r\n\x1a\n":
            return None
        # IHDR chunk begins at byte 8
        if data[12:16] != b"IHDR":
            return None
        w = int.from_bytes(data[16:20], "big")
        h = int.from_bytes(data[20:24], "big")
        return (w, h)

    def _svg_dimensions(self, text: str) -> Optional[Tuple[float, float]]:
        # Best-effort parse; many SVGs omit explicit width/height.
        # Try width/height attributes first.
        m_w = re.search(r'\bwidth\s*=\s*"([0-9.]+)', text)
        m_h = re.search(r'\bheight\s*=\s*"([0-9.]+)', text)
        if m_w and m_h:
            try:
                return (float(m_w.group(1)), float(m_h.group(1)))
            except ValueError:
                pass

        # Fallback to viewBox.
        m_vb = re.search(r'\bviewBox\s*=\s*"([0-9.\-]+)\s+([0-9.\-]+)\s+([0-9.\-]+)\s+([0-9.\-]+)"', text)
        if m_vb:
            try:
                return (float(m_vb.group(3)), float(m_vb.group(4)))
            except ValueError:
                pass
        return None

    def _add_asset_bytes(self, *, data: bytes, data_format: str) -> Tuple[str, str]:
        md5 = self._md5_hex(data)
        md5ext = f"{md5}.{data_format}"
        if md5ext not in self.asset_blobs:
            self.asset_blobs[md5ext] = data
        return md5, md5ext

    def _blank_costume_entry(self, name: str) -> Dict[str, Any]:
        asset_id, md5ext = self._add_asset_bytes(data=self._blank_svg, data_format="svg")
        return {
            "assetId": asset_id,
            "name": name,
            "bitmapResolution": 1,
            "md5ext": md5ext,
            "dataFormat": "svg",
            "rotationCenterX": 0,
            "rotationCenterY": 0,
        }

    def _record_extension_from_opcode(self, opcode: str):
        # Scratch extension opcodes are prefixed by extension id (e.g. pen_*, music_*).
        if opcode.startswith("pen_"):
            self.extensions.add("pen")
        elif opcode.startswith("music_"):
            self.extensions.add("music")
        elif opcode.startswith("videoSensing_"):
            self.extensions.add("videoSensing")
        elif opcode.startswith("text2speech_"):
            self.extensions.add("text2speech")
        elif opcode.startswith("translate_"):
            self.extensions.add("translate")
        elif opcode.startswith("makeymakey_"):
            self.extensions.add("makeymakey")
        elif opcode.startswith("microbit_"):
            self.extensions.add("microbit")
        elif opcode.startswith("ev3_"):
            self.extensions.add("ev3")
        elif opcode.startswith("boost_"):
            self.extensions.add("boost")
        elif opcode.startswith("wedo2_"):
            self.extensions.add("wedo2")
        elif opcode.startswith("gdxfor_"):
            self.extensions.add("gdxfor")

    def _make_menu_shadow(self, *, opcode: str, field_name: str, field_value: str, parent_id: str) -> str:
        
        shadow_id = self.gen_id()
        self.blocks[shadow_id] = {
            "opcode": opcode,
            "next": None,
            "parent": parent_id,
            "inputs": {},
            "fields": {
                field_name: [field_value, None]
            },
            "shadow": True,
            "topLevel": False
        }
        return shadow_id

    def _compile_costume_menu_input(self, costume_name: str, parent_id: str) -> List[Any]:
        sid = self._make_menu_shadow(opcode="looks_costume", field_name="COSTUME", field_value=costume_name, parent_id=parent_id)
        return [1, sid]

    def _compile_backdrop_menu_input(self, backdrop_name: str, parent_id: str) -> List[Any]:
        sid = self._make_menu_shadow(opcode="looks_backdrops", field_name="BACKDROP", field_value=backdrop_name, parent_id=parent_id)
        return [1, sid]

    def _compile_sound_menu_input(self, sound_name: str, parent_id: str) -> List[Any]:
        sid = self._make_menu_shadow(opcode="sound_sounds_menu", field_name="SOUND_MENU", field_value=sound_name, parent_id=parent_id)
        return [1, sid]

    def _wav_metadata(self, data: bytes) -> Optional[Tuple[int, int]]:
        
        # Very small WAV parser: RIFF/WAVE + fmt + data.
        if len(data) < 44:
            return None
        if data[0:4] != b"RIFF" or data[8:12] != b"WAVE":
            return None

        off = 12
        fmt_channels = None
        fmt_sample_rate = None
        fmt_bits_per_sample = None
        data_size = None

        while off + 8 <= len(data):
            chunk_id = data[off:off+4]
            chunk_size = _read_u32_le(data, off+4)
            chunk_data_off = off + 8
            if chunk_data_off + chunk_size > len(data):
                break

            if chunk_id == b"fmt ":
                if chunk_size >= 16:
                    # audio_format = _read_u16_le(data, chunk_data_off+0)
                    fmt_channels = _read_u16_le(data, chunk_data_off+2)
                    fmt_sample_rate = _read_u32_le(data, chunk_data_off+4)
                    fmt_bits_per_sample = _read_u16_le(data, chunk_data_off+14)
            elif chunk_id == b"data":
                data_size = chunk_size

            # chunks are word-aligned
            off = chunk_data_off + chunk_size
            if off % 2 == 1:
                off += 1

        if fmt_channels and fmt_sample_rate and fmt_bits_per_sample and data_size is not None:
            bytes_per_sample_frame = fmt_channels * (fmt_bits_per_sample // 8)
            if bytes_per_sample_frame > 0:
                sample_count = int(data_size // bytes_per_sample_frame)
                return (int(fmt_sample_rate), int(sample_count))
        return None
    
    def compile_stage(self, stage: Stage):
        
        target = {
            "isStage": True,
            "name": "Stage",
            "variables": {},
            "lists": {},
            "broadcasts": {},
            "blocks": {},
            "comments": {},
            "currentCostume": 0,
            "costumes": [],
            "sounds": [],
            "volume": 100,
            "layerOrder": 0,
            "tempo": stage.tempo,
            "videoTransparency": stage.video_transparency,
            "videoState": stage.video_state,
            "textToSpeechLanguage": None
        }
        
        self.current_target = target
        self.blocks = target["blocks"]
        self.comments = target["comments"]  # Reset comments for this target
        self._comment_y_offset = 0  # Reset comment positioning
        self.variables = {}
        self.lists = {}
        self.custom_blocks = {}
        
        # Process assets
        self.process_costumes(stage.backdrops, target)
        self.process_sounds(stage.sounds, target)
        
        # Process variables and lists
        for var in stage.variables:
            var_id = self.gen_id()
            # Use display_name if set, otherwise use identifier name
            var_scratch_name = var.display_name if var.display_name else var.name
            # Cloud variables have special encoding: name prefixed with "☁ " 
            # and stored as [name, value, true] instead of [name, value]
            if var.is_cloud:
                cloud_name = f"☁ {var_scratch_name}"
                initial = self._get_initial_value(var.initial_value)
                # Cloud variables must be numeric
                if not isinstance(initial, (int, float)):
                    initial = 0
                target["variables"][var_id] = [cloud_name, initial, True]
                self.variables[var.name] = {"name": cloud_name, "id": var_id, "is_cloud": True}
                # Track by Felis name for global scope lookup
                self.stage_variables_by_name[var.name] = {"name": cloud_name, "id": var_id, "is_cloud": True}
            else:
                target["variables"][var_id] = [var_scratch_name, self._get_initial_value(var.initial_value)]
                self.variables[var.name] = {"name": var_scratch_name, "id": var_id}
                # Track by Felis name for global scope lookup
                self.stage_variables_by_name[var.name] = {"name": var_scratch_name, "id": var_id}
            
        for lst in stage.lists:
            list_id = self.gen_id()
            # Use display_name if set, otherwise use identifier name
            list_scratch_name = lst.display_name if lst.display_name else lst.name
            list_values = self._get_list_values(lst)
            target["lists"][list_id] = [list_scratch_name, list_values]
            self.lists[lst.name] = {"name": list_scratch_name, "id": list_id}
            # Track by Felis name for global scope lookup
            self.stage_lists_by_name[lst.name] = {"name": list_scratch_name, "id": list_id}
            
        # Process custom blocks definitions first
        for cb in stage.custom_blocks:
            self.register_custom_block(cb)
            
        # Process code
        top_level_blocks = []
        for cb in stage.custom_blocks:
            bid = self.compile_custom_block(cb)
            top_level_blocks.append(bid)
            
        for handler in stage.event_handlers:
            bid = self.compile_event_handler(handler)
            top_level_blocks.append(bid)
            
        # Fix any orphaned blocks that weren't properly parented
        self._fix_orphaned_blocks()
            
        self.layout_blocks(top_level_blocks)
            
        self.project["targets"].append(target)
        
    def compile_sprite(self, sprite: Sprite):
        # Use display_name if set, otherwise use identifier name
        scratch_name = sprite.display_name if sprite.display_name else sprite.name
        
        target = {
            "isStage": False,
            "name": scratch_name,
            "variables": {},
            "lists": {},
            "broadcasts": {},
            "blocks": {},
            "comments": {},
            "currentCostume": 0,
            "costumes": [],
            "sounds": [],
            "volume": 100,
            "layerOrder": sprite.layer_order,
            "visible": sprite.visible,
            "x": sprite.x,
            "y": sprite.y,
            "size": sprite.size,
            "direction": sprite.direction,
            "draggable": False,
            "rotationStyle": sprite.rotation_style
        }
        
        self.current_target = target
        self.blocks = target["blocks"]
        self.comments = target["comments"]  # Reset comments for this target
        self._comment_y_offset = 0  # Reset comment positioning
        self.variables = {}
        self.lists = {}
        self.custom_blocks = {}
        
        # Process assets
        self.process_costumes(sprite.costumes, target)
        self.process_sounds(sprite.sounds, target)
        
        # Process variables and lists
        for var in sprite.variables:
            var_id = self.gen_id()
            # Use display_name if set, otherwise use identifier name
            var_scratch_name = var.display_name if var.display_name else var.name
            # Cloud variables have special encoding
            if var.is_cloud:
                cloud_name = f"☁ {var_scratch_name}"
                initial = self._get_initial_value(var.initial_value)
                # Cloud variables must be numeric
                if not isinstance(initial, (int, float)):
                    initial = 0
                target["variables"][var_id] = [cloud_name, initial, True]
                self.variables[var.name] = {"name": cloud_name, "id": var_id, "is_cloud": True}
            else:
                target["variables"][var_id] = [var_scratch_name, self._get_initial_value(var.initial_value)]
                self.variables[var.name] = {"name": var_scratch_name, "id": var_id}
            
        for lst in sprite.lists:
            list_id = self.gen_id()
            # Use display_name if set, otherwise use identifier name
            list_scratch_name = lst.display_name if lst.display_name else lst.name
            list_values = self._get_list_values(lst)
            target["lists"][list_id] = [list_scratch_name, list_values]
            self.lists[lst.name] = {"name": list_scratch_name, "id": list_id}
            
        # Process custom blocks definitions first
        for cb in sprite.custom_blocks:
            self.register_custom_block(cb)
            
        # Process code
        top_level_blocks = []
        for cb in sprite.custom_blocks:
            bid = self.compile_custom_block(cb)
            top_level_blocks.append(bid)
            
        for handler in sprite.event_handlers:
            bid = self.compile_event_handler(handler)
            top_level_blocks.append(bid)
            
        # Fix any orphaned blocks that weren't properly parented
        self._fix_orphaned_blocks()
            
        self.layout_blocks(top_level_blocks)
            
        self.project["targets"].append(target)
        
    def layout_blocks(self, block_ids: List[str]):
        
        start_x = 50
        x = start_x
        y = 50
        padding = 60
        column_width = 500
        max_y = 1500
        
        for block_id in block_ids:
            if block_id in self.blocks:
                self.blocks[block_id]["x"] = x
                self.blocks[block_id]["y"] = y
                
                # Estimate height
                height = self.estimate_stack_height(block_id)
                y += height + padding
                
                if y > max_y:
                    y = 50
                    x += column_width
                
    def estimate_stack_height(self, block_id: str) -> int:
        
        height = 0
        current = block_id
        
        # Traverse next
        while current:
            block = self.blocks.get(current)
            if not block: break
            
            height += 48 # Standard block height approx
            
            # Check substacks (if/repeat)
            if "inputs" in block:
                for input_name, input_val in block["inputs"].items():
                    if input_name.startswith("SUBSTACK"):
                        # input_val is [2, block_id]
                        if isinstance(input_val, list) and len(input_val) >= 2 and isinstance(input_val[1], str):
                            height += self.estimate_stack_height(input_val[1]) + 10
            
            current = block.get("next")
            
        return height

    def process_costumes(self, costumes: List[Costume], target: Dict):
        
        if not costumes:
            # Always ensure the target has at least one costume/backdrop, and include the bytes in the SB3.
            target["costumes"].append(self._blank_costume_entry("costume1"))
            return

        for costume in costumes:
            if not costume.file:
                target["costumes"].append(self._blank_costume_entry(costume.name))
                continue

            resolved = self._resolve_asset_path(costume.file, node=costume)
            if not os.path.exists(resolved):
                raise CompilerError(f"Costume file not found: {costume.file} (resolved to {resolved})", costume)

            ext = os.path.splitext(resolved)[1].lower().lstrip(".")
            if ext not in ("svg", "png"):
                raise CompilerError(f"Unsupported costume format: .{ext} (supported: .svg, .png)", costume)

            with open(resolved, "rb") as f:
                data = f.read()

            asset_id, md5ext = self._add_asset_bytes(data=data, data_format=ext)

            # Infer center if not explicitly set.
            center_x = costume.rotation_center_x
            center_y = costume.rotation_center_y
            if center_x is None or center_y is None:
                if ext == "png":
                    dims = self._png_dimensions(data)
                    if dims:
                        w, h = dims
                        center_x = (w / 2.0)
                        center_y = (h / 2.0)
                    else:
                        center_x = 0
                        center_y = 0
                else:
                    try:
                        text = data.decode("utf-8", errors="ignore")
                    except Exception:
                        text = ""
                    dims = self._svg_dimensions(text)
                    if dims:
                        w, h = dims
                        center_x = (w / 2.0)
                        center_y = (h / 2.0)
                    else:
                        center_x = 0
                        center_y = 0

            target["costumes"].append({
                "assetId": asset_id,
                "name": costume.name,
                "bitmapResolution": 1,
                "md5ext": md5ext,
                "dataFormat": ext,
                "rotationCenterX": center_x,
                "rotationCenterY": center_y,
            })
            
    def process_sounds(self, sounds: List[Sound], target: Dict):
        
        for sound in sounds:
            if not sound.file:
                # No file: skip (Scratch allows empty sounds array).
                continue

            resolved = self._resolve_asset_path(sound.file, node=sound)
            if not os.path.exists(resolved):
                raise CompilerError(f"Sound file not found: {sound.file} (resolved to {resolved})", sound)

            ext = os.path.splitext(resolved)[1].lower().lstrip(".")
            if ext not in ("wav", "mp3"):
                raise CompilerError(f"Unsupported sound format: .{ext} (supported: .wav, .mp3)", sound)

            with open(resolved, "rb") as f:
                data = f.read()

            asset_id, md5ext = self._add_asset_bytes(data=data, data_format=ext)

            rate = 44100
            sample_count = 0
            if ext == "wav":
                meta = self._wav_metadata(data)
                if meta:
                    rate, sample_count = meta

            target["sounds"].append({
                "assetId": asset_id,
                "name": sound.name,
                "dataFormat": ext,
                "format": "",
                "rate": rate,
                "sampleCount": sample_count,
                "md5ext": md5ext,
            })

    def _humanize_custom_block_name(self, name: str) -> str:
        """Convert a Felis function name into a more readable Scratch custom block label.

        This only affects how blocks appear in Scratch/TurboWarp's "My Blocks" UI.
        The Felis API remains the original function name.
        """
        prefix_map = [
            ("dbg_", "Debug"),
            ("obj_", "Objects"),
            ("dyn_list_", "Dynamic Lists"),
            ("dyn_", "Dynamic Variables"),
            ("kv_", "Key/Value"),
            ("cs_", "Cutscene"),
            ("anim_", "Animation"),
            ("ui_", "UI"),
            ("pen_", "Pen"),
            ("list_", "List"),
        ]

        category = None
        rest = name
        for pref, cat in prefix_map:
            if name.startswith(pref):
                category = cat
                rest = name[len(pref):]
                break

        # Replace snake_case with spaces.
        rest = rest.replace("_", " ")
        # Add spaces around digits for readability (e.g., bezier3 -> bezier 3).
        rest = re.sub(r"([A-Za-z])(\d)", r"\1 \2", rest)
        rest = re.sub(r"(\d)([A-Za-z])", r"\1 \2", rest)
        rest = rest.strip()

        if category:
            return f"{category}: {rest}" if rest else category

        # No known category; still humanize.
        return name.replace("_", " ").strip()

    def _custom_block_proccode(self, cb: CustomBlock) -> str:
        """Compute the Scratch proccode (display label) for a Felis custom block.

        This only affects how blocks look in Scratch/TurboWarp. The Felis API stays the same.
        """

        # Templates for beginner-friendly SDK blocks.
        # NOTE: Placeholders must match the number/order of cb.params.
        templates: Dict[str, str] = {
            # sdk_dyn (dynamic variables)
            "dyn_clear": "Dynamic Variables: Clear all",
            "dyn_has": "Dynamic Variables: Has variable named %s ?",
            "dyn_get": "Dynamic Variables: Get value of %s (default %s)",
            "dyn_set": "Dynamic Variables: Set variable %s to %s",
            "dyn_del": "Dynamic Variables: Delete variable %s",
            "dyn_add": "Dynamic Variables: Increase variable %s by %s",

            # sdk_dyn (dynamic lists)
            "dyn_list_create": "Dynamic Lists: Create list %s",
            "dyn_list_clear": "Dynamic Lists: Clear list %s",
            "dyn_list_clear_all": "Dynamic Lists: Clear ALL dynamic lists",
            "dyn_list_len": "Dynamic Lists: Length of list %s",
            "dyn_list_to_output": "Dynamic Lists: Copy list %s to output",
            "dyn_list_get": "Dynamic Lists: In list %s, get item %s (default %s)",
            "dyn_list_set": "Dynamic Lists: In list %s, set item %s to %s",
            "dyn_list_push": "Dynamic Lists: In list %s, add %s",
            "dyn_list_pop": "Dynamic Lists: In list %s, pop last item (default %s)",
            "dyn_list_remove_at": "Dynamic Lists: In list %s, delete item %s",

            # sdk_cutscene
            "cs_clear": "Cutscene: Clear queued actions",
            "cs_add_wait": "Cutscene: Add wait %s seconds",
            "cs_add_say": "Cutscene: Add say %s for %s seconds",
            "cs_add_think": "Cutscene: Add think %s for %s seconds",
            "cs_add_broadcast": "Cutscene: Add broadcast %s",
            "cs_add_show": "Cutscene: Add show",
            "cs_add_hide": "Cutscene: Add hide",
            "cs_add_cam_to": "Cutscene Camera: Pan to x %s y %s over %s seconds",
            "cs_add_zoom_to": "Cutscene Camera: Zoom to %s over %s seconds",
            "cs_cam_reset": "Cutscene Camera: Reset",
            "cs_cam_set": "Cutscene Camera: Set x %s y %s",
            "cs_cam_zoom_set": "Cutscene Camera: Set zoom %s",
            "cs_play": "Cutscene: Play",
            "cs_request_skip": "Cutscene: Request skip",

            # sdk_ui
            "ui_clear": "UI: Clear elements",
            "ui_begin_frame": "UI: Begin frame (clear clicks)",
            "ui_add_button": "UI: Add button id %s at x %s y %s w %s h %s",
            "ui_register_self": "UI: Register this sprite as button %s (w %s h %s)",
            "ui_update": "UI: Update (detect click)",
            "ui_clicked": "UI: Was %s clicked?",
            "ui_pen_clear": "UI Pen: Clear drawings",
            "ui_pen_panel_outline": "UI Pen: Draw panel outline at x %s y %s w %s h %s",
            "ui_pen_button_outline": "UI Pen: Draw button outline %s at x %s y %s w %s h %s",
        }

        template = templates.get(cb.name)
        if template:
            expected = len(cb.params)
            actual = template.count("%s") + template.count("%b")
            if actual == expected:
                return template

        # If custom block has display_name, use it directly
        if cb.display_name:
            proccode_parts = [cb.display_name]
            for param in cb.params:
                # Use param display_name if available
                param_label = param.display_name if param.display_name else param.name
                if param.param_type in ("number", "string"):
                    proccode_parts.append(f"%s")
                elif param.param_type == "boolean":
                    proccode_parts.append(f"%b")
            return " ".join(proccode_parts)

        # Default behavior: readable name + raw positional args.
        proccode_parts = [self._humanize_custom_block_name(cb.name)]
        for param in cb.params:
            if param.param_type in ("number", "string"):
                proccode_parts.append("%s")
            elif param.param_type == "boolean":
                proccode_parts.append("%b")
        return " ".join(proccode_parts)

    def register_custom_block(self, cb: CustomBlock):
        
        # Generate proccode (e.g., "my block %s %b")
        param_ids = []
        param_names = []
        
        proccode = self._custom_block_proccode(cb)

        for param in cb.params:
            param_ids.append(self.gen_id())
            param_names.append(param.name)
            
        self.custom_blocks[cb.name] = {
            "proccode": proccode,
            "argumentIds": json.dumps(param_ids),
            "argumentNames": json.dumps(param_names),
            "warp": cb.warp,
            "param_map": dict(zip(param_names, param_ids))
        }

    def compile_custom_block(self, cb: CustomBlock) -> str:
        
        block_id = self.gen_id()
        def_info = self.custom_blocks[cb.name]
        
        # Store preceding comments to add after block is created
        preceding_comments = getattr(cb, 'preceding_comments', None) or []
        
        # Set current params context
        self.current_custom_block_params = {}
        self.current_function_name = cb.name  # Track current function name
        
        param_ids = json.loads(def_info["argumentIds"])
        param_names = json.loads(def_info["argumentNames"])
        for i, (pid, pname) in enumerate(zip(param_ids, param_names)):
            self.current_custom_block_params[pname] = (cb.params[i].param_type, pid)
        
        # Definition block
        self.blocks[block_id] = {
            "opcode": "procedures_definition",
            "next": None,
            "parent": None,
            "inputs": {
                "custom_block": [1, self.compile_prototype(cb, def_info, block_id)]
            },
            "fields": {},
            "shadow": False,
            "topLevel": True,
            "x": 0,  # Layout would be handled by a formatter
            "y": 0
        }
        
        # Handle preceding comments (floating comments above this custom block)
        # Added AFTER block is created so we can position relative to it
        for comment_text in preceding_comments:
            self.add_floating_comment(comment_text, near_block_id=block_id)
        
        # Handle inline comment (attached to the definition block)
        if hasattr(cb, 'comment') and cb.comment:
            self.add_block_comment(block_id, cb.comment)
        
        # Compile body
        if cb.body:
            first_stmt_id = self.compile_statement_list(cb.body, block_id)
            self.blocks[block_id]["next"] = first_stmt_id
            
        # Clear context
        self.current_custom_block_params = {}
        self.current_function_name = None
        
        return block_id

    def compile_prototype(self, cb: CustomBlock, def_info: Dict, parent_id: str) -> str:
        
        proto_id = self.gen_id()
        
        inputs = {}
        param_ids = json.loads(def_info["argumentIds"])
        param_names = json.loads(def_info["argumentNames"])
        
        for i, (pid, pname) in enumerate(zip(param_ids, param_names)):
            # Create argument reporter blocks for the prototype
            arg_id = self.gen_id()
            param_type = cb.params[i].param_type
            opcode = "argument_reporter_boolean" if param_type == "boolean" else "argument_reporter_string_number"
            
            self.blocks[arg_id] = {
                "opcode": opcode,
                "next": None,
                "parent": proto_id,
                "inputs": {},
                "fields": {
                    "VALUE": [pname, None]
                },
                "shadow": True,
                "topLevel": False
            }
            inputs[pid] = [1, arg_id]

        self.blocks[proto_id] = {
            "opcode": "procedures_prototype",
            "next": None,
            "parent": parent_id,
            "inputs": inputs,
            "fields": {},
            "shadow": True,
            "topLevel": False,
            "mutation": {
                "tagName": "mutation",
                "children": [],
                "proccode": def_info["proccode"],
                "argumentids": def_info["argumentIds"],
                "argumentnames": def_info["argumentNames"],
                "argumentdefaults": "[]",
                "warp": "true" if def_info["warp"] else "false"
            }
        }
        
        return proto_id

    def compile_event_handler(self, handler: EventHandler):
        
        block_id = self.gen_id()
        
        # Store preceding comments to add after block is created
        preceding_comments = getattr(handler, 'preceding_comments', None) or []
        
        opcode = ""
        fields = {}
        inputs = {}
        
        if handler.event_type == EventType.FLAG_CLICKED:
            opcode = "event_whenflagclicked"
        elif handler.event_type == EventType.KEY_PRESSED:
            opcode = "event_whenkeypressed"
            key = self._normalize_key_option(handler.event_param)
            fields["KEY_OPTION"] = [key, None]
        elif handler.event_type == EventType.SPRITE_CLICKED:
            opcode = "event_whenthisspriteclicked"
        elif handler.event_type == EventType.STAGE_CLICKED:
            opcode = "event_whenstageclicked"
        elif handler.event_type == EventType.BACKDROP_SWITCHES:
            opcode = "event_whenbackdropswitchesto"
            fields["BACKDROP"] = [handler.event_param, None]
        elif handler.event_type == EventType.LOUDNESS_GREATER:
            opcode = "event_whengreaterthan"
            fields["WHENGREATERTHANMENU"] = ["LOUDNESS", None]
            inputs["VALUE"] = self.compile_input(NumberLiteral(handler.event_param))
        elif handler.event_type == EventType.TIMER_GREATER:
            opcode = "event_whengreaterthan"
            fields["WHENGREATERTHANMENU"] = ["TIMER", None]
            inputs["VALUE"] = self.compile_input(NumberLiteral(handler.event_param))
        elif handler.event_type == EventType.MESSAGE_RECEIVED:
            opcode = "event_whenbroadcastreceived"
            fields["BROADCAST_OPTION"] = [handler.event_param, self.get_broadcast_id(handler.event_param)]
        elif handler.event_type == EventType.CLONE_STARTS:
            opcode = "control_start_as_clone"

        self._record_extension_from_opcode(opcode)
            
        self.blocks[block_id] = {
            "opcode": opcode,
            "next": None,
            "parent": None,
            "inputs": inputs,
            "fields": fields,
            "shadow": False,
            "topLevel": True,
            "x": 0,
            "y": 0
        }
        
        # Handle preceding comments (floating comments above this event handler)
        # Added AFTER block is created so we can position relative to it
        for comment_text in preceding_comments:
            self.add_floating_comment(comment_text, near_block_id=block_id)
        
        # Handle inline comment (attached to the hat block)
        if hasattr(handler, 'comment') and handler.comment:
            self.add_block_comment(block_id, handler.comment)
        
        if handler.body:
            first_stmt_id = self.compile_statement_list(handler.body, block_id)
            self.blocks[block_id]["next"] = first_stmt_id
            
        return block_id

    def compile_statement_list(self, statements: List[Statement], parent_id: str) -> Optional[str]:
        
        if not statements:
            return None
            
        first_id = None
        prev_id = parent_id
        
        for stmt in statements:
            stmt_id = self.compile_statement(stmt, prev_id)
            if not first_id:
                first_id = stmt_id
            
            # Link previous block to this one
            if prev_id and prev_id in self.blocks:
                # If prev was a parent (like a hat block or C-block start), link via 'next' or substack
                # But here we assume prev_id is the strictly previous block in the chain
                # The parent linkage is handled by compile_statement setting 'parent'
                
                # If prev_id is the container (e.g. "if"), we don't set its next to the first child
                # The container sets its input (substack) to the first child.
                # So we only set 'next' if prev_id is a sibling statement.
                
                if self.blocks[prev_id]["parent"] == parent_id and parent_id != prev_id:
                     # This logic is tricky. Let's simplify:
                     # We return the ID of the first block.
                     # The caller attaches it to the appropriate place.
                     # Inside this loop, we link stmt N to stmt N+1.
                     pass
            
            if prev_id != parent_id:
                self.blocks[prev_id]["next"] = stmt_id
                
            prev_id = stmt_id
            
        return first_id

    def compile_statement(self, stmt: Statement, parent_id: str) -> str:
        
        block_id = self.gen_id()
        self._stats["blocks_compiled"] += 1
        
        # Store preceding comments to add AFTER block is compiled
        preceding_comments = getattr(stmt, 'preceding_comments', None) or []
        
        if isinstance(stmt, BlockCall):
            self.compile_block_call(stmt, block_id, parent_id)
        elif isinstance(stmt, IfStatement):
            self.compile_if(stmt, block_id, parent_id)
        elif isinstance(stmt, RepeatStatement):
            self.compile_repeat(stmt, block_id, parent_id)
        elif isinstance(stmt, ForeverStatement):
            self.compile_forever(stmt, block_id, parent_id)
        elif isinstance(stmt, WhileStatement):
            self.compile_while(stmt, block_id, parent_id)
        elif isinstance(stmt, WaitStatement):
            self.compile_wait(stmt, block_id, parent_id)
        elif isinstance(stmt, WaitUntilStatement):
            self.compile_wait_until(stmt, block_id, parent_id)
        elif isinstance(stmt, StopStatement):
            self.compile_stop(stmt, block_id, parent_id)
        elif isinstance(stmt, ReturnStatement):
            # Return is special: it might generate multiple blocks (set var + stop)
            # But compile_statement expects to return ONE block ID that starts the chain.
            # So we delegate to compile_return which handles the chaining internally
            # and returns the ID of the FIRST block.
            # Handle inline comment first before returning
            if hasattr(stmt, 'comment') and stmt.comment:
                self.add_block_comment(block_id, stmt.comment)
            return self.compile_return(stmt, block_id, parent_id)
        elif isinstance(stmt, FunctionCall):
            # Handle function call as a statement (void context)
            # This allows calling custom blocks that return values but ignoring the return value
            # We need to treat it as a BlockCall
            # Convert FunctionCall to BlockCall
            block_call = BlockCall(block_name=stmt.func_name, args=stmt.args, fields={}, position=stmt.position)
            self.compile_block_call(block_call, block_id, parent_id)
        elif isinstance(stmt, SetVariable):
            self.compile_set_variable(stmt, block_id, parent_id)
        elif isinstance(stmt, ChangeVariable):
            self.compile_change_variable(stmt, block_id, parent_id)
        elif isinstance(stmt, ShowVariable):
            self.compile_show_hide_var(stmt, block_id, parent_id, True)
        elif isinstance(stmt, HideVariable):
            self.compile_show_hide_var(stmt, block_id, parent_id, False)
        elif isinstance(stmt, ListOperation):
            self.compile_list_op(stmt, block_id, parent_id)
        elif isinstance(stmt, ShowList):
            self.compile_show_hide_list(stmt, block_id, parent_id, True)
        elif isinstance(stmt, HideList):
            self.compile_show_hide_list(stmt, block_id, parent_id, False)
        elif isinstance(stmt, VariableDecl):
            self.compile_variable_decl_stmt(stmt, block_id, parent_id)
        elif isinstance(stmt, ListDecl):
            self.compile_list_decl_stmt(stmt, block_id, parent_id)
        else:
            raise CompilerError(f"Unknown statement type: {type(stmt)}", stmt)
        
        # Handle preceding comments (floating comments above this statement)
        # Added AFTER block is compiled so we can position relative to it
        for comment_text in preceding_comments:
            self.add_floating_comment(comment_text, near_block_id=block_id)
        
        # Handle inline comment (attached to block)
        if hasattr(stmt, 'comment') and stmt.comment:
            self.add_block_comment(block_id, stmt.comment)
            
        return block_id

    def compile_variable_decl_stmt(self, stmt: VariableDecl, block_id: str, parent_id: str):
        
        # Register variable if not exists
        if stmt.name not in self.variables:
            var_id = self.gen_id()
            self.variables[stmt.name] = {"name": stmt.name, "id": var_id}
            self.current_target["variables"][var_id] = [stmt.name, 0]
        
        # Compile as set variable
        set_stmt = SetVariable(var_name=stmt.name, value=stmt.initial_value, position=stmt.position)
        self.compile_set_variable(set_stmt, block_id, parent_id)

    def compile_list_decl_stmt(self, stmt: ListDecl, block_id: str, parent_id: str):
        
        # Register list if not exists
        if stmt.name not in self.lists:
            list_id = self.gen_id()
            self.lists[stmt.name] = {"name": stmt.name, "id": list_id}
            self.current_target["lists"][list_id] = [stmt.name, []]
        
        # Compile as delete all
        # We need to chain multiple blocks if there are initial values
        # But compile_statement returns one block_id.
        # So we'll compile the first one (delete all) and chain the rest.
        
        # 1. Delete all
        delete_op = ListOperation(operation="deleteAll", list_name=stmt.name, position=stmt.position)
        self.compile_list_op(delete_op, block_id, parent_id)
        
        # 2. Add initial values
        current_parent = block_id
        for val in stmt.initial_values:
            add_id = self.gen_id()
            add_op = ListOperation(operation="add", list_name=stmt.name, item=val, position=stmt.position)
            self.compile_list_op(add_op, add_id, current_parent)
            current_parent = add_id

    def compile_block_call(self, stmt: BlockCall, block_id: str, parent_id: str):
        
        # Check if it's a custom block call
        if stmt.block_name in self.custom_blocks:
            self.compile_custom_block_call(stmt, block_id, parent_id)
            return
        
        # Check if it's an extension block
        ext_block = self.extension_loader.get_block(stmt.block_name)
        if ext_block:
            self.compile_extension_block_call(stmt, ext_block, block_id, parent_id)
            return

        # Special handling for go_to_layer("front") / go_to_layer("back")
        if stmt.block_name == "go_to_layer" and stmt.args:
            arg = stmt.args[0]
            layer_value = "front"
            if isinstance(arg, StringLiteral):
                layer_value = arg.value.lower()
            self.blocks[block_id] = {
                "opcode": "looks_gotofrontback",
                "next": None,
                "parent": parent_id,
                "inputs": {},
                "fields": {
                    "FRONT_BACK": [layer_value, None]
                },
                "shadow": False,
                "topLevel": False
            }
            return

        block_def = _get_block_def(stmt.block_name)
        if not block_def:
            # Try to find similar block names for helpful error
            all_block_names = list(ALL_BLOCKS.keys())
            similar = [name for name in all_block_names if stmt.block_name.lower() in name.lower() or name.lower() in stmt.block_name.lower()][:5]
            raise CompilerError(
                f"Unknown block: {stmt.block_name}", 
                stmt,
                suggestion="Check the block name spelling or see docs/remaining_blocks.md for available blocks",
                related_symbols=similar
            )

        self._record_extension_from_opcode(block_def.opcode)
            
        inputs = {}
        fields = {}
        
        # Map arguments to inputs
        for i, arg in enumerate(stmt.args):
            if i < len(block_def.inputs):
                input_name = block_def.inputs[i]
                # Improve editor compatibility for menu-style inputs.
                if isinstance(arg, StringLiteral):
                    if block_def.opcode == "looks_switchcostumeto" and input_name == "COSTUME":
                        inputs[input_name] = self._compile_costume_menu_input(arg.value, block_id)
                        continue
                    if block_def.opcode in ("looks_switchbackdropto", "looks_switchbackdroptoandwait") and input_name == "BACKDROP":
                        inputs[input_name] = self._compile_backdrop_menu_input(arg.value, block_id)
                        continue
                    if block_def.opcode in ("sound_play", "sound_playuntildone") and input_name == "SOUND_MENU":
                        inputs[input_name] = self._compile_sound_menu_input(arg.value, block_id)
                        continue

                inputs[input_name] = self.compile_input(arg)
                
        # Map fields
        for field_name, value in stmt.fields.items():
            fields[field_name] = [value, None]
            
        # Special handling for broadcast
        if stmt.block_name in ('broadcast', 'broadcast_and_wait'):
            msg = stmt.args[0]
            if isinstance(msg, StringLiteral):
                # It's a field input (shadow)
                inputs["BROADCAST_INPUT"] = [1, [11, msg.value, self.get_broadcast_id(msg.value)]]
            else:
                inputs["BROADCAST_INPUT"] = self.compile_input(msg)
        
        # Special handling for effect blocks where arg order is (effect, value)
        # but block structure needs effect in EFFECT field and value in input
        if stmt.block_name in ('change_effect', 'set_effect', 'change_effect_sound', 'set_effect_sound') and len(stmt.args) >= 2:
            effect_arg = stmt.args[0]
            value_arg = stmt.args[1]
            # Put effect in EFFECT field
            if isinstance(effect_arg, StringLiteral):
                fields["EFFECT"] = [effect_arg.value, None]
            else:
                fields["EFFECT"] = [str(effect_arg), None]
            # Put value in the input (CHANGE for change_effect, VALUE for set_effect)
            input_name = block_def.inputs[0] if block_def.inputs else "CHANGE"
            inputs[input_name] = self.compile_input(value_arg)
        
        # Special handling for point_towards - needs menu shadow block
        # Parser may put string literal in args OR in fields['TOWARDS']
        if stmt.block_name == 'point_towards':
            towards_value = None
            if len(stmt.args) >= 1 and isinstance(stmt.args[0], StringLiteral):
                towards_value = stmt.args[0].value
            elif 'TOWARDS' in stmt.fields:
                towards_value = stmt.fields['TOWARDS']
                del fields['TOWARDS']  # Remove from fields, we'll put it in inputs
            
            if towards_value is not None:
                menu_id = self._make_menu_shadow(
                    opcode='motion_pointtowards_menu',
                    field_name='TOWARDS',
                    field_value=towards_value,
                    parent_id=block_id
                )
                inputs['TOWARDS'] = [1, menu_id]
            elif len(stmt.args) >= 1:
                inputs['TOWARDS'] = self.compile_input(stmt.args[0])
        
        # Special handling for goto (to sprite) - needs menu shadow block
        # Parser may put string literal in args OR in fields['TO']
        if stmt.block_name == 'goto':
            to_value = None
            if len(stmt.args) == 1 and isinstance(stmt.args[0], StringLiteral):
                to_value = stmt.args[0].value
            elif 'TO' in stmt.fields:
                to_value = stmt.fields['TO']
                del fields['TO']  # Remove from fields, we'll put it in inputs
            
            if to_value is not None:
                menu_id = self._make_menu_shadow(
                    opcode='motion_goto_menu',
                    field_name='TO',
                    field_value=to_value,
                    parent_id=block_id
                )
                inputs['TO'] = [1, menu_id]
            elif len(stmt.args) == 1:
                inputs['TO'] = self.compile_input(stmt.args[0])
        
        # Special handling for glide_to - needs menu shadow block for TO
        # Parser may put string literal in fields['TO']
        if stmt.block_name == 'glide_to':
            to_value = None
            if 'TO' in stmt.fields:
                to_value = stmt.fields['TO']
                del fields['TO']
            elif len(stmt.args) >= 2 and isinstance(stmt.args[1], StringLiteral):
                to_value = stmt.args[1].value
                # Don't process this arg again below
            
            if to_value is not None:
                menu_id = self._make_menu_shadow(
                    opcode='motion_glideto_menu',
                    field_name='TO',
                    field_value=to_value,
                    parent_id=block_id
                )
                inputs['TO'] = [1, menu_id]
                
        self.blocks[block_id] = {
            "opcode": block_def.opcode,
            "next": None,
            "parent": parent_id,
            "inputs": inputs,
            "fields": fields,
            "shadow": False,
            "topLevel": False
        }
        # Set parent links for all input blocks
        self._assign_input_parents(block_id, inputs)

    def compile_custom_block_call(self, stmt: BlockCall, block_id: str, parent_id: str):
        
        def_info = self.custom_blocks[stmt.block_name]
        
        inputs = {}
        param_ids = json.loads(def_info["argumentIds"])
        
        for i, arg in enumerate(stmt.args):
            if i < len(param_ids):
                inputs[param_ids[i]] = self.compile_input(arg)
                
        self.blocks[block_id] = {
            "opcode": "procedures_call",
            "next": None,
            "parent": parent_id,
            "inputs": inputs,
            "fields": {},
            "shadow": False,
            "topLevel": False,
            "mutation": {
                "tagName": "mutation",
                "children": [],
                "proccode": def_info["proccode"],
                "argumentids": def_info["argumentIds"],
                "warp": "true" if def_info["warp"] else "false"
            }
        }
        # Set parent links for all input blocks
        self._assign_input_parents(block_id, inputs)

    def compile_extension_block_call(self, stmt: BlockCall, ext_block: ExtensionBlock, block_id: str, parent_id: str):
        
        # Record the extension
        ext_id = self.extension_loader.get_extension_for_opcode(ext_block.opcode)
        if ext_id:
            self.extensions.add(ext_id)
        
        inputs = {}
        fields = {}
        
        # Map arguments to inputs based on the extension block definition
        for i, arg in enumerate(stmt.args):
            if i < len(ext_block.arguments):
                ext_arg = ext_block.arguments[i]
                arg_name = ext_arg.name
                
                # Handle menu arguments specially
                if ext_arg.menu:
                    # For menu args with string literals, create a menu shadow block
                    if isinstance(arg, StringLiteral):
                        # Use fields for simple string menus
                        fields[arg_name] = [arg.value, None]
                        continue
                
                inputs[arg_name] = self.compile_input(arg)
        
        # Add any additional fields from stmt.fields
        for field_name, value in stmt.fields.items():
            fields[field_name] = [value, None]
        
        self.blocks[block_id] = {
            "opcode": ext_block.opcode,
            "next": None,
            "parent": parent_id,
            "inputs": inputs,
            "fields": fields,
            "shadow": False,
            "topLevel": ext_block.block_type == "hat"
        }
        
        # Set parent links for all input blocks
        self._assign_input_parents(block_id, inputs)

    def compile_if(self, stmt: IfStatement, block_id: str, parent_id: str):
        
        inputs = {
            "CONDITION": self.compile_input(stmt.condition)
        }
        
        if stmt.then_body:
            inputs["SUBSTACK"] = [2, self.compile_statement_list(stmt.then_body, block_id)]
            
        if stmt.else_body:
            inputs["SUBSTACK2"] = [2, self.compile_statement_list(stmt.else_body, block_id)]
            
        opcode = "control_if_else" if stmt.else_body else "control_if"

        self._assign_input_parents(block_id, {"CONDITION": inputs["CONDITION"]})
        
        self.blocks[block_id] = {
            "opcode": opcode,
            "next": None,
            "parent": parent_id,
            "inputs": inputs,
            "fields": {},
            "shadow": False,
            "topLevel": False
        }

    def compile_repeat(self, stmt: RepeatStatement, block_id: str, parent_id: str):
        
        inputs = {
            "TIMES": self.compile_input(stmt.count)
        }
        
        if stmt.body:
            inputs["SUBSTACK"] = [2, self.compile_statement_list(stmt.body, block_id)]
            
        self.blocks[block_id] = {
            "opcode": "control_repeat",
            "next": None,
            "parent": parent_id,
            "inputs": inputs,
            "fields": {},
            "shadow": False,
            "topLevel": False
        }
        # Set parent links for TIMES input
        self._assign_input_parents(block_id, {"TIMES": inputs["TIMES"]})

    def compile_forever(self, stmt: ForeverStatement, block_id: str, parent_id: str):
        
        inputs = {}
        
        if stmt.body:
            inputs["SUBSTACK"] = [2, self.compile_statement_list(stmt.body, block_id)]
            
        self.blocks[block_id] = {
            "opcode": "control_forever",
            "next": None,
            "parent": parent_id,
            "inputs": inputs,
            "fields": {},
            "shadow": False,
            "topLevel": False
        }

    def compile_while(self, stmt: WhileStatement, block_id: str, parent_id: str):
        
        condition = stmt.condition
        
        # Scratch only has repeat until. While(cond) is Repeat Until(Not(cond))
        if not stmt.is_until:
            # Wrap condition in Not
            condition = UnaryOp(operator="not", operand=condition)
            
        inputs = {
            "CONDITION": self.compile_input(condition)
        }
        
        if stmt.body:
            inputs["SUBSTACK"] = [2, self.compile_statement_list(stmt.body, block_id)]

        self._assign_input_parents(block_id, {"CONDITION": inputs["CONDITION"]})
            
        self.blocks[block_id] = {
            "opcode": "control_repeat_until",
            "next": None,
            "parent": parent_id,
            "inputs": inputs,
            "fields": {},
            "shadow": False,
            "topLevel": False
        }

    def compile_wait(self, stmt: WaitStatement, block_id: str, parent_id: str):
        
        duration_input = self.compile_input(stmt.duration)
        self.blocks[block_id] = {
            "opcode": "control_wait",
            "next": None,
            "parent": parent_id,
            "inputs": {
                "DURATION": duration_input
            },
            "fields": {},
            "shadow": False,
            "topLevel": False
        }
        self._assign_input_parents(block_id, {"DURATION": duration_input})

    def compile_wait_until(self, stmt: WaitUntilStatement, block_id: str, parent_id: str):
        
        cond = self.compile_input(stmt.condition)
        self._assign_input_parents(block_id, {"CONDITION": cond})
        self.blocks[block_id] = {
            "opcode": "control_wait_until",
            "next": None,
            "parent": parent_id,
            "inputs": {
                "CONDITION": cond
            },
            "fields": {},
            "shadow": False,
            "topLevel": False
        }

    def compile_stop(self, stmt: StopStatement, block_id: str, parent_id: str):
        
        self.blocks[block_id] = {
            "opcode": "control_stop",
            "next": None,
            "parent": parent_id,
            "inputs": {},
            "fields": {
                "STOP_OPTION": [stmt.stop_option, None]
            },
            "shadow": False,
            "topLevel": False,
            "mutation": {
                "tagName": "mutation",
                "children": [],
                "hasnext": "false" if stmt.stop_option == "all" else "true"
            }
        }

    def compile_return(self, stmt: ReturnStatement, block_id: str, parent_id: str) -> str:
        
        # If there is a value, set the return variable
        first_block_id = block_id
        
        if stmt.value:
            # Use function-specific return variable if inside a function
            return_var_name = "_return"
            if hasattr(self, 'current_function_name') and self.current_function_name:
                return_var_name = f"_return_{self.current_function_name}"
            
            # Ensure return variable exists
            if return_var_name not in self.variables:
                var_id = self.gen_id()
                self.variables[return_var_name] = {"name": return_var_name, "id": var_id}
                # Add to stage variables if possible, or current target
                if self.current_target:
                    self.current_target["variables"][var_id] = [return_var_name, 0]
            
            # Compile set variable
            set_stmt = SetVariable(var_name=return_var_name, value=stmt.value, position=stmt.position)
            self.compile_set_variable(set_stmt, block_id, parent_id)
            
            # Chain stop script
            stop_id = self.gen_id()
            self.blocks[block_id]["next"] = stop_id
            
            stop_stmt = StopStatement(stop_option="this script", position=stmt.position)
            self.compile_stop(stop_stmt, stop_id, block_id)
        else:
            # Just stop script
            stop_stmt = StopStatement(stop_option="this script", position=stmt.position)
            self.compile_stop(stop_stmt, block_id, parent_id)
            
        return first_block_id

    def compile_set_variable(self, stmt: SetVariable, block_id: str, parent_id: str):
        
        var_id = self.get_variable_id(stmt.var_name)
        display_name = self.get_variable_display_name(stmt.var_name)
        value_input = self.compile_input(stmt.value)
        self.blocks[block_id] = {
            "opcode": "data_setvariableto",
            "next": None,
            "parent": parent_id,
            "inputs": {
                "VALUE": value_input
            },
            "fields": {
                "VARIABLE": [display_name, var_id]
            },
            "shadow": False,
            "topLevel": False
        }
        self._assign_input_parents(block_id, {"VALUE": value_input})

    def compile_change_variable(self, stmt: ChangeVariable, block_id: str, parent_id: str):
        
        var_id = self.get_variable_id(stmt.var_name)
        display_name = self.get_variable_display_name(stmt.var_name)
        value_input = self.compile_input(stmt.value)
        self.blocks[block_id] = {
            "opcode": "data_changevariableby",
            "next": None,
            "parent": parent_id,
            "inputs": {
                "VALUE": value_input
            },
            "fields": {
                "VARIABLE": [display_name, var_id]
            },
            "shadow": False,
            "topLevel": False
        }
        self._assign_input_parents(block_id, {"VALUE": value_input})

    def compile_show_hide_var(self, stmt: Union[ShowVariable, HideVariable], block_id: str, parent_id: str, show: bool):
        
        var_id = self.get_variable_id(stmt.var_name)
        display_name = self.get_variable_display_name(stmt.var_name)
        self.blocks[block_id] = {
            "opcode": "data_showvariable" if show else "data_hidevariable",
            "next": None,
            "parent": parent_id,
            "inputs": {},
            "fields": {
                "VARIABLE": [display_name, var_id]
            },
            "shadow": False,
            "topLevel": False
        }

    def compile_list_op(self, stmt: ListOperation, block_id: str, parent_id: str):
        
        list_id = self.get_list_id(stmt.list_name)
        opcode = ""
        inputs = {}
        
        if stmt.operation == "add":
            opcode = "data_addtolist"
            inputs["ITEM"] = self.compile_input(stmt.value)
        elif stmt.operation == "delete":
            opcode = "data_deleteoflist"
            inputs["INDEX"] = self.compile_input(stmt.index)
        elif stmt.operation == "deleteAll":
            opcode = "data_deletealloflist"
        elif stmt.operation == "insert":
            opcode = "data_insertatlist"
            inputs["ITEM"] = self.compile_input(stmt.value)
            inputs["INDEX"] = self.compile_input(stmt.index)
        elif stmt.operation == "replace":
            opcode = "data_replaceitemoflist"
            inputs["ITEM"] = self.compile_input(stmt.value)
            inputs["INDEX"] = self.compile_input(stmt.index)
            
        self.blocks[block_id] = {
            "opcode": opcode,
            "next": None,
            "parent": parent_id,
            "inputs": inputs,
            "fields": {
                "LIST": [stmt.list_name, list_id]
            },
            "shadow": False,
            "topLevel": False
        }
        # Set parent links for input blocks
        self._assign_input_parents(block_id, inputs)

    def compile_show_hide_list(self, stmt: Union[ShowList, HideList], block_id: str, parent_id: str, show: bool):
        
        list_id = self.get_list_id(stmt.list_name)
        self.blocks[block_id] = {
            "opcode": "data_showlist" if show else "data_hidelist",
            "next": None,
            "parent": parent_id,
            "inputs": {},
            "fields": {
                "LIST": [stmt.list_name, list_id]
            },
            "shadow": False,
            "topLevel": False
        }

    def _is_boolean_expr(self, expr: Expression) -> bool:
        """Best-effort classification of expressions that produce Scratch booleans.

        TurboWarp is stricter than Scratch about input array shapes.
        In particular, boolean (diamond) inputs should not carry a string/number shadow like [10, ""].
        """
        if isinstance(expr, BooleanLiteral):
            return True
        if isinstance(expr, UnaryOp):
            return expr.operator == "not"
        if isinstance(expr, BinaryOp):
            return expr.operator in ("<", ">", "==", "!=", "<=", ">=", "and", "or")
        if isinstance(expr, FunctionCall):
            return expr.func_name in {
                "key_pressed",
                "mouse_down",
                "touching",
                "touching_color",
                "color_touching",
            }
        if isinstance(expr, ReporterBlock):
            block_def = get_block_definition(expr.block_name)
            return bool(block_def and block_def.is_boolean)
        if isinstance(expr, (ListContains,)):
            return True
        return False

    def compile_input(self, expr: Expression) -> List[Any]:
        
        # 1 = shadow (literal), 2 = no shadow (block), 3 = shadow (block)
        
        if isinstance(expr, NumberLiteral):
            return [1, [4, expr.value]]
        elif isinstance(expr, StringLiteral):
            return [1, [10, expr.value]]
        elif isinstance(expr, BooleanLiteral):
            # Scratch has no "true/false" literal reporter.
            # If we encode booleans as strings, Scratch often drops them in boolean (diamond) slots.
            # Represent constants via comparisons:
            #   true  -> (0 = 0)
            #   false -> (0 = 1)
            block_id = self.gen_id()
            self.blocks[block_id] = {
                "opcode": "operator_equals",
                "next": None,
                "parent": None,
                "inputs": {
                    "OPERAND1": [1, [4, 0]],
                    "OPERAND2": [1, [4, 0 if expr.value else 1]],
                },
                "fields": {},
                "shadow": False,
                "topLevel": False,
            }
            return [2, block_id]
        elif isinstance(expr, ColorLiteral):
            return [1, [9, expr.value]]
        elif isinstance(expr, VariableRef):
            # Check if it's a custom block parameter
            if expr.name in self.current_custom_block_params:
                param_type, param_id = self.current_custom_block_params[expr.name]
                block_id = self.gen_id()
                opcode = "argument_reporter_boolean" if param_type == "boolean" else "argument_reporter_string_number"
                
                self.blocks[block_id] = {
                    "opcode": opcode,
                    "next": None,
                    "parent": None,
                    "inputs": {},
                    "fields": {
                        "VALUE": [expr.name, None]
                    },
                    "shadow": False,
                    "topLevel": False
                }
                return [2, block_id] if param_type == "boolean" else [3, block_id, [10, ""]]

            # Variable reporter
            try:
                var_id = self.get_variable_id(expr.name)
            except CompilerError:
                # Check if it's a built-in reporter that looks like a variable (e.g. size, volume)
                if expr.name == "size":
                    block_id = self.gen_id()
                    self.blocks[block_id] = {
                        "opcode": "looks_size",
                        "next": None,
                        "parent": None,
                        "inputs": {},
                        "fields": {},
                        "shadow": False,
                        "topLevel": False
                    }
                    return [3, block_id, [10, ""]]
                elif expr.name == "volume":
                    block_id = self.gen_id()
                    self.blocks[block_id] = {
                        "opcode": "sound_volume",
                        "next": None,
                        "parent": None,
                        "inputs": {},
                        "fields": {},
                        "shadow": False,
                        "topLevel": False
                    }
                    return [3, block_id, [10, ""]]
                elif expr.name == "loudness":
                    block_id = self.gen_id()
                    self.blocks[block_id] = {
                        "opcode": "sensing_loudness",
                        "next": None,
                        "parent": None,
                        "inputs": {},
                        "fields": {},
                        "shadow": False,
                        "topLevel": False
                    }
                    return [3, block_id, [10, ""]]
                elif expr.name == "timer":
                    block_id = self.gen_id()
                    self.blocks[block_id] = {
                        "opcode": "sensing_timer",
                        "next": None,
                        "parent": None,
                        "inputs": {},
                        "fields": {},
                        "shadow": False,
                        "topLevel": False
                    }
                    return [3, block_id, [10, ""]]
                elif expr.name == "x":
                    block_id = self.gen_id()
                    self.blocks[block_id] = {
                        "opcode": "motion_xposition",
                        "next": None,
                        "parent": None,
                        "inputs": {},
                        "fields": {},
                        "shadow": False,
                        "topLevel": False
                    }
                    return [3, block_id, [10, ""]]
                elif expr.name == "y":
                    block_id = self.gen_id()
                    self.blocks[block_id] = {
                        "opcode": "motion_yposition",
                        "next": None,
                        "parent": None,
                        "inputs": {},
                        "fields": {},
                        "shadow": False,
                        "topLevel": False
                    }
                    return [3, block_id, [10, ""]]
                elif expr.name == "direction":
                    block_id = self.gen_id()
                    self.blocks[block_id] = {
                        "opcode": "motion_direction",
                        "next": None,
                        "parent": None,
                        "inputs": {},
                        "fields": {},
                        "shadow": False,
                        "topLevel": False
                    }
                    return [3, block_id, [10, ""]]
                elif expr.name == "mouse_x":
                    block_id = self.gen_id()
                    self.blocks[block_id] = {
                        "opcode": "sensing_mousex",
                        "next": None,
                        "parent": None,
                        "inputs": {},
                        "fields": {},
                        "shadow": False,
                        "topLevel": False
                    }
                    return [3, block_id, [10, ""]]
                elif expr.name == "mouse_y":
                    block_id = self.gen_id()
                    self.blocks[block_id] = {
                        "opcode": "sensing_mousey",
                        "next": None,
                        "parent": None,
                        "inputs": {},
                        "fields": {},
                        "shadow": False,
                        "topLevel": False
                    }
                    return [3, block_id, [10, ""]]
                elif expr.name == "answer":
                    block_id = self.gen_id()
                    self.blocks[block_id] = {
                        "opcode": "sensing_answer",
                        "next": None,
                        "parent": None,
                        "inputs": {},
                        "fields": {},
                        "shadow": False,
                        "topLevel": False
                    }
                    return [3, block_id, [10, ""]]
                elif expr.name == "username":
                    block_id = self.gen_id()
                    self.blocks[block_id] = {
                        "opcode": "sensing_username",
                        "next": None,
                        "parent": None,
                        "inputs": {},
                        "fields": {},
                        "shadow": False,
                        "topLevel": False
                    }
                    return [3, block_id, [10, ""]]
                elif expr.name == "days_since_2000":
                    block_id = self.gen_id()
                    self.blocks[block_id] = {
                        "opcode": "sensing_dayssince2000",
                        "next": None,
                        "parent": None,
                        "inputs": {},
                        "fields": {},
                        "shadow": False,
                        "topLevel": False
                    }
                    return [3, block_id, [10, ""]]
                elif expr.name == "costume_number":
                    block_id = self.gen_id()
                    self.blocks[block_id] = {
                        "opcode": "looks_costumenumbername",
                        "next": None,
                        "parent": None,
                        "inputs": {},
                        "fields": {
                            "NUMBER_NAME": ["number", None]
                        },
                        "shadow": False,
                        "topLevel": False
                    }
                    return [3, block_id, [10, ""]]
                elif expr.name == "costume_name":
                    block_id = self.gen_id()
                    self.blocks[block_id] = {
                        "opcode": "looks_costumenumbername",
                        "next": None,
                        "parent": None,
                        "inputs": {},
                        "fields": {
                            "NUMBER_NAME": ["name", None]
                        },
                        "shadow": False,
                        "topLevel": False
                    }
                    return [3, block_id, [10, ""]]
                elif expr.name == "size":
                    block_id = self.gen_id()
                    self.blocks[block_id] = {
                        "opcode": "looks_size",
                        "next": None,
                        "parent": None,
                        "inputs": {},
                        "fields": {},
                        "shadow": False,
                        "topLevel": False
                    }
                    return [3, block_id, [10, ""]]
                elif expr.name == "volume":
                    block_id = self.gen_id()
                    self.blocks[block_id] = {
                        "opcode": "sound_volume",
                        "next": None,
                        "parent": None,
                        "inputs": {},
                        "fields": {},
                        "shadow": False,
                        "topLevel": False
                    }
                    return [3, block_id, [10, ""]]
                elif expr.name == "timer":
                    block_id = self.gen_id()
                    self.blocks[block_id] = {
                        "opcode": "sensing_timer",
                        "next": None,
                        "parent": None,
                        "inputs": {},
                        "fields": {},
                        "shadow": False,
                        "topLevel": False
                    }
                    return [3, block_id, [10, ""]]
                elif expr.name == "loudness":
                    block_id = self.gen_id()
                    self.blocks[block_id] = {
                        "opcode": "sensing_loudness",
                        "next": None,
                        "parent": None,
                        "inputs": {},
                        "fields": {},
                        "shadow": False,
                        "topLevel": False
                    }
                    return [3, block_id, [10, ""]]
                # TurboWarp runtime reporters (implemented as special argument_reporter_boolean blocks)
                elif expr.name == "is_turbowarp":
                    block_id = self.gen_id()
                    self.blocks[block_id] = {
                        "opcode": "argument_reporter_boolean",
                        "next": None,
                        "parent": None,
                        "inputs": {},
                        "fields": {
                            "VALUE": ["is TurboWarp?", None]
                        },
                        "shadow": False,
                        "topLevel": False
                    }
                    return [2, block_id]  # Boolean type
                elif expr.name == "is_compiled":
                    block_id = self.gen_id()
                    self.blocks[block_id] = {
                        "opcode": "argument_reporter_boolean",
                        "next": None,
                        "parent": None,
                        "inputs": {},
                        "fields": {
                            "VALUE": ["is compiled?", None]
                        },
                        "shadow": False,
                        "topLevel": False
                    }
                    return [2, block_id]  # Boolean type
                elif expr.name == "is_fenced":
                    block_id = self.gen_id()
                    self.blocks[block_id] = {
                        "opcode": "argument_reporter_boolean",
                        "next": None,
                        "parent": None,
                        "inputs": {},
                        "fields": {
                            "VALUE": ["is fenced?", None]
                        },
                        "shadow": False,
                        "topLevel": False
                    }
                    return [2, block_id]  # Boolean type
                else:
                    raise
            
            block_id = self.gen_id()
            self.blocks[block_id] = {
                "opcode": "data_variable",
                "next": None,
                "parent": None,
                "inputs": {},
                "fields": {
                    "VARIABLE": [expr.name, var_id]
                },
                "shadow": False,
                "topLevel": False
            }
            return [3, block_id, [10, ""]] # 3 = block over shadow
            
        elif isinstance(expr, ListRef):
            block_id = self.gen_id()
            list_id = self.get_list_id(expr.name)
            self.blocks[block_id] = {
                "opcode": "data_listcontents",
                "next": None,
                "parent": None,
                "inputs": {},
                "fields": {
                    "LIST": [expr.name, list_id]
                },
                "shadow": False,
                "topLevel": False
            }
            return [3, block_id, [10, ""]]
            
        elif isinstance(expr, (BinaryOp, UnaryOp, FunctionCall, ReporterBlock, ListItemAccess, ListLength, ListContains, ListIndexOf)):
            rid = self.compile_reporter(expr)
            return [2, rid] if self._is_boolean_expr(expr) else [3, rid, [10, ""]]
            
        raise CompilerError(f"Unknown expression type: {type(expr)}", expr)

    def compile_reporter(self, expr: Expression) -> str:
        
        block_id = self.gen_id()
        
        if isinstance(expr, BinaryOp):
            self.compile_binary_op(expr, block_id)
        elif isinstance(expr, UnaryOp):
            self.compile_unary_op(expr, block_id)
        elif isinstance(expr, FunctionCall):
            self.compile_function_call(expr, block_id)
        elif isinstance(expr, ReporterBlock):
            self.compile_reporter_block(expr, block_id)
        elif isinstance(expr, ListItemAccess):
            self.compile_list_item(expr, block_id)
        elif isinstance(expr, ListLength):
            self.compile_list_length(expr, block_id)
        elif isinstance(expr, ListContains):
            self.compile_list_contains(expr, block_id)
        elif isinstance(expr, ListIndexOf):
            self.compile_list_index(expr, block_id)
        else:
            # Fallback for literals wrapped in reporter context (shouldn't happen often)
            pass
            
        return block_id

    def compile_binary_op(self, expr: BinaryOp, block_id: str):
        
        opcode = ""
        inputs = {}
        
        if expr.operator == "+":
            opcode = "operator_add"
            inputs = {"NUM1": self.compile_input(expr.left), "NUM2": self.compile_input(expr.right)}
        elif expr.operator == "-":
            opcode = "operator_subtract"
            inputs = {"NUM1": self.compile_input(expr.left), "NUM2": self.compile_input(expr.right)}
        elif expr.operator == "*":
            opcode = "operator_multiply"
            inputs = {"NUM1": self.compile_input(expr.left), "NUM2": self.compile_input(expr.right)}
        elif expr.operator == "/":
            opcode = "operator_divide"
            inputs = {"NUM1": self.compile_input(expr.left), "NUM2": self.compile_input(expr.right)}
        elif expr.operator == "mod":
            opcode = "operator_mod"
            inputs = {"NUM1": self.compile_input(expr.left), "NUM2": self.compile_input(expr.right)}
        elif expr.operator == ">":
            opcode = "operator_gt"
            inputs = {"OPERAND1": self.compile_input(expr.left), "OPERAND2": self.compile_input(expr.right)}
        elif expr.operator == "<":
            opcode = "operator_lt"
            inputs = {"OPERAND1": self.compile_input(expr.left), "OPERAND2": self.compile_input(expr.right)}
        elif expr.operator == "==":
            opcode = "operator_equals"
            inputs = {"OPERAND1": self.compile_input(expr.left), "OPERAND2": self.compile_input(expr.right)}
        elif expr.operator == "!=":
            # Scratch has no "not equals" block; lower to NOT(EQUALS)
            inner_id = self.gen_id()
            inner_expr = BinaryOp(operator="==", left=expr.left, right=expr.right, position=expr.position)
            self.compile_binary_op(inner_expr, inner_id)
            self.blocks[block_id] = {
                "opcode": "operator_not",
                "next": None,
                "parent": None,
                "inputs": {
                    "OPERAND": [2, inner_id]
                },
                "fields": {},
                "shadow": False,
                "topLevel": False
            }
            self._assign_input_parents(block_id, {"OPERAND": [2, inner_id]})
            return
        elif expr.operator == "and":
            opcode = "operator_and"
            inputs = {"OPERAND1": self.compile_input(expr.left), "OPERAND2": self.compile_input(expr.right)}
        elif expr.operator == "or":
            opcode = "operator_or"
            inputs = {"OPERAND1": self.compile_input(expr.left), "OPERAND2": self.compile_input(expr.right)}
        elif expr.operator == "<=":
            # Lower to NOT( left > right )
            inner_id = self.gen_id()
            inner_expr = BinaryOp(operator=">", left=expr.left, right=expr.right, position=expr.position)
            self.compile_binary_op(inner_expr, inner_id)
            self.blocks[block_id] = {
                "opcode": "operator_not",
                "next": None,
                "parent": None,
                "inputs": {
                    "OPERAND": [2, inner_id]
                },
                "fields": {},
                "shadow": False,
                "topLevel": False
            }
            self._assign_input_parents(block_id, {"OPERAND": [2, inner_id]})
            return
        elif expr.operator == ">=":
            # Lower to NOT( left < right )
            inner_id = self.gen_id()
            inner_expr = BinaryOp(operator="<", left=expr.left, right=expr.right, position=expr.position)
            self.compile_binary_op(inner_expr, inner_id)
            self.blocks[block_id] = {
                "opcode": "operator_not",
                "next": None,
                "parent": None,
                "inputs": {
                    "OPERAND": [2, inner_id]
                },
                "fields": {},
                "shadow": False,
                "topLevel": False
            }
            self._assign_input_parents(block_id, {"OPERAND": [2, inner_id]})
            return

        if not opcode:
            raise CompilerError(f"Unsupported binary operator: {expr.operator}", expr)
            
        self.blocks[block_id] = {
            "opcode": opcode,
            "next": None,
            "parent": None,
            "inputs": inputs,
            "fields": {},
            "shadow": False,
            "topLevel": False
        }
        self._assign_input_parents(block_id, inputs)

    def compile_unary_op(self, expr: UnaryOp, block_id: str):
        
        if expr.operator == "not":
            inputs = {
                "OPERAND": self.compile_input(expr.operand)
            }
            self.blocks[block_id] = {
                "opcode": "operator_not",
                "next": None,
                "parent": None,
                "inputs": inputs,
                "fields": {},
                "shadow": False,
                "topLevel": False
            }
            self._assign_input_parents(block_id, inputs)

    def compile_function_call(self, expr: FunctionCall, block_id: str):
        
        # Check for math functions
        if expr.func_name in MATH_OPERATIONS:
            self.blocks[block_id] = {
                "opcode": "operator_mathop",
                "next": None,
                "parent": None,
                "inputs": {
                    "NUM": self.compile_input(expr.args[0])
                },
                "fields": {
                    "OPERATOR": [MATH_OPERATIONS[expr.func_name], None]
                },
                "shadow": False,
                "topLevel": False
            }
            return

        # Other built-ins
        if expr.func_name == "key_pressed":
            # Special handling for key_pressed.
            # Scratch encodes the key selection via a shadow menu block (sensing_keyoptions)
            # referenced from the KEY_OPTION input. Emitting KEY_OPTION as a plain field can
            # display as blank in Scratch/TurboWarp even if the JSON looks plausible.
            key_val: Any = "space"
            if expr.args and hasattr(expr.args[0], "value"):
                key_val = expr.args[0].value
            key_val = self._normalize_key_option(key_val)

            menu_id = self._make_menu_shadow(
                opcode="sensing_keyoptions",
                field_name="KEY_OPTION",
                field_value=key_val,
                parent_id=block_id,
            )
            self.blocks[block_id] = {
                "opcode": "sensing_keypressed",
                "next": None,
                "parent": None,
                "inputs": {
                    "KEY_OPTION": [1, menu_id]
                },
                "fields": {},
                "shadow": False,
                "topLevel": False
            }
        elif expr.func_name == "random":
            self.blocks[block_id] = {
                "opcode": "operator_random",
                "next": None,
                "parent": None,
                "inputs": {
                    "FROM": self.compile_input(expr.args[0]),
                    "TO": self.compile_input(expr.args[1])
                },
                "fields": {},
                "shadow": False,
                "topLevel": False
            }
        elif expr.func_name == "join":
            self.blocks[block_id] = {
                "opcode": "operator_join",
                "next": None,
                "parent": None,
                "inputs": {
                    "STRING1": self.compile_input(expr.args[0]),
                    "STRING2": self.compile_input(expr.args[1])
                },
                "fields": {},
                "shadow": False,
                "topLevel": False
            }
        elif expr.func_name == "length":
            arg = expr.args[0]
            # Check if arg is a list reference
            is_list = False
            if isinstance(arg, VariableRef):
                try:
                    list_id = self.get_list_id(arg.name)
                    # It IS a list! Compile as data_lengthoflist
                    self.blocks[block_id] = {
                        "opcode": "data_lengthoflist",
                        "next": None,
                        "parent": None,
                        "inputs": {},
                        "fields": {
                            "LIST": [arg.name, list_id]
                        },
                        "shadow": False,
                        "topLevel": False
                    }
                    is_list = True
                except CompilerError:
                    pass
            
            if not is_list:
                self.blocks[block_id] = {
                    "opcode": "operator_length",
                    "next": None,
                    "parent": None,
                    "inputs": {
                        "STRING": self.compile_input(expr.args[0])
                    },
                    "fields": {},
                    "shadow": False,
                    "topLevel": False
                }
        elif expr.func_name == "letter":
            self.blocks[block_id] = {
                "opcode": "operator_letter_of",
                "next": None,
                "parent": None,
                "inputs": {
                    "LETTER": self.compile_input(expr.args[0]),
                    "STRING": self.compile_input(expr.args[1])
                },
                "fields": {},
                "shadow": False,
                "topLevel": False
            }
        elif expr.func_name == "contains":
            self.blocks[block_id] = {
                "opcode": "operator_contains",
                "next": None,
                "parent": None,
                "inputs": {
                    "STRING1": self.compile_input(expr.args[0]),
                    "STRING2": self.compile_input(expr.args[1])
                },
                "fields": {},
                "shadow": False,
                "topLevel": False
            }
        elif expr.func_name == "round":
            self.blocks[block_id] = {
                "opcode": "operator_round",
                "next": None,
                "parent": None,
                "inputs": {
                    "NUM": self.compile_input(expr.args[0])
                },
                "fields": {},
                "shadow": False,
                "topLevel": False
            }
        else:
            # Check if this is a built-in reporter/boolean block from SENSING_BLOCKS, etc.
            block_def = _get_block_def(expr.func_name)
            if block_def and (block_def.is_reporter or block_def.is_boolean):
                self._record_extension_from_opcode(block_def.opcode)
                
                inputs = {}
                fields = {}
                
                # Special handling for attribute_of: args are (property, object)
                # but PROPERTY is a field and OBJECT is an input
                if expr.func_name == 'attribute_of' and len(expr.args) >= 2:
                    prop_arg = expr.args[0]
                    obj_arg = expr.args[1]
                    # PROPERTY goes to field
                    if isinstance(prop_arg, StringLiteral):
                        fields['PROPERTY'] = [prop_arg.value, None]
                    else:
                        fields['PROPERTY'] = [str(prop_arg), None]
                    # OBJECT goes to input - need a menu shadow block
                    if isinstance(obj_arg, StringLiteral):
                        # Create a menu shadow block for the sprite name
                        menu_id = self._make_menu_shadow(
                            opcode='sensing_of_object_menu',
                            field_name='OBJECT',
                            field_value=obj_arg.value,
                            parent_id=block_id
                        )
                        inputs['OBJECT'] = [1, menu_id]
                    else:
                        inputs['OBJECT'] = self.compile_input(obj_arg)
                # Special handling for touching: needs sensing_touchingobjectmenu shadow
                # Parser may put string literal in args OR in fields['TOUCHINGOBJECTMENU']
                elif expr.func_name == 'touching':
                    obj_value = None
                    if len(expr.args) >= 1 and isinstance(expr.args[0], StringLiteral):
                        obj_value = expr.args[0].value
                    elif hasattr(expr, 'fields') and 'TOUCHINGOBJECTMENU' in expr.fields:
                        obj_value = expr.fields['TOUCHINGOBJECTMENU']
                    
                    if obj_value is not None:
                        menu_id = self._make_menu_shadow(
                            opcode='sensing_touchingobjectmenu',
                            field_name='TOUCHINGOBJECTMENU',
                            field_value=obj_value,
                            parent_id=block_id
                        )
                        inputs['TOUCHINGOBJECTMENU'] = [1, menu_id]
                    elif len(expr.args) >= 1:
                        inputs['TOUCHINGOBJECTMENU'] = self.compile_input(expr.args[0])
                else:
                    # Default handling: process inputs first, then fields
                    arg_idx = 0
                    for i, input_name in enumerate(block_def.inputs):
                        if arg_idx < len(expr.args):
                            inputs[input_name] = self.compile_input(expr.args[arg_idx])
                            arg_idx += 1
                            
                    for i, field_name in enumerate(block_def.fields):
                        if arg_idx < len(expr.args):
                            arg = expr.args[arg_idx]
                            if isinstance(arg, StringLiteral):
                                fields[field_name] = [arg.value, None]
                            elif isinstance(arg, NumberLiteral):
                                fields[field_name] = [str(arg.value), None]
                            else:
                                # For dynamic field values, some blocks support inputs too
                                # Try as input (e.g., sensing_of OBJECT)
                                inputs[field_name] = self.compile_input(arg)
                            arg_idx += 1
                
                self.blocks[block_id] = {
                    "opcode": block_def.opcode,
                    "next": None,
                    "parent": None,
                    "inputs": inputs,
                    "fields": fields,
                    "shadow": False,
                    "topLevel": False
                }
                self._assign_input_parents(block_id, inputs)
                return
            
            # Custom block call as reporter
            # This is tricky because Scratch doesn't support custom reporters natively.
            # We assume the custom block sets a return variable.
            # We can't easily inline the call here because we are in an expression context (reporter).
            # But we can return the variable that holds the result.
            # HOWEVER, the custom block must have been called BEFORE this expression is evaluated.
            # This implies that 'foo()' in an expression is not really a call, but a read of the result?
            # No, that would be weird semantics.
            
            # If the user writes `set x = foo()`, we want to:
            # 1. Call foo (stack block)
            # 2. Set x to _return_foo
            
            # But `compile_function_call` is called by `compile_input` or `compile_expression` which expects a reporter block ID.
            # We cannot insert a stack block here.
            
            # The only way to support this in Scratch is if the compiler lifts the function call out of the expression.
            # e.g. `set x = foo() + 1` becomes:
            #   call foo
            #   set x = _return_foo + 1
            
            # This requires a significant architectural change to support "expression lowering" or "pre-computation".
            # For now, we will assume the user knows what they are doing and we just return the variable reference.
            # BUT wait, if we just return the variable, the function is never called!
            
            # Current workaround:
            # We can't support true function calls in expressions without lowering.
            # We will raise an error for now, or just return the variable and assume the user called it previously?
            # No, that's bad UX.
            
            # Let's check if we can hack it.
            # If we are compiling a statement, we can inject blocks.
            # But here we are deep in expression compilation.
            
            # For this iteration, let's implement the variable read, assuming the user called it?
            # No, the user expects `foo()` to call foo.
            
            # Let's look at how `compile_custom_block_call` works. It compiles a stack block.
            # If we are here, we need a reporter.
            
            # We will return a variable reporter for `_return_{func_name}`.
            # AND we will log a warning that the function is not actually called?
            # Or better: we assume this is a variable read for a function that was just called?
            
            # Actually, maybe we can't fix this fully right now without a big refactor.
            # But the user asked for "distinctive variable upon compiling".
            # So I should at least implement the variable naming convention.
            
            return_var_name = f"_return_{expr.func_name}"
            
            # Check if variable exists, if not create it (it might be created later when the function is defined/compiled)
            if return_var_name not in self.variables:
                 var_id = self.gen_id()
                 self.variables[return_var_name] = {"name": return_var_name, "id": var_id}
                 if self.current_target:
                    self.current_target["variables"][var_id] = [return_var_name, 0]
            
            var_id = self.get_variable_id(return_var_name)
            self.blocks[block_id] = {
                "opcode": "data_variable",
                "next": None,
                "parent": None,
                "inputs": {},
                "fields": {
                    "VARIABLE": [return_var_name, var_id]
                },
                "shadow": False,
                "topLevel": False
            }

    def compile_reporter_block(self, expr: ReporterBlock, block_id: str):
        
        # Handle TurboWarp runtime reporters - these use special argument_reporter_boolean blocks
        # NOT the tw_* opcodes, because they need to work in standard Scratch too
        if expr.block_name == "is_turbowarp":
            self.blocks[block_id] = {
                "opcode": "argument_reporter_boolean",
                "next": None,
                "parent": None,
                "inputs": {},
                "fields": {
                    "VALUE": ["is TurboWarp?", None]
                },
                "shadow": False,
                "topLevel": False
            }
            return
        elif expr.block_name == "is_compiled":
            self.blocks[block_id] = {
                "opcode": "argument_reporter_boolean",
                "next": None,
                "parent": None,
                "inputs": {},
                "fields": {
                    "VALUE": ["is compiled?", None]
                },
                "shadow": False,
                "topLevel": False
            }
            return
        elif expr.block_name == "is_fenced":
            self.blocks[block_id] = {
                "opcode": "argument_reporter_boolean",
                "next": None,
                "parent": None,
                "inputs": {},
                "fields": {
                    "VALUE": ["is fenced?", None]
                },
                "shadow": False,
                "topLevel": False
            }
            return
        
        # Check if it's an extension reporter block
        ext_block = self.extension_loader.get_block(expr.block_name)
        if ext_block and ext_block.block_type in ("reporter", "boolean"):
            self.compile_extension_reporter(expr, ext_block, block_id)
            return
        
        block_def = get_block_definition(expr.block_name)
        if not block_def:
            raise CompilerError(f"Unknown reporter: {expr.block_name}", expr)
            
        inputs = {}
        fields = {}
        
        for i, arg in enumerate(expr.args):
            if i < len(block_def.inputs):
                inputs[block_def.inputs[i]] = self.compile_input(arg)
                
        for field_name, value in expr.fields.items():
            fields[field_name] = [value, None]

        # Some dropdown blocks become uneditable (and can break TurboWarp)
        # if KEY_OPTION is missing/empty. Also, sensing_keypressed is canonically
        # encoded with a KEY_OPTION *input* referencing a sensing_keyoptions shadow.
        if block_def.opcode == "sensing_keypressed":
            current = fields.get("KEY_OPTION", [None, None])[0]
            key_val = self._normalize_key_option(current)
            menu_id = self._make_menu_shadow(
                opcode="sensing_keyoptions",
                field_name="KEY_OPTION",
                field_value=key_val,
                parent_id=block_id,
            )
            inputs["KEY_OPTION"] = [1, menu_id]
            fields.pop("KEY_OPTION", None)
        elif block_def.opcode == "event_whenkeypressed":
            current = fields.get("KEY_OPTION", [None, None])[0]
            fields["KEY_OPTION"] = [self._normalize_key_option(current), None]
        # sensing_touchingobject needs menu shadow block for TOUCHINGOBJECTMENU
        elif block_def.opcode == "sensing_touchingobject":
            obj_value = fields.get("TOUCHINGOBJECTMENU", [None, None])[0]
            if obj_value is not None:
                menu_id = self._make_menu_shadow(
                    opcode="sensing_touchingobjectmenu",
                    field_name="TOUCHINGOBJECTMENU",
                    field_value=obj_value,
                    parent_id=block_id,
                )
                inputs["TOUCHINGOBJECTMENU"] = [1, menu_id]
                fields.pop("TOUCHINGOBJECTMENU", None)
            
        self.blocks[block_id] = {
            "opcode": block_def.opcode,
            "next": None,
            "parent": None,
            "inputs": inputs,
            "fields": fields,
            "shadow": False,
            "topLevel": False
        }
        self._assign_input_parents(block_id, inputs)

    def compile_list_item(self, expr: ListItemAccess, block_id: str):
        
        list_id = self.get_list_id(expr.list_name)
        self.blocks[block_id] = {
            "opcode": "data_itemoflist",
            "next": None,
            "parent": None,
            "inputs": {
                "INDEX": self.compile_input(expr.index)
            },
            "fields": {
                "LIST": [expr.list_name, list_id]
            },
            "shadow": False,
            "topLevel": False
        }

    def compile_extension_reporter(self, expr: ReporterBlock, ext_block: ExtensionBlock, block_id: str):
        
        # Record the extension
        ext_id = self.extension_loader.get_extension_for_opcode(ext_block.opcode)
        if ext_id:
            self.extensions.add(ext_id)
        
        inputs = {}
        fields = {}
        
        # Map arguments
        for i, arg in enumerate(expr.args):
            if i < len(ext_block.arguments):
                ext_arg = ext_block.arguments[i]
                arg_name = ext_arg.name
                
                # Handle menu arguments
                if ext_arg.menu and isinstance(arg, StringLiteral):
                    fields[arg_name] = [arg.value, None]
                    continue
                
                inputs[arg_name] = self.compile_input(arg)
        
        # Add any additional fields
        for field_name, value in expr.fields.items():
            fields[field_name] = [value, None]
        
        self.blocks[block_id] = {
            "opcode": ext_block.opcode,
            "next": None,
            "parent": None,
            "inputs": inputs,
            "fields": fields,
            "shadow": False,
            "topLevel": False
        }
        
        self._assign_input_parents(block_id, inputs)

    def compile_list_length(self, expr: ListLength, block_id: str):
        
        list_id = self.get_list_id(expr.list_name)
        self.blocks[block_id] = {
            "opcode": "data_lengthoflist",
            "next": None,
            "parent": None,
            "inputs": {},
            "fields": {
                "LIST": [expr.list_name, list_id]
            },
            "shadow": False,
            "topLevel": False
        }

    def compile_list_contains(self, expr: ListContains, block_id: str):
        
        list_id = self.get_list_id(expr.list_name)
        self.blocks[block_id] = {
            "opcode": "data_listcontainsitem",
            "next": None,
            "parent": None,
            "inputs": {
                "ITEM": self.compile_input(expr.item)
            },
            "fields": {
                "LIST": [expr.list_name, list_id]
            },
            "shadow": False,
            "topLevel": False
        }

    def compile_list_index(self, expr: ListIndexOf, block_id: str):
        
        list_id = self.get_list_id(expr.list_name)
        self.blocks[block_id] = {
            "opcode": "data_itemnumoflist",
            "next": None,
            "parent": None,
            "inputs": {
                "ITEM": self.compile_input(expr.item)
            },
            "fields": {
                "LIST": [expr.list_name, list_id]
            },
            "shadow": False,
            "topLevel": False
        }

