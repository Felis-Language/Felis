import json
import re
import os
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass
from .extensions import (
    FelisExtension, ExtensionBlock, ExtensionArgument, ExtensionMenu, 
    export_extension
)


@dataclass
class ParsedExtension:
    id: str
    name: str
    description: str
    color1: str
    color2: Optional[str]
    color3: Optional[str]
    blocks: List[Dict[str, Any]]
    menus: Dict[str, Any]
    source_url: Optional[str] = None
    extension_url: Optional[str] = None


class ExtensionConverter:
    # Scratch block type constants
    BLOCK_TYPE_MAP = {
        "command": "command",
        "reporter": "reporter",
        "Boolean": "boolean",
        "hat": "hat",
        "conditional": "conditional",
        "loop": "loop",
        "button": "button",
        "label": "label",
        # Scratch.BlockType enums
        "Scratch.BlockType.COMMAND": "command",
        "Scratch.BlockType.REPORTER": "reporter",
        "Scratch.BlockType.BOOLEAN": "boolean",
        "Scratch.BlockType.HAT": "hat",
        "Scratch.BlockType.CONDITIONAL": "conditional",
        "Scratch.BlockType.LOOP": "loop",
        "Scratch.BlockType.BUTTON": "button",
        "Scratch.BlockType.LABEL": "label",
        "Scratch.BlockType.EVENT": "hat",
        # BlockType shorthand
        "BlockType.COMMAND": "command",
        "BlockType.REPORTER": "reporter",
        "BlockType.BOOLEAN": "boolean",
        "BlockType.HAT": "hat", 
        "BlockType.CONDITIONAL": "conditional",
        "BlockType.LOOP": "loop",
        "BlockType.BUTTON": "button",
        "BlockType.LABEL": "label",
        "BlockType.EVENT": "hat",
    }
    
    ARG_TYPE_MAP = {
        "number": "number",
        "string": "string",
        "boolean": "boolean",
        "angle": "angle",
        "color": "color",
        "note": "note",
        "matrix": "matrix",
        "image": "image",
        # Scratch.ArgumentType enums
        "Scratch.ArgumentType.NUMBER": "number",
        "Scratch.ArgumentType.STRING": "string",
        "Scratch.ArgumentType.BOOLEAN": "boolean",
        "Scratch.ArgumentType.ANGLE": "angle",
        "Scratch.ArgumentType.COLOR": "color",
        "Scratch.ArgumentType.NOTE": "note",
        "Scratch.ArgumentType.MATRIX": "matrix",
        "Scratch.ArgumentType.IMAGE": "image",
        # ArgumentType shorthand
        "ArgumentType.NUMBER": "number",
        "ArgumentType.STRING": "string",
        "ArgumentType.BOOLEAN": "boolean",
        "ArgumentType.ANGLE": "angle",
        "ArgumentType.COLOR": "color",
        "ArgumentType.NOTE": "note",
        "ArgumentType.MATRIX": "matrix",
        "ArgumentType.IMAGE": "image",
    }
    
    def __init__(self):
        self.source_file: Optional[str] = None
        self.extension_url: Optional[str] = None
    
    def convert_file(self, js_filepath: str, output_path: Optional[str] = None, 
                     extension_url: Optional[str] = None) -> FelisExtension:
        """Convert a JavaScript extension file to Felis extension.
        
        Args:
            js_filepath: Path to the JS extension file
            output_path: Optional path to save .felisx file
            extension_url: URL where the extension is hosted (for auto-loading)
        """
        self.source_file = js_filepath
        self.extension_url = extension_url
        
        with open(js_filepath, 'r', encoding='utf-8') as f:
            js_source = f.read()
        
        ext = self.convert_source(js_source, extension_url)
        
        if output_path:
            export_extension(ext, output_path)
            print(f"Exported extension to {output_path}")
        
        return ext
    
    def convert_source(self, js_source: str, extension_url: Optional[str] = None) -> FelisExtension:
        self.extension_url = extension_url
        parsed = self._parse_extension(js_source)
        return self._build_felis_extension(parsed)
    
    def _parse_extension(self, source: str) -> ParsedExtension:
        # Extract metadata from comments
        name = self._extract_comment_field(source, "Name") or "Unknown Extension"
        ext_id = self._extract_comment_field(source, "ID") or self._generate_id(name)
        description = self._extract_comment_field(source, "Description") or ""
        author = self._extract_comment_field(source, "By") or ""
        
        # Try to extract extension URL from comments or known patterns
        extension_url = self.extension_url  # Use provided URL if given
        if not extension_url:
            # Try common comment patterns for URL
            extension_url = (
                self._extract_comment_field(source, "URL") or
                self._extract_comment_field(source, "Extension URL") or
                self._extract_comment_field(source, "Original") or
                self._extract_url_from_source(source, ext_id)
            )
        
        # Find getInfo() method and extract its return value
        info = self._extract_get_info(source)
        
        if info:
            # Override with info from getInfo if available
            if "id" in info:
                ext_id = info["id"]
            if "name" in info:
                name = info["name"]
            if "description" in info:
                description = info.get("description", description)
        
        color1 = info.get("color1", "#0FBD8C") if info else "#0FBD8C"
        color2 = info.get("color2") if info else None
        color3 = info.get("color3") if info else None
        
        blocks = info.get("blocks", []) if info else []
        menus = info.get("menus", {}) if info else {}
        
        return ParsedExtension(
            id=ext_id,
            name=name,
            description=description,
            color1=color1,
            color2=color2,
            color3=color3,
            blocks=blocks,
            menus=menus,
            source_url=self.source_file,
            extension_url=extension_url
        )
    
    def _extract_comment_field(self, source: str, field: str) -> Optional[str]:
        pattern = rf'^//\s*{field}:\s*(.+)$'
        match = re.search(pattern, source, re.MULTILINE | re.IGNORECASE)
        if match:
            return match.group(1).strip()
        return None
    
    def _extract_url_from_source(self, source: str, ext_id: str) -> Optional[str]:
        url_patterns = [
            r'https?://extensions\.turbowarp\.org/[^\s\'"<>]+\.js',
            r'https?://extensions\.penguinmod\.com/[^\s\'"<>]+\.js',
            r'https?://[^\s\'"<>]+/extensions?/[^\s\'"<>]+\.js',
        ]
        for pattern in url_patterns:
            match = re.search(pattern, source)
            if match:
                return match.group(0)
        
        # If source file is from a known extension gallery, construct URL
        if self.source_file:
            filename = os.path.basename(self.source_file)
            # Common TurboWarp extension URL patterns
            if 'turbowarp' in self.source_file.lower():
                return f"https://extensions.turbowarp.org/{filename}"
        
        return None
    
    def _generate_id(self, name: str) -> str:
        words = re.sub(r'[^a-zA-Z0-9\s]', '', name).split()
        if not words:
            return "unknownExtension"
        result = words[0].lower()
        for word in words[1:]:
            result += word.capitalize()
        return result
    
    def _extract_get_info(self, source: str) -> Optional[Dict[str, Any]]:
        # First try to find extInfo pattern (used by TurboWarp extensions like simple3d)
        ext_info_match = re.search(r'(?:const|let|var)\s+extInfo\s*=\s*\{', source)
        if ext_info_match:
            obj_start = ext_info_match.end() - 1
            obj_str = self._extract_balanced_braces(source, obj_start)
            if obj_str:
                result = self._parse_js_object(obj_str, source)
                # Check if blocks is a reference to definitions
                if result.get("blocks") == [] or not result.get("blocks"):
                    # Try to find definitions array
                    defs_match = re.search(r'(?:const|let|var)\s+definitions\s*=\s*\[', source)
                    if defs_match:
                        defs_start = defs_match.end() - 1
                        defs_str = self._extract_balanced_brackets(source, defs_start)
                        if defs_str:
                            result["blocks"] = self._parse_blocks_array(defs_str, source)
                return result
        
        # Find the getInfo method and extract the return object
        get_info_start = -1
        patterns = [
            r'getInfo\s*\(\s*\)\s*\{',
            r'getInfo\s*=\s*\(\s*\)\s*=>\s*\{',
            r'getInfo\s*=\s*function\s*\(\s*\)\s*\{',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, source)
            if match:
                get_info_start = match.end()
                break
        
        if get_info_start == -1:
            return None
        
        # Check if it returns extInfo
        search_region = source[get_info_start:get_info_start + 2000]
        if re.search(r'return\s+extInfo\s*;?', search_region):
            # Already handled above
            return None
        
        # Find the return statement within getInfo
        return_match = re.search(r'return\s*(\{)', search_region)
        if not return_match:
            return None
        
        obj_start = get_info_start + return_match.start(1)
        obj_str = self._extract_balanced_braces(source, obj_start)
        
        if obj_str:
            return self._parse_js_object(obj_str, source)
        
        return None
    
    def _extract_info_object(self, source: str) -> Optional[str]:
        patterns = [
            r'return\s*\{',  # return { in getInfo
            r'extInfo\s*=\s*\{',  # const extInfo = {
            r'getInfo\s*\([^)]*\)\s*\{[^{]*return\s*\{',  # getInfo() { return {
        ]
        
        for pattern in patterns:
            match = re.search(pattern, source)
            if match:
                start = match.end() - 1  # Position of opening {
                obj_str = self._extract_balanced_braces(source, start)
                if obj_str:
                    return obj_str
        
        return None
    
    def _extract_balanced_braces(self, source: str, start: int) -> Optional[str]:
        if start >= len(source) or source[start] != '{':
            return None
        
        depth = 0
        in_string = False
        string_char = None
        i = start
        
        while i < len(source):
            c = source[i]
            
            # Handle strings
            if not in_string and c in '"\'`':
                in_string = True
                string_char = c
            elif in_string:
                if c == string_char and (i == 0 or source[i-1] != '\\'):
                    in_string = False
            elif c == '{':
                depth += 1
            elif c == '}':
                depth -= 1
                if depth == 0:
                    return source[start:i+1]
            
            i += 1
        
        return None
    
    def _parse_js_object(self, obj_source: str, full_source: str) -> Dict[str, Any]:
        result = {}
        
        # Extract id
        id_match = re.search(r'["\']?id["\']?\s*:\s*["\']([^"\']+)["\']', obj_source)
        if id_match:
            result["id"] = id_match.group(1)
        
        # Extract name
        name_match = re.search(r'["\']?name["\']?\s*:\s*["\']([^"\']+)["\']', obj_source)
        if name_match:
            result["name"] = name_match.group(1)
        
        # Extract colors
        for color in ["color1", "color2", "color3"]:
            color_match = re.search(rf'["\']?{color}["\']?\s*:\s*["\']([^"\']+)["\']', obj_source)
            if color_match:
                result[color] = color_match.group(1)
        
        # Extract blocks array
        blocks_match = re.search(r'["\']?blocks["\']?\s*:\s*\[', obj_source)
        if blocks_match:
            blocks_start = blocks_match.end() - 1
            blocks_str = self._extract_balanced_brackets(obj_source, blocks_start)
            if blocks_str:
                result["blocks"] = self._parse_blocks_array(blocks_str, full_source)
        
        # Extract menus
        menus_match = re.search(r'["\']?menus["\']?\s*:\s*\{', obj_source)
        if menus_match:
            menus_start = menus_match.end() - 1
            menus_str = self._extract_balanced_braces(obj_source, menus_start)
            if menus_str:
                result["menus"] = self._parse_menus_object(menus_str, full_source)
        
        return result
    
    def _extract_balanced_brackets(self, source: str, start: int) -> Optional[str]:
        if start >= len(source) or source[start] != '[':
            return None
        
        depth = 0
        in_string = False
        string_char = None
        i = start
        
        while i < len(source):
            c = source[i]
            
            if not in_string and c in '"\'`':
                in_string = True
                string_char = c
            elif in_string:
                if c == string_char and (i == 0 or source[i-1] != '\\'):
                    in_string = False
            elif c == '[':
                depth += 1
            elif c == ']':
                depth -= 1
                if depth == 0:
                    return source[start:i+1]
            
            i += 1
        
        return None
    
    def _parse_blocks_array(self, blocks_str: str, full_source: str) -> List[Dict[str, Any]]:
        blocks = []
        
        # Find each block object
        i = 1  # Skip opening [
        while i < len(blocks_str):
            # Skip whitespace
            while i < len(blocks_str) and blocks_str[i] in ' \t\n\r,':
                i += 1
            
            if i >= len(blocks_str) or blocks_str[i] == ']':
                break
            
            # Handle string separators like "---"
            if blocks_str[i] in '"\'':
                string_end = blocks_str.find(blocks_str[i], i + 1)
                if string_end != -1:
                    i = string_end + 1
                    continue
            
            if blocks_str[i] == '{':
                block_str = self._extract_balanced_braces(blocks_str, i)
                if block_str:
                    block = self._parse_block_object(block_str, full_source)
                    if block:
                        blocks.append(block)
                    i += len(block_str)
                else:
                    i += 1
            else:
                i += 1
        
        return blocks
    
    def _parse_block_object(self, block_str: str, full_source: str) -> Optional[Dict[str, Any]]:
        block = {}
        
        # Extract opcode
        opcode_match = re.search(r'["\']?opcode["\']?\s*:\s*["\']([^"\']+)["\']', block_str)
        if opcode_match:
            block["opcode"] = opcode_match.group(1)
        else:
            # Try to find func property as alternative
            func_match = re.search(r'["\']?func["\']?\s*:\s*["\']([^"\']+)["\']', block_str)
            if func_match:
                block["opcode"] = func_match.group(1)
            else:
                return None  # No opcode, skip this block
        
        # Extract blockType
        block_type_match = re.search(r'["\']?blockType["\']?\s*:\s*([^\s,}]+)', block_str)
        if block_type_match:
            bt_raw = block_type_match.group(1).strip('"\'')
            block["blockType"] = self.BLOCK_TYPE_MAP.get(bt_raw, bt_raw)
        else:
            block["blockType"] = "command"
        
        # Extract text
        text_match = re.search(r'["\']?text["\']?\s*:\s*["\']([^"\']*)["\']', block_str)
        if text_match:
            block["text"] = text_match.group(1)
        else:
            # Try template literal
            text_match2 = re.search(r'["\']?text["\']?\s*:\s*`([^`]*)`', block_str)
            if text_match2:
                block["text"] = text_match2.group(1)
        
        # Extract hideFromPalette
        if re.search(r'hideFromPalette\s*:\s*true', block_str):
            block["hideFromPalette"] = True
        
        # Extract isTerminal
        if re.search(r'isTerminal\s*:\s*true', block_str):
            block["isTerminal"] = True
        
        # Extract arguments
        args_match = re.search(r'["\']?arguments["\']?\s*:\s*\{', block_str)
        if args_match:
            args_start = args_match.end() - 1
            args_str = self._extract_balanced_braces(block_str, args_start)
            if args_str:
                block["arguments"] = self._parse_arguments(args_str)
        
        return block
    
    def _parse_arguments(self, args_str: str) -> Dict[str, Any]:
        arguments = {}
        
        # Find each argument
        # Pattern: ARGNAME: { type: ..., defaultValue: ... }
        arg_pattern = re.compile(r'([A-Z_][A-Z0-9_]*)\s*:\s*\{', re.IGNORECASE)
        
        for match in arg_pattern.finditer(args_str):
            arg_name = match.group(1)
            arg_start = match.end() - 1
            arg_obj = self._extract_balanced_braces(args_str, arg_start)
            
            if arg_obj:
                arg_data = {}
                
                # Extract type
                type_match = re.search(r'["\']?type["\']?\s*:\s*([^\s,}]+)', arg_obj)
                if type_match:
                    type_raw = type_match.group(1).strip('"\'')
                    arg_data["type"] = self.ARG_TYPE_MAP.get(type_raw, "string")
                
                # Extract defaultValue
                default_match = re.search(r'["\']?defaultValue["\']?\s*:\s*([^\s,}]+|"[^"]*"|\'[^\']*\')', arg_obj)
                if default_match:
                    default_val = default_match.group(1).strip('"\'')
                    # Try to parse as number
                    try:
                        if '.' in default_val:
                            arg_data["defaultValue"] = float(default_val)
                        else:
                            arg_data["defaultValue"] = int(default_val)
                    except ValueError:
                        if default_val.lower() == 'true':
                            arg_data["defaultValue"] = True
                        elif default_val.lower() == 'false':
                            arg_data["defaultValue"] = False
                        else:
                            arg_data["defaultValue"] = default_val
                
                # Extract menu
                menu_match = re.search(r'["\']?menu["\']?\s*:\s*["\']?([^"\'}\s,]+)["\']?', arg_obj)
                if menu_match:
                    arg_data["menu"] = menu_match.group(1)
                
                arguments[arg_name] = arg_data
        
        return arguments
    
    def _parse_menus_object(self, menus_str: str, full_source: str) -> Dict[str, Any]:
        menus = {}
        
        # Find each menu
        # Pattern: menuName: { items: [...] } or menuName: [...]
        menu_pattern = re.compile(r'([a-zA-Z_][a-zA-Z0-9_]*)\s*:\s*(\{|\[)', re.IGNORECASE)
        
        for match in menu_pattern.finditer(menus_str):
            menu_name = match.group(1)
            bracket = match.group(2)
            menu_start = match.end() - 1
            
            if bracket == '{':
                menu_obj = self._extract_balanced_braces(menus_str, menu_start)
                if menu_obj:
                    menu_data = {"acceptReporters": False, "items": []}
                    
                    # Check for acceptReporters
                    if re.search(r'acceptReporters\s*:\s*true', menu_obj):
                        menu_data["acceptReporters"] = True
                    
                    # Extract items array
                    items_match = re.search(r'["\']?items["\']?\s*:\s*\[', menu_obj)
                    if items_match:
                        items_start = items_match.end() - 1
                        items_str = self._extract_balanced_brackets(menu_obj, items_start)
                        if items_str:
                            menu_data["items"] = self._parse_menu_items(items_str)
                    
                    menus[menu_name] = menu_data
            
            elif bracket == '[':
                menu_arr = self._extract_balanced_brackets(menus_str, menu_start)
                if menu_arr:
                    menus[menu_name] = self._parse_menu_items(menu_arr)
        
        return menus
    
    def _parse_menu_items(self, items_str: str) -> List[Any]:
        items = []
        
        # Remove brackets
        inner = items_str.strip()[1:-1]
        
        # Split by commas (being careful about nested structures)
        current = ""
        depth = 0
        in_string = False
        string_char = None
        
        for c in inner:
            if not in_string and c in '"\'`':
                in_string = True
                string_char = c
                current += c
            elif in_string:
                current += c
                if c == string_char:
                    in_string = False
            elif c in '{[':
                depth += 1
                current += c
            elif c in '}]':
                depth -= 1
                current += c
            elif c == ',' and depth == 0:
                item = current.strip()
                if item:
                    parsed_item = self._parse_menu_item(item)
                    if parsed_item is not None:
                        items.append(parsed_item)
                current = ""
            else:
                current += c
        
        # Don't forget the last item
        item = current.strip()
        if item:
            parsed_item = self._parse_menu_item(item)
            if parsed_item is not None:
                items.append(parsed_item)
        
        return items
    
    def _parse_menu_item(self, item_str: str) -> Any:
        item_str = item_str.strip()
        
        if not item_str:
            return None
        
        # String item
        if item_str[0] in '"\'`':
            return item_str.strip('"\'`')
        
        # Object item {text: ..., value: ...}
        if item_str.startswith('{'):
            text_match = re.search(r'["\']?text["\']?\s*:\s*["\']([^"\']*)["\']', item_str)
            value_match = re.search(r'["\']?value["\']?\s*:\s*["\']([^"\']*)["\']', item_str)
            
            if text_match and value_match:
                return {"text": text_match.group(1), "value": value_match.group(1)}
            elif text_match:
                return text_match.group(1)
            elif value_match:
                return value_match.group(1)
        
        # Plain identifier (probably a variable reference)
        return item_str
    
    def _build_felis_extension(self, parsed: ParsedExtension) -> FelisExtension:
        menus = {}
        for menu_name, menu_data in parsed.menus.items():
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
        
        # Convert blocks
        blocks = []
        for block_data in parsed.blocks:
            if block_data.get("blockType") in ("label", "button"):
                continue
            
            opcode = block_data.get("opcode", "")
            if not opcode:
                continue
            
            # Build arguments
            arguments = []
            for arg_name, arg_data in block_data.get("arguments", {}).items():
                if isinstance(arg_data, dict):
                    arguments.append(ExtensionArgument(
                        name=arg_name,
                        arg_type=arg_data.get("type", "string"),
                        default_value=arg_data.get("defaultValue"),
                        menu=arg_data.get("menu")
                    ))
            
            # Generate Felis name
            felis_name = f"{parsed.id}.{self._to_snake_case(opcode)}"
            
            # Full opcode (with extension prefix)
            full_opcode = f"{parsed.id}_{opcode}" if not opcode.startswith(parsed.id) else opcode
            
            blocks.append(ExtensionBlock(
                opcode=full_opcode,
                felis_name=felis_name,
                block_type=block_data.get("blockType", "command"),
                text=block_data.get("text", ""),
                arguments=arguments,
                is_terminal=block_data.get("isTerminal", False),
                hidden=block_data.get("hideFromPalette", False)
            ))
        
        return FelisExtension(
            id=parsed.id,
            name=parsed.name,
            description=parsed.description,
            color1=parsed.color1,
            color2=parsed.color2,
            color3=parsed.color3,
            blocks=blocks,
            menus=menus,
            extension_url=parsed.extension_url,
            scratch_url=parsed.source_url
        )
    
    def _to_snake_case(self, name: str) -> str:
        s1 = re.sub('(.)([A-Z][a-z]+)', r'\1_\2', name)
        return re.sub('([a-z0-9])([A-Z])', r'\1_\2', s1).lower()


def convert_extension(js_filepath: str, output_path: Optional[str] = None, 
                      extension_url: Optional[str] = None) -> FelisExtension:
    converter = ExtensionConverter()
    return converter.convert_file(js_filepath, output_path, extension_url)


def convert_extension_source(js_source: str, extension_url: Optional[str] = None) -> FelisExtension:
    converter = ExtensionConverter()
    return converter.convert_source(js_source, extension_url)
