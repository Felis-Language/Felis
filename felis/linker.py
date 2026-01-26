import os
from typing import Dict, List, Optional, Set
from .ast_nodes import *
from .parser import parse


class LinkerError(Exception):
    def __init__(self, message: str, filename: str = None):
        self.message = message
        self.filename = filename
        super().__init__(f"Linker error in {filename}: {message}" if filename else f"Linker error: {message}")


class Linker:
    def __init__(self, base_path: str = "."):
        self.base_path = base_path
        self.loaded_libraries: Dict[str, Program] = {}
        self.processing: Set[str] = set()
        
    def link(self, entry_file: str) -> Program:
        if not os.path.exists(entry_file):
            raise LinkerError(f"File not found: {entry_file}")
            
        with open(entry_file, 'r', encoding='utf-8') as f:
            source = f.read()
            
        program = parse(source, entry_file)
        self.resolve_imports(program, os.path.dirname(os.path.abspath(entry_file)))
        
        # Optimize: Only include used blocks
        self.optimize_and_merge(program)
        
        return program
    
    def resolve_imports(self, program: Program, current_dir: str):
        for import_stmt in program.imports:
            lib_path = import_stmt.library_path
            
            # Resolve path
            if not os.path.isabs(lib_path):
                full_path = os.path.join(current_dir, lib_path)
                # Try adding .felis extension
                if not os.path.exists(full_path) and os.path.exists(full_path + ".felis"):
                    full_path += ".felis"
            else:
                full_path = lib_path
                
            if not os.path.exists(full_path):
                # Try looking in standard library path
                std_path = os.path.join(os.path.dirname(__file__), "stdlib", lib_path)
                if os.path.exists(std_path + ".felis"):
                    full_path = std_path + ".felis"
                else:
                    # Try looking in libs path (SDK and other libraries)
                    libs_path = os.path.join(os.path.dirname(__file__), "libs", lib_path)
                    if os.path.exists(libs_path + ".felis"):
                        full_path = libs_path + ".felis"
                    else:
                        raise LinkerError(f"Library not found: {lib_path}", program.position.filename if program.position else None)
            
            # Check for circular dependency
            abs_path = os.path.abspath(full_path)
            if abs_path in self.processing:
                raise LinkerError(f"Circular dependency detected: {lib_path}")
            
            if abs_path in self.loaded_libraries:
                lib_program = self.loaded_libraries[abs_path]
            else:
                self.processing.add(abs_path)
                with open(abs_path, 'r', encoding='utf-8') as f:
                    lib_source = f.read()
                
                lib_program = parse(lib_source, abs_path)
                self.resolve_imports(lib_program, os.path.dirname(abs_path))
                self.loaded_libraries[abs_path] = lib_program
                self.processing.remove(abs_path)
            
            # Do NOT merge here. We merge later based on usage.

    def optimize_and_merge(self, program: Program):
        # symbol table: name -> (library_path, CustomBlock)
        block_symbol_table = {}
        var_symbol_table = {}
        list_symbol_table = {}

        for lib_path, lib_prog in self.loaded_libraries.items():
            if lib_prog.stage:
                for cb in lib_prog.stage.custom_blocks:
                    block_symbol_table[cb.name] = (lib_path, cb)
                for var in lib_prog.stage.variables:
                    var_symbol_table[var.name] = (lib_path, var)
                for lst in lib_prog.stage.lists:
                    list_symbol_table[lst.name] = (lib_path, lst)
        
        # Scan roots (event handlers and custom blocks)
        block_queue = []
        visited_blocks = set()
        
        used_vars = set()
        used_lists = set()
        
        def scan_block(statements):
            for stmt in statements:
                if isinstance(stmt, BlockCall):
                    if stmt.block_name not in visited_blocks:
                        block_queue.append(stmt.block_name)
                elif isinstance(stmt, FunctionCall):
                    if stmt.func_name not in visited_blocks:
                        block_queue.append(stmt.func_name)
                elif isinstance(stmt, SetVariable):
                    used_vars.add(stmt.var_name)
                    scan_expression(stmt.value)
                elif isinstance(stmt, ChangeVariable):
                    used_vars.add(stmt.var_name)
                    scan_expression(stmt.value)
                elif isinstance(stmt, (ShowVariable, HideVariable)):
                    used_vars.add(stmt.var_name)
                elif isinstance(stmt, ListOperation):
                    used_lists.add(stmt.list_name)
                    if stmt.value: scan_expression(stmt.value)
                    if stmt.index: scan_expression(stmt.index)
                elif isinstance(stmt, (ShowList, HideList)):
                    used_lists.add(stmt.list_name)
                elif isinstance(stmt, VariableDecl):
                    if stmt.initial_value:
                        scan_expression(stmt.initial_value)
                
                # Recurse into children
                if hasattr(stmt, 'body') and stmt.body:
                    scan_block(stmt.body)
                if hasattr(stmt, 'then_body') and stmt.then_body:
                    scan_block(stmt.then_body)
                if hasattr(stmt, 'else_body') and stmt.else_body:
                    scan_block(stmt.else_body)
                
                # Check args
                if hasattr(stmt, 'args'):
                    for arg in stmt.args:
                        scan_expression(arg)
                if hasattr(stmt, 'condition'):
                    scan_expression(stmt.condition)
                if hasattr(stmt, 'value') and not isinstance(stmt, (SetVariable, ChangeVariable, ListOperation)):
                    scan_expression(stmt.value)
                if hasattr(stmt, 'duration'):
                    scan_expression(stmt.duration)

        def scan_expression(expr):
            if isinstance(expr, FunctionCall):
                if expr.func_name not in visited_blocks:
                    block_queue.append(expr.func_name)
            elif isinstance(expr, BlockCall): 
                if expr.block_name not in visited_blocks:
                    block_queue.append(expr.block_name)
            elif isinstance(expr, VariableRef):
                used_vars.add(expr.name)
            elif isinstance(expr, ListRef):
                used_lists.add(expr.name)
            elif isinstance(expr, (ListItemAccess, ListLength, ListContains, ListIndexOf)):
                used_lists.add(expr.list_name)
            
            # Recurse
            if hasattr(expr, 'args'):
                for arg in expr.args:
                    scan_expression(arg)
            if hasattr(expr, 'left'):
                scan_expression(expr.left)
            if hasattr(expr, 'right'):
                scan_expression(expr.right)
            if hasattr(expr, 'operand'):
                scan_expression(expr.operand)
            if hasattr(expr, 'item'):
                scan_expression(expr.item)
            if hasattr(expr, 'index'):
                scan_expression(expr.index)

        if program.stage:
            for handler in program.stage.event_handlers:
                scan_block(handler.body)
            for cb in program.stage.custom_blocks:
                scan_block(cb.body)
                
        for sprite in program.sprites:
            for handler in sprite.event_handlers:
                scan_block(handler.body)
            for cb in sprite.custom_blocks:
                scan_block(cb.body)

        # reachability analysis
        used_blocks = []
        
        while block_queue:
            name = block_queue.pop(0)
            if name in visited_blocks:
                continue
            
            visited_blocks.add(name)
            
            if name in block_symbol_table:
                lib_path, cb = block_symbol_table[name]
                used_blocks.append((lib_path, cb))
                # Scan the body of this block for more dependencies
                scan_block(cb.body)
        
        # merge
        if not program.stage:
            program.stage = Stage()

        for _, cb in used_blocks:
            program.stage.custom_blocks.append(cb)
            for sprite in program.sprites:
                sprite.custom_blocks.append(cb)

        # Merge used variables
        for var_name in used_vars:
            if var_name in var_symbol_table:
                lib_path, var = var_symbol_table[var_name]
                if not any(v.name == var.name for v in program.stage.variables):
                    program.stage.variables.append(var)
            # Also check list symbol table because parser might have confused them
            if var_name in list_symbol_table:
                lib_path, lst = list_symbol_table[var_name]
                if not any(l.name == lst.name for l in program.stage.lists):
                    program.stage.lists.append(lst)

        # Merge used lists
        for list_name in used_lists:
            if list_name in list_symbol_table:
                lib_path, lst = list_symbol_table[list_name]
                # Check if list already exists
                existing_idx = None
                for idx, l in enumerate(program.stage.lists):
                    if l.name == lst.name:
                        existing_idx = idx
                        break
                
                if existing_idx is not None:
                    # REPLACE with library version to ensure same object
                    program.stage.lists[existing_idx] = lst
                else:
                    program.stage.lists.append(lst)

    def merge_library(self, target: Program, library: Program, import_stmt: ImportStatement):
        # deprecated
        pass
