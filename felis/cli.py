import argparse
import json
import os
import sys
import zipfile
from .compiler import FelisCompiler
from .linker import Linker
from .decompiler import decompile_sb3


# Safe print function that handles Unicode on Windows
def safe_print(msg):
    try:
        print(msg)
    except UnicodeEncodeError:
        # Strip ANSI codes and replace Unicode symbols with ASCII
        import re
        clean = re.sub(r'\033\[[0-9;]*m', '', msg)
        clean = clean.replace('\u25b6', '>').replace('\u2717', 'X').replace('\u2713', 'OK').replace('\u26a0', '!')
        print(clean)


def compile_cmd(args):
    from .extensions import ExtensionLoader
    import time as time_module
    
    try:
        start_time = time_module.perf_counter()
        
        # Link and parse
        safe_print(f"\033[1;36m▶\033[0m Compiling {args.input}...")
        linker = Linker()
        program = linker.link(args.input)
        
        link_time = time_module.perf_counter()
        
        # Load extensions if specified
        ext_loader = ExtensionLoader()
        extensions_list = getattr(args, 'extensions', None) or []
        for ext_path in extensions_list:
            print(f"  Loading extension: {ext_path}")
            ext_loader.load_from_file(ext_path)
        
        # Compile
        compiler = FelisCompiler(
            base_dir=os.path.dirname(os.path.abspath(args.input)),
            extension_loader=ext_loader
        )
        project_data = compiler.compile(program)
        
        compile_time = time_module.perf_counter()
        
        # Get compilation stats
        stats = compiler.get_compilation_stats()
        
        # Show warnings if any
        if stats["warnings"]:
            safe_print(f"\n\033[1;33m⚠ {stats['warning_count']} warning(s):\033[0m")
            for warning in stats["warnings"]:
                safe_print(f"  {warning}")
            print()
        
        # Write output
        output_path = args.output
        if not output_path.endswith(".sb3"):
            output_path += ".sb3"
            
        safe_print(f"\033[1;36m▶\033[0m Writing to {output_path}...")
        
        with zipfile.ZipFile(output_path, 'w', compression=zipfile.ZIP_DEFLATED) as zf:
            # Write project.json
            zf.writestr("project.json", json.dumps(project_data, indent=0))

            # Write referenced assets (costumes/backdrops/sounds)
            for md5ext, blob in compiler.asset_blobs.items():
                zf.writestr(md5ext, blob)
        
        end_time = time_module.perf_counter()
        
        # Show timing stats
        total_time = end_time - start_time
        safe_print(f"\n\033[1;32m✓ Done!\033[0m")
        print(f"  Linking:    {(link_time - start_time)*1000:.1f}ms")
        print(f"  Compiling:  {(compile_time - link_time)*1000:.1f}ms")
        print(f"  Writing:    {(end_time - compile_time)*1000:.1f}ms")
        print(f"  Total:      {total_time*1000:.1f}ms")
        print(f"  Blocks:     {stats['blocks_compiled']}")
        
    except Exception as e:
        safe_print(f"\033[1;31m✗ Error:\033[0m {e}")
        if args.debug:
            import traceback
            traceback.print_exc()
        sys.exit(1)


def decompile_cmd(args):
    try:
        print(f"Decompiling {args.input}...")
        
        # Determine output name (without extension)
        output_name = args.output
        if output_name:
            # Remove .felis extension if provided
            if output_name.endswith(".felis"):
                output_name = output_name[:-6]
        else:
            # Default to input name without .sb3
            output_name = os.path.splitext(os.path.basename(args.input))[0]
        
        # Create project directory structure
        project_dir = output_name
        os.makedirs(project_dir, exist_ok=True)
        
        # Output .felis file inside the project directory
        project_name = os.path.basename(output_name)
        output_path = os.path.join(project_dir, f"{project_name}.felis")
        
        # Assets go into the project directory
        output_dir = project_dir
        
        source = decompile_sb3(args.input, output_path, output_dir)
        
        print(f"Decompiled to {output_path}")
        print(f"Assets extracted to {output_dir}/costumes/ and {output_dir}/sounds/")
        print("Done!")
        
    except Exception as e:
        print(f"Error: {e}")
        if args.debug:
            import traceback
            traceback.print_exc()
        sys.exit(1)


def ext_convert_cmd(args):
    from .ext_converter import convert_extension, ExtensionConverter
    
    try:
        print(f"Converting extension {args.input}...")
        
        # Determine output path
        output_path = args.output
        if not output_path:
            base_name = os.path.splitext(os.path.basename(args.input))[0]
            output_path = base_name + ".felisx"
        
        if not output_path.endswith(".felisx"):
            output_path += ".felisx"
        
        # Get extension URL if provided
        extension_url = getattr(args, 'url', None)
        
        ext = convert_extension(args.input, output_path, extension_url)
        
        print(f"Extension ID: {ext.id}")
        print(f"Name: {ext.name}")
        print(f"Blocks: {len(ext.blocks)}")
        print(f"Menus: {len(ext.menus)}")
        if ext.extension_url:
            print(f"Extension URL: {ext.extension_url}")
        print(f"Output: {output_path}")
        print("Done!")
        
    except Exception as e:
        print(f"Error: {e}")
        if hasattr(args, 'debug') and args.debug:
            import traceback
            traceback.print_exc()
        sys.exit(1)


def ext_list_cmd(args):
    from .extensions import ExtensionLoader
    
    try:
        loader = ExtensionLoader()
        ext = loader.load_from_file(args.input)
        
        print(f"Extension: {ext.name} ({ext.id})")
        print(f"Version: {ext.version}")
        if ext.description:
            print(f"Description: {ext.description}")
        print(f"Color: {ext.color1}")
        print()
        
        print("Blocks:")
        for block in ext.blocks:
            if block.hidden:
                continue
            type_symbol = {
                "command": "⬛",
                "reporter": "⬭",
                "boolean": "◇",
                "hat": "⚑",
                "conditional": "↳",
                "loop": "↻",
            }.get(block.block_type, "?")
            
            print(f"  {type_symbol} {block.felis_name}")
            if block.text:
                print(f"      Text: {block.text}")
            if block.arguments:
                args_str = ", ".join(f"{a.name}: {a.arg_type}" for a in block.arguments)
                print(f"      Args: ({args_str})")
        
        if ext.menus:
            print()
            print("Menus:")
            for name, menu in ext.menus.items():
                items_preview = menu.items[:5]
                if len(menu.items) > 5:
                    items_preview.append("...")
                print(f"  {name}: {items_preview}")
        
    except Exception as e:
        print(f"Error: {e}")
        if args.debug:
            import traceback
            traceback.print_exc()
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(description="Felis Compiler and Decompiler")
    parser.add_argument("--debug", action="store_true", help="Enable debug output")
    
    subparsers = parser.add_subparsers(dest="command", help="Commands")
    
    # Compile command
    compile_parser = subparsers.add_parser("compile", aliases=["c"], help="Compile Felis to SB3")
    compile_parser.add_argument("input", help="Input Felis file (.felis)")
    compile_parser.add_argument("-o", "--output", help="Output SB3 file (.sb3)", default="project.sb3")
    compile_parser.add_argument("-e", "--extension", action="append", dest="extensions", help="Load a Felis extension (.felisx)")
    compile_parser.set_defaults(func=compile_cmd)
    
    # Decompile command
    decompile_parser = subparsers.add_parser("decompile", aliases=["d"], help="Decompile SB3 to Felis")
    decompile_parser.add_argument("input", help="Input SB3 file (.sb3)")
    decompile_parser.add_argument("-o", "--output", help="Output Felis file (.felis)")
    decompile_parser.add_argument("--assets-dir", dest="assets_dir", help="Directory for extracted assets (defaults to output file directory)")
    decompile_parser.set_defaults(func=decompile_cmd)
    
    # Extension convert command
    ext_convert_parser = subparsers.add_parser("ext-convert", aliases=["ec"], help="Convert Scratch/TurboWarp/PenguinMod extension to Felis format")
    ext_convert_parser.add_argument("input", help="Input JavaScript extension file (.js)")
    ext_convert_parser.add_argument("-o", "--output", help="Output Felis extension file (.felisx)")
    ext_convert_parser.add_argument("--url", help="URL where the extension is hosted (for auto-loading in TurboWarp/PenguinMod)")
    ext_convert_parser.set_defaults(func=ext_convert_cmd)
    
    # Extension list command  
    ext_list_parser = subparsers.add_parser("ext-list", aliases=["el"], help="List blocks in a Felis extension")
    ext_list_parser.add_argument("input", help="Input Felis extension file (.felisx)")
    ext_list_parser.set_defaults(func=ext_list_cmd)
    
    args = parser.parse_args()
    
    # Handle legacy usage (direct file argument without subcommand)
    if args.command is None:
        # Check if we have positional arguments that look like files
        if len(sys.argv) > 1 and not sys.argv[1].startswith('-'):
            input_file = sys.argv[1]
            if input_file.endswith('.felis'):
                # Legacy compile mode
                legacy_parser = argparse.ArgumentParser(description="Felis Compiler")
                legacy_parser.add_argument("input", help="Input Felis file (.felis)")
                legacy_parser.add_argument("-o", "--output", help="Output SB3 file (.sb3)", default="project.sb3")
                legacy_parser.add_argument("--debug", action="store_true", help="Enable debug output")
                args = legacy_parser.parse_args()
                compile_cmd(args)
                return
            elif input_file.endswith('.sb3'):
                # Auto-detect decompile mode
                legacy_parser = argparse.ArgumentParser(description="Felis Decompiler")
                legacy_parser.add_argument("input", help="Input SB3 file (.sb3)")
                legacy_parser.add_argument("-o", "--output", help="Output Felis file (.felis)")
                legacy_parser.add_argument("--assets-dir", dest="assets_dir", help="Directory for extracted assets")
                legacy_parser.add_argument("--debug", action="store_true", help="Enable debug output")
                args = legacy_parser.parse_args()
                decompile_cmd(args)
                return
        
        parser.print_help()
        sys.exit(1)
    
    args.func(args)


if __name__ == "__main__":
    main()
