import json
import os
import re
from dataclasses import dataclass, field
from typing import Dict, List, Any, Optional, Union


@dataclass
class ExtensionArgument:
    name: str                          # Internal name (e.g., "X", "MESSAGE")
    arg_type: str = "number"           # "number", "string", "boolean", "angle", "color", "note", "matrix", "menu"
    default_value: Any = None          # Default value
    menu: Optional[str] = None         # Menu name if arg_type is "menu" or has a dropdown


@dataclass
class ExtensionBlock:
    opcode: str                         # Scratch opcode (e.g., "SPsoundWaves_playNoteV2")
    felis_name: str                     # Name to use in Felis code (e.g., "sound_waves.play_note")
    block_type: str                     # "command", "reporter", "boolean", "hat", "conditional", "loop"
    text: str                           # Block text with argument placeholders (e.g., "play [WAVE] note [NOTE]")
    arguments: List[ExtensionArgument] = field(default_factory=list)
    is_terminal: bool = False           # Whether this block ends a script
    hidden: bool = False                # Hidden from palette
    

@dataclass
class ExtensionMenu:
    name: str
    items: List[Union[str, Dict[str, str]]]  # List of items or {text, value} dicts
    accept_reporters: bool = False


@dataclass
class FelisExtension:
    id: str                             # Extension ID (e.g., "SPsoundWaves")
    name: str                           # Display name (e.g., "Sound Waves")
    description: str = ""
    version: str = "1.0.0"
    author: str = ""
    color1: str = "#0FBD8C"             # Primary color
    color2: Optional[str] = None        # Secondary color  
    color3: Optional[str] = None        # Tertiary color
    blocks: List[ExtensionBlock] = field(default_factory=list)
    menus: Dict[str, ExtensionMenu] = field(default_factory=dict)
    
    # The URL where TurboWarp/PenguinMod can load this extension from
    # This is included in the output SB3's extensionURLs to auto-load the extension
    extension_url: Optional[str] = None
    
    # Legacy field for backwards compatibility
    scratch_url: Optional[str] = None
    

class ExtensionLoader:
    def __init__(self):
        self.extensions: Dict[str, FelisExtension] = {}
        self.block_map: Dict[str, ExtensionBlock] = {}  # felis_name -> block
        self.extension_by_opcode: Dict[str, str] = {}   # opcode -> extension_id
        
    def load_from_file(self, filepath: str) -> FelisExtension:
        with open(filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return self.load_from_dict(data)
    
    def load_from_dict(self, data: Dict[str, Any]) -> FelisExtension:
        # Parse menus
        menus = {}
        for menu_name, menu_data in data.get("menus", {}).items():
            if isinstance(menu_data, list):
                menus[menu_name] = ExtensionMenu(
                    name=menu_name,
                    items=menu_data,
                    accept_reporters=False
                )
            else:
                menus[menu_name] = ExtensionMenu(
                    name=menu_name,
                    items=menu_data.get("items", []),
                    accept_reporters=menu_data.get("acceptReporters", False)
                )
        
        # Parse blocks
        blocks = []
        for block_data in data.get("blocks", []):
            if block_data.get("blockType") == "label":
                continue  # Skip labels
                
            arguments = []
            for arg_name, arg_data in block_data.get("arguments", {}).items():
                if isinstance(arg_data, dict):
                    arguments.append(ExtensionArgument(
                        name=arg_name,
                        arg_type=self._convert_arg_type(arg_data.get("type", "string")),
                        default_value=arg_data.get("defaultValue"),
                        menu=arg_data.get("menu")
                    ))
                else:
                    arguments.append(ExtensionArgument(
                        name=arg_name,
                        arg_type="string",
                        default_value=arg_data
                    ))
            
            # Generate Felis name from opcode if not provided
            felis_name = block_data.get("felisName")
            if not felis_name:
                # Convert camelCase to snake_case and add extension prefix
                opcode = block_data["opcode"]
                felis_name = f"{data['id']}.{self._to_snake_case(opcode)}"
            
            blocks.append(ExtensionBlock(
                opcode=f"{data['id']}_{block_data['opcode']}" if not block_data['opcode'].startswith(data['id']) else block_data['opcode'],
                felis_name=felis_name,
                block_type=self._convert_block_type(block_data.get("blockType", "command")),
                text=block_data.get("text", ""),
                arguments=arguments,
                is_terminal=block_data.get("isTerminal", False),
                hidden=block_data.get("hideFromPalette", False)
            ))
        
        ext = FelisExtension(
            id=data["id"],
            name=data.get("name", data["id"]),
            description=data.get("description", ""),
            version=data.get("version", "1.0.0"),
            author=data.get("author", ""),
            color1=data.get("color1", "#0FBD8C"),
            color2=data.get("color2"),
            color3=data.get("color3"),
            blocks=blocks,
            menus=menus,
            extension_url=data.get("extensionUrl") or data.get("scratchUrl"),
            scratch_url=data.get("scratchUrl")
        )
        
        self.register_extension(ext)
        return ext
    
    def register_extension(self, ext: FelisExtension):
        self.extensions[ext.id] = ext
        
        for block in ext.blocks:
            self.block_map[block.felis_name] = block
            self.extension_by_opcode[block.opcode] = ext.id
            
            # Also register without the extension prefix for convenience
            simple_name = block.felis_name.split(".")[-1] if "." in block.felis_name else block.felis_name
            if simple_name not in self.block_map:
                self.block_map[simple_name] = block
    
    def get_block(self, name: str) -> Optional[ExtensionBlock]:
        return self.block_map.get(name)
    
    def get_extension(self, ext_id: str) -> Optional[FelisExtension]:
        return self.extensions.get(ext_id)
    
    def get_extension_for_opcode(self, opcode: str) -> Optional[str]:
        return self.extension_by_opcode.get(opcode)
    
    def load_directory(self, dirpath: str):
        if not os.path.exists(dirpath):
            return
            
        for filename in os.listdir(dirpath):
            if filename.endswith(".felisx"):
                self.load_from_file(os.path.join(dirpath, filename))
    
    def _convert_arg_type(self, scratch_type: str) -> str:
        type_map = {
            "number": "number",
            "string": "string", 
            "boolean": "boolean",
            "angle": "angle",
            "color": "color",
            "note": "note",
            "matrix": "matrix",
            "STRING": "string",
            "NUMBER": "number",
            "BOOLEAN": "boolean",
            "ANGLE": "angle",
            "COLOR": "color",
            "NOTE": "note",
        }
        return type_map.get(scratch_type, "string")
    
    def _convert_block_type(self, scratch_type: str) -> str:
        type_map = {
            "command": "command",
            "reporter": "reporter",
            "Boolean": "boolean",
            "BOOLEAN": "boolean",
            "hat": "hat",
            "conditional": "conditional",
            "loop": "loop",
            "COMMAND": "command",
            "REPORTER": "reporter",
            "HAT": "hat",
            "CONDITIONAL": "conditional",
            "LOOP": "loop",
        }
        return type_map.get(scratch_type, "command")
    
    def _to_snake_case(self, name: str) -> str:
        s1 = re.sub('(.)([A-Z][a-z]+)', r'\1_\2', name)
        return re.sub('([a-z0-9])([A-Z])', r'\1_\2', s1).lower()


def export_extension(ext: FelisExtension, filepath: str):
    data = {
        "id": ext.id,
        "name": ext.name,
        "description": ext.description,
        "version": ext.version,
        "author": ext.author,
        "color1": ext.color1,
    }
    
    if ext.color2:
        data["color2"] = ext.color2
    if ext.color3:
        data["color3"] = ext.color3
    if ext.extension_url:
        data["extensionUrl"] = ext.extension_url
    if ext.scratch_url:
        data["scratchUrl"] = ext.scratch_url
    
    # Export menus
    data["menus"] = {}
    for menu_name, menu in ext.menus.items():
        if menu.accept_reporters:
            data["menus"][menu_name] = {
                "acceptReporters": True,
                "items": menu.items
            }
        else:
            data["menus"][menu_name] = menu.items
    
    # Export blocks
    data["blocks"] = []
    for block in ext.blocks:
        block_data = {
            "opcode": block.opcode.replace(f"{ext.id}_", "") if block.opcode.startswith(ext.id) else block.opcode,
            "felisName": block.felis_name,
            "blockType": block.block_type,
            "text": block.text,
        }
        
        if block.arguments:
            block_data["arguments"] = {}
            for arg in block.arguments:
                arg_data = {
                    "type": arg.arg_type
                }
                if arg.default_value is not None:
                    arg_data["defaultValue"] = arg.default_value
                if arg.menu:
                    arg_data["menu"] = arg.menu
                block_data["arguments"][arg.name] = arg_data
        
        if block.is_terminal:
            block_data["isTerminal"] = True
        if block.hidden:
            block_data["hideFromPalette"] = True
            
        data["blocks"].append(block_data)
    
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2)


# Global extension loader instance
_global_loader: Optional[ExtensionLoader] = None


def get_extension_loader() -> ExtensionLoader:
    global _global_loader
    if _global_loader is None:
        _global_loader = ExtensionLoader()
        # Load extensions from standard locations
        ext_dir = os.path.join(os.path.dirname(__file__), "extensions")
        if os.path.exists(ext_dir):
            _global_loader.load_directory(ext_dir)
    return _global_loader


def reset_extension_loader():
    global _global_loader
    _global_loader = None
