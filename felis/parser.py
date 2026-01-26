# Recursive descent parser for Felis

from typing import List, Optional, Any, Callable
from .lexer import Token, TokenType, Lexer
from .ast_nodes import *


class ParseError(Exception):
    def __init__(self, message: str, token: Token, source: str = None, suggestion: str = None):
        self.message = message
        self.token = token
        self.source = source
        self.suggestion = suggestion
        super().__init__(self._fmt())
    
    def _fmt(self) -> str:
        out = [f"\n\033[1;31mParse Error\033[0m at {self.token.line}:{self.token.column}"]
        out.append(f"  {self.message}")
        out.append(f"  Got: {self.token.type.name}" + (f" ('{self.token.value}')" if self.token.value else ""))
        
        if self.source:
            src = self.source.split('\n')
            if 0 < self.token.line <= len(src):
                start = max(0, self.token.line - 2)
                end = min(len(src), self.token.line + 1)
                out.append("")
                for i in range(start, end):
                    ln = i + 1
                    pfx = "\033[1;31m>\033[0m " if ln == self.token.line else "  "
                    out.append(f"{pfx}{ln:4d} | {src[i]}")
                    if ln == self.token.line:
                        out.append(" " * (7 + self.token.column - 1) + "\033[1;31m^\033[0m")
        
        if self.suggestion:
            out.append(f"\n\033[1;33mHint:\033[0m {self.suggestion}")
        
        return "\n".join(out)


class Parser:
    # Grammar (roughly):
    #   program      -> (import | library | export | sprite | stage)*
    #   sprite/stage -> costumes, sounds, vars, lists, define blocks, event handlers
    #   expression   -> standard precedence (or > and > comparison > add > mul > unary > power > call)
    
    def __init__(self, tokens: List[Token], filename: str = "<input>"):
        self.tokens = tokens
        self.filename = filename
        self.pos = 0
        
    def current(self) -> Token:
        return self.tokens[self.pos]
    
    def peek(self, offset: int = 1) -> Token:
        pos = self.pos + offset
        if pos >= len(self.tokens):
            return self.tokens[-1]
        return self.tokens[pos]
    
    def is_at_end(self) -> bool:
        return self.current().type == TokenType.EOF
    
    def check(self, *types: TokenType) -> bool:
        return not self.is_at_end() and self.current().type in types
    
    def match(self, *types: TokenType) -> Optional[Token]:
        if self.check(*types):
            return self.advance()
        return None
    
    def advance(self) -> Token:
        tok = self.current()
        if not self.is_at_end():
            self.pos += 1
        return tok
    
    def expect(self, token_type: TokenType, msg: str) -> Token:
        if self.check(token_type):
            return self.advance()
        raise ParseError(msg, self.current())
    
    def expect_ident_or_kw(self, msg: str) -> Token:
        """Accept identifier or certain keywords that can be used as names."""
        if self.check(TokenType.IDENTIFIER):
            return self.advance()
        
        # keywords that double as valid block/var names
        ok = [TokenType.ROUND, TokenType.ABS, TokenType.FLOOR, TokenType.CEIL,
              TokenType.SQRT, TokenType.SIN, TokenType.COS, TokenType.TAN,
              TokenType.ASIN, TokenType.ACOS, TokenType.ATAN, TokenType.LN,
              TokenType.LOG, TokenType.ANTILN, TokenType.ANTILOG,
              TokenType.LENGTH, TokenType.LETTER, TokenType.CONTAINS, 
              TokenType.JOIN, TokenType.RANDOM, TokenType.START, TokenType.STOP,
              TokenType.WAIT, TokenType.TIMER, TokenType.SIZE, TokenType.VOLUME,
              TokenType.LOUDNESS, TokenType.KEY, TokenType.FLAG, TokenType.CLONE,
              TokenType.MESSAGE, TokenType.BACKDROP, TokenType.PITCH, TokenType.PAN]
        
        if self.current().type in ok:
            return self.advance()
        raise ParseError(msg, self.current())

    def skip_newlines(self) -> List[str]:
        """Skip newlines and comments, returning any regular comments found.
        
        EXCLUDED_COMMENT tokens are skipped but not collected (they don't appear in Scratch).
        """
        comments = []
        while self.match(TokenType.NEWLINE, TokenType.COMMENT, TokenType.EXCLUDED_COMMENT):
            if self.tokens[self.pos - 1].type == TokenType.COMMENT:
                comments.append(self.tokens[self.pos - 1].value)
            # EXCLUDED_COMMENT is silently skipped
        return comments
    
    def collect_preceding_comments(self) -> List[str]:
        """Collect any comment tokens that appear before the current position (standalone comments).
        
        Only COMMENT tokens are collected. EXCLUDED_COMMENT tokens are skipped.
        """
        comments = []
        while self.check(TokenType.COMMENT) or self.check(TokenType.EXCLUDED_COMMENT):
            token = self.advance()
            if token.type == TokenType.COMMENT:
                comments.append(token.value)
            # EXCLUDED_COMMENT is silently skipped
            # Skip newlines after the comment
            while self.match(TokenType.NEWLINE):
                pass
        return comments
    
    def collect_inline_comment(self) -> Optional[str]:
        """Collect a comment that appears on the same line (after a statement).
        
        Only COMMENT tokens are collected. EXCLUDED_COMMENT tokens are skipped.
        """
        # Skip any excluded comments first
        while self.check(TokenType.EXCLUDED_COMMENT):
            self.advance()
        if self.check(TokenType.COMMENT):
            return self.advance().value
        return None
    
    def make_pos(self, token: Token) -> Position:
        return Position(line=token.line, column=token.column, filename=self.filename)
    
    # --- top level ---
    
    def parse(self) -> Program:
        prog = Program()
        self.skip_newlines()
        
        while not self.is_at_end():
            # Collect preceding comments for top-level items
            preceding_comments = self.collect_preceding_comments()
            self.skip_newlines()
            more_comments = self.collect_preceding_comments()
            preceding_comments.extend(more_comments)
            
            if self.check(TokenType.IMPORT):
                prog.imports.append(self.parse_import())
            elif self.check(TokenType.LIBRARY):
                lib = self.parse_library_decl()
                prog.is_library = True
                prog.library_name = lib.name
            elif self.check(TokenType.EXPORT):
                prog.exports.append(self.parse_export())
            elif self.check(TokenType.SPRITE):
                prog.sprites.append(self.parse_sprite())
            elif self.check(TokenType.STAGE):
                # merge with existing stage if there is one (for top-level vars)
                old_vars, old_lists, old_blocks = [], [], []
                if prog.stage:
                    old_vars = prog.stage.variables[:]
                    old_lists = prog.stage.lists[:]
                    old_blocks = prog.stage.custom_blocks[:]
                
                prog.stage = self.parse_stage()
                prog.stage.variables = old_vars + prog.stage.variables
                prog.stage.lists = old_lists + prog.stage.lists
                prog.stage.custom_blocks = old_blocks + prog.stage.custom_blocks
            elif self.check(TokenType.DEFINE):
                if not prog.stage:
                    prog.stage = Stage()
                cb = self.parse_custom_block()
                if preceding_comments:
                    cb.preceding_comments = preceding_comments
                prog.stage.custom_blocks.append(cb)
            elif self.check(TokenType.VAR) or self.check(TokenType.CLOUD):
                if not prog.stage:
                    prog.stage = Stage()
                prog.stage.variables.append(self.parse_var_decl())
            elif self.check(TokenType.LIST):
                if not prog.stage:
                    prog.stage = Stage()
                prog.stage.lists.append(self.parse_list_decl())
            elif self.is_at_end():
                break
            else:
                raise ParseError(f"Unexpected: {self.current().type.name}", self.current())
            
            self.skip_newlines()
        
        return prog
    
    def parse_import(self) -> ImportStatement:
        tok = self.expect(TokenType.IMPORT, "Expected 'import'")
        pos = self.make_pos(tok)
        
        if self.check(TokenType.STRING):
            path = self.advance().value
            alias = self.expect(TokenType.IDENTIFIER, "Expected alias").value if self.match(TokenType.AS) else None
            return ImportStatement(library_path=path, alias=alias, position=pos)
        
        raise ParseError("Expected library path", self.current())
    
    def parse_export(self) -> ExportStatement:
        tok = self.expect(TokenType.EXPORT, "Expected 'export'")
        pos = self.make_pos(tok)
        
        items = [self.expect_ident_or_kw("Expected identifier").value]
        while self.match(TokenType.COMMA):
            items.append(self.expect_ident_or_kw("Expected identifier").value)
        
        return ExportStatement(items=items, position=pos)
    
    def parse_library_decl(self) -> LibraryDecl:
        tok = self.expect(TokenType.LIBRARY, "Expected 'library'")
        name = self.expect(TokenType.IDENTIFIER, "Expected library name").value
        return LibraryDecl(name=name, position=self.make_pos(tok))
    
    # --- sprite/stage ---
    
    def parse_sprite(self) -> Sprite:
        tok = self.expect(TokenType.SPRITE, "Expected 'sprite'")
        pos = self.make_pos(tok)
        
        name = self.expect(TokenType.IDENTIFIER, "Expected sprite name").value
        
        sprite = Sprite(name=name, position=pos)
        
        # Optional properties before the body
        while self.match(TokenType.AT):
            # Property name can be an identifier or certain keywords like 'size'
            if self.check(TokenType.IDENTIFIER):
                prop_name = self.advance().value
            elif self.check(TokenType.SIZE):
                prop_name = self.advance().value
            elif self.check(TokenType.KEY):
                prop_name = self.advance().value
            else:
                raise ParseError("Expected property name", self.current())
            self.expect(TokenType.ASSIGN, "Expected '='")
            
            if prop_name == "x":
                sprite.x = self.parse_number_value()
            elif prop_name == "y":
                sprite.y = self.parse_number_value()
            elif prop_name == "size":
                sprite.size = self.parse_number_value()
            elif prop_name == "direction":
                sprite.direction = self.parse_number_value()
            elif prop_name == "visible":
                sprite.visible = self.match(TokenType.BOOLEAN).value
            elif prop_name == "rotation":
                sprite.rotation_style = self.expect(TokenType.STRING, "Expected rotation style").value
            elif prop_name == "name":
                sprite.display_name = self.expect(TokenType.STRING, "Expected display name string").value
        
        # Skip only newlines, not comments
        while self.match(TokenType.NEWLINE):
            pass
        self.expect(TokenType.LBRACE, "Expected '{' after sprite name")
        # Don't skip newlines/comments here - let parse_sprite_body handle it
        
        self.parse_sprite_body(sprite)
        
        self.expect(TokenType.RBRACE, "Expected '}'")
        
        return sprite
    
    def parse_stage(self) -> Stage:
        token = self.expect(TokenType.STAGE, "Expected 'stage'")
        pos = self.make_pos(token)
        
        stage = Stage(position=pos)
        
        # Skip only newlines, not comments
        while self.match(TokenType.NEWLINE):
            pass
        self.expect(TokenType.LBRACE, "Expected '{' after 'stage'")
        # Don't skip newlines/comments here - let parse_stage_body handle it
        
        self.parse_stage_body(stage)
        
        self.expect(TokenType.RBRACE, "Expected '}'")
        
        return stage
    
    def parse_sprite_body(self, sprite: Sprite):
        while not self.check(TokenType.RBRACE) and not self.is_at_end():
            # Skip only newlines
            while self.match(TokenType.NEWLINE):
                pass
            
            if self.check(TokenType.RBRACE):
                break
            
            # Collect preceding comments for items inside sprite
            preceding_comments = []
            while True:
                while self.match(TokenType.NEWLINE):
                    pass
                # Skip excluded comments, only collect regular comments
                if self.check(TokenType.EXCLUDED_COMMENT):
                    self.advance()  # skip excluded comment
                elif self.check(TokenType.COMMENT):
                    preceding_comments.append(self.advance().value)
                else:
                    break
            
            if self.check(TokenType.RBRACE):
                break
            
            if self.check(TokenType.COSTUMES):
                sprite.costumes.extend(self.parse_costumes())
            elif self.check(TokenType.SOUNDS):
                sprite.sounds.extend(self.parse_sounds())
            elif self.check(TokenType.VAR) or self.check(TokenType.CLOUD):
                sprite.variables.append(self.parse_var_decl())
            elif self.check(TokenType.LIST):
                sprite.lists.append(self.parse_list_decl())
            elif self.check(TokenType.DEFINE):
                cb = self.parse_custom_block()
                if preceding_comments:
                    cb.preceding_comments = preceding_comments
                sprite.custom_blocks.append(cb)
            elif self.check(TokenType.ON):
                handler = self.parse_event_handler()
                if preceding_comments:
                    handler.preceding_comments = preceding_comments
                sprite.event_handlers.append(handler)
            else:
                raise ParseError(f"Unexpected in sprite: {self.current().type.name}", self.current())
            
            # Skip only newlines
            while self.match(TokenType.NEWLINE):
                pass
    
    def parse_stage_body(self, stage: Stage):
        while not self.check(TokenType.RBRACE) and not self.is_at_end():
            # Skip only newlines
            while self.match(TokenType.NEWLINE):
                pass
            
            if self.check(TokenType.RBRACE):
                break
            
            # Collect preceding comments for items inside stage
            preceding_comments = []
            while True:
                while self.match(TokenType.NEWLINE):
                    pass
                # Skip excluded comments, only collect regular comments
                if self.check(TokenType.EXCLUDED_COMMENT):
                    self.advance()  # skip excluded comment
                elif self.check(TokenType.COMMENT):
                    preceding_comments.append(self.advance().value)
                else:
                    break
            
            if self.check(TokenType.RBRACE):
                break
            
            if self.check(TokenType.COSTUMES):
                stage.backdrops.extend(self.parse_costumes())
            elif self.check(TokenType.SOUNDS):
                stage.sounds.extend(self.parse_sounds())
            elif self.check(TokenType.VAR) or self.check(TokenType.CLOUD):
                stage.variables.append(self.parse_var_decl())
            elif self.check(TokenType.LIST):
                stage.lists.append(self.parse_list_decl())
            elif self.check(TokenType.DEFINE):
                cb = self.parse_custom_block()
                if preceding_comments:
                    cb.preceding_comments = preceding_comments
                stage.custom_blocks.append(cb)
            elif self.check(TokenType.ON):
                handler = self.parse_event_handler()
                if preceding_comments:
                    handler.preceding_comments = preceding_comments
                stage.event_handlers.append(handler)
            else:
                raise ParseError(f"Unexpected in stage: {self.current().type.name}", self.current())
            
            # Skip only newlines
            while self.match(TokenType.NEWLINE):
                pass
    
    # --- assets ---
    
    def parse_costumes(self) -> List[Costume]:
        self.expect(TokenType.COSTUMES, "Expected 'costumes'")
        self.skip_newlines()
        self.expect(TokenType.LBRACE, "Expected '{'")
        self.skip_newlines()
        
        costumes = []
        while not self.check(TokenType.RBRACE) and not self.is_at_end():
            name_tok = self.expect(TokenType.IDENTIFIER, "Expected costume name")
            name = name_tok.value
            pos = self.make_pos(name_tok)
            
            file = None
            if self.match(TokenType.COLON):
                file = self.expect(TokenType.STRING, "Expected file path").value
            
            costumes.append(Costume(name=name, file=file, position=pos))
            
            self.skip_newlines()
            self.match(TokenType.COMMA)
            self.skip_newlines()
        
        self.expect(TokenType.RBRACE, "Expected '}'")
        return costumes
    
    def parse_sounds(self) -> List[Sound]:
        self.expect(TokenType.SOUNDS, "Expected 'sounds'")
        self.skip_newlines()
        self.expect(TokenType.LBRACE, "Expected '{'")
        self.skip_newlines()
        
        sounds = []
        while not self.check(TokenType.RBRACE) and not self.is_at_end():
            name_tok = self.expect(TokenType.IDENTIFIER, "Expected sound name")
            name = name_tok.value
            pos = self.make_pos(name_tok)
            
            file = None
            if self.match(TokenType.COLON):
                file = self.expect(TokenType.STRING, "Expected file path").value
            
            sounds.append(Sound(name=name, file=file, position=pos))
            
            self.skip_newlines()
            self.match(TokenType.COMMA)
            self.skip_newlines()
        
        self.expect(TokenType.RBRACE, "Expected '}'")
        return sounds
    
    # --- vars/lists ---
    
    def parse_var_decl(self) -> VariableDecl:
        is_cloud = bool(self.match(TokenType.CLOUD))
        
        token = self.expect(TokenType.VAR, "Expected 'var'")
        pos = self.make_pos(token)
        
        name = self.expect_ident_or_kw("Expected var name").value
        
        # Check for @name attribute
        display_name = None
        if self.match(TokenType.AT):
            attr_name = self.expect(TokenType.IDENTIFIER, "Expected attribute name").value
            if attr_name == "name":
                self.expect(TokenType.ASSIGN, "Expected '='")
                display_name = self.expect(TokenType.STRING, "Expected display name string").value
        
        initial_value = 0
        if self.match(TokenType.ASSIGN):
            initial_value = self.parse_expression()
        
        return VariableDecl(name=name, display_name=display_name, initial_value=initial_value, is_cloud=is_cloud, position=pos)
    
    def parse_list_decl(self) -> ListDecl:
        token = self.expect(TokenType.LIST, "Expected 'list'")
        pos = self.make_pos(token)
        
        name = self.expect(TokenType.IDENTIFIER, "Expected list name").value
        
        # Check for @name attribute
        display_name = None
        if self.match(TokenType.AT):
            attr_name = self.expect(TokenType.IDENTIFIER, "Expected attribute name").value
            if attr_name == "name":
                self.expect(TokenType.ASSIGN, "Expected '='")
                display_name = self.expect(TokenType.STRING, "Expected display name string").value
        
        initial_values = []
        if self.match(TokenType.ASSIGN):
            self.expect(TokenType.LBRACKET, "Expected '['")
            self.skip_newlines()
            
            if not self.check(TokenType.RBRACKET):
                initial_values.append(self.parse_expression())
                self.skip_newlines()
                while self.match(TokenType.COMMA):
                    self.skip_newlines()
                    initial_values.append(self.parse_expression())
                    self.skip_newlines()
            
            self.expect(TokenType.RBRACKET, "Expected ']'")
        
        return ListDecl(name=name, display_name=display_name, initial_values=initial_values, position=pos)
    
    def parse_literal_value(self) -> Any:
        if self.check(TokenType.NUMBER):
            return self.advance().value
        elif self.check(TokenType.STRING):
            return self.advance().value
        elif self.check(TokenType.BOOLEAN):
            return self.advance().value
        elif self.match(TokenType.MINUS):
            return -self.expect(TokenType.NUMBER, "Expected number").value
        else:
            raise ParseError("Expected literal", self.current())
    
    def parse_number_value(self) -> float:
        if self.match(TokenType.MINUS):
            return -self.expect(TokenType.NUMBER, "Expected number").value
        return self.expect(TokenType.NUMBER, "Expected number").value
    
    # --- custom blocks ---
    
    def parse_custom_block(self) -> CustomBlock:
        token = self.expect(TokenType.DEFINE, "Expected 'define'")
        pos = self.make_pos(token)
        
        warp = bool(self.match(TokenType.WARP))
        
        name = self.expect_ident_or_kw("Expected block name").value
        
        # Check for @name attribute
        display_name = None
        if self.match(TokenType.AT):
            attr_name = self.expect(TokenType.IDENTIFIER, "Expected attribute name").value
            if attr_name == "name":
                self.expect(TokenType.ASSIGN, "Expected '='")
                display_name = self.expect(TokenType.STRING, "Expected display name string").value
        
        params = []
        if self.match(TokenType.LPAREN):
            self.skip_newlines()
            if not self.check(TokenType.RPAREN):
                params.append(self.parse_custom_block_param())
                self.skip_newlines()
                while self.match(TokenType.COMMA):
                    self.skip_newlines()
                    params.append(self.parse_custom_block_param())
                    self.skip_newlines()
            self.skip_newlines()
            self.expect(TokenType.RPAREN, "Expected ')'")
        
        # Collect inline comment after the signature
        inline_comment = self.collect_inline_comment()
        
        self.skip_newlines()
        body = self.parse_block()
        
        cb = CustomBlock(name=name, display_name=display_name, params=params, body=body, warp=warp, position=pos)
        if inline_comment:
            cb.comment = inline_comment
        return cb
    
    def parse_custom_block_param(self) -> CustomBlockParam:
        """Parse a parameter for a custom block."""
        name = self.expect_ident_or_kw("Expected parameter name").value
        
        # Check for @name attribute
        display_name = None
        if self.match(TokenType.AT):
            attr_name = self.expect(TokenType.IDENTIFIER, "Expected attribute name").value
            if attr_name == "name":
                self.expect(TokenType.ASSIGN, "Expected '='")
                display_name = self.expect(TokenType.STRING, "Expected display name string").value
        
        param_type = "string"
        if self.match(TokenType.COLON):
            type_token = self.expect(TokenType.IDENTIFIER, "Expected parameter type")
            param_type = type_token.value.lower()
        
        return CustomBlockParam(name=name, display_name=display_name, param_type=param_type)
    
    # --- events ---
    
    def parse_event_handler(self) -> EventHandler:
        """Parse event handler."""
        token = self.expect(TokenType.ON, "Expected 'on'")
        pos = self.make_pos(token)
        
        event_type = None
        event_param = None
        
        if self.match(TokenType.FLAG):
            event_type = EventType.FLAG_CLICKED
        elif self.match(TokenType.KEY):
            event_type = EventType.KEY_PRESSED
            event_param = self.expect(TokenType.STRING, "Expected key name").value
        elif self.match(TokenType.CLICKED):
            event_type = EventType.SPRITE_CLICKED
        elif self.match(TokenType.BACKDROP):
            event_type = EventType.BACKDROP_SWITCHES
            event_param = self.expect(TokenType.STRING, "Expected backdrop name").value
        elif self.match(TokenType.LOUDNESS):
            event_type = EventType.LOUDNESS_GREATER
            self.expect(TokenType.GT, "Expected '>'")
            event_param = self.parse_number_value()
        elif self.match(TokenType.TIMER):
            event_type = EventType.TIMER_GREATER
            self.expect(TokenType.GT, "Expected '>'")
            event_param = self.parse_number_value()
        elif self.match(TokenType.MESSAGE):
            event_type = EventType.MESSAGE_RECEIVED
            event_param = self.expect(TokenType.STRING, "Expected message name").value
        elif self.match(TokenType.CLONE):
            event_type = EventType.CLONE_STARTS
        else:
            raise ParseError("Expected event type", self.current())
        
        # Collect inline comment after event declaration
        inline_comment = self.collect_inline_comment()
        
        self.skip_newlines()
        body = self.parse_block()
        
        handler = EventHandler(event_type=event_type, event_param=event_param, body=body, position=pos)
        if inline_comment:
            handler.comment = inline_comment
        return handler
    
    # --- statements ---
    
    def parse_block(self) -> List[Statement]:
        self.expect(TokenType.LBRACE, "Expected '{'")
        
        statements = []
        while not self.check(TokenType.RBRACE) and not self.is_at_end():
            # Skip newlines but NOT comments - let parse_statement handle comments
            while self.match(TokenType.NEWLINE):
                pass
            
            if self.check(TokenType.RBRACE):
                break
                
            stmt = self.parse_statement()
            if stmt:
                statements.append(stmt)
        
        self.expect(TokenType.RBRACE, "Expected '}'")
        return statements
    
    def parse_statement(self) -> Optional[Statement]:
        # Collect any preceding comments (standalone comments on their own lines)
        preceding_comments = []
        while True:
            # Skip newlines
            while self.match(TokenType.NEWLINE):
                pass
            # Skip excluded comments, only collect regular comments
            if self.check(TokenType.EXCLUDED_COMMENT):
                self.advance()  # skip excluded comment
            elif self.check(TokenType.COMMENT):
                preceding_comments.append(self.advance().value)
            else:
                break
        
        # Skip any remaining newlines
        while self.match(TokenType.NEWLINE):
            pass
        
        stmt = None
        
        if self.check(TokenType.IF):
            stmt = self.parse_if_statement()
        elif self.check(TokenType.REPEAT):
            stmt = self.parse_repeat_statement()
        elif self.check(TokenType.FOREVER):
            stmt = self.parse_forever_statement()
        elif self.check(TokenType.WHILE):
            stmt = self.parse_while_statement()
        elif self.check(TokenType.UNTIL):
            stmt = self.parse_until_statement()
        elif self.check(TokenType.WAIT):
            stmt = self.parse_wait_statement()
        elif self.check(TokenType.STOP):
            stmt = self.parse_stop_statement()
        elif self.check(TokenType.RETURN):
            stmt = self.parse_return_statement()
        elif self.check(TokenType.VAR):
            stmt = self.parse_var_decl()
        elif self.check(TokenType.LIST):
            stmt = self.parse_list_decl()
        elif self.check(TokenType.SET):
            stmt = self.parse_set_statement()
        elif self.check(TokenType.CHANGE):
            stmt = self.parse_change_statement()
        elif self.check(TokenType.SHOW):
            stmt = self.parse_show_statement()
        elif self.check(TokenType.HIDE):
            stmt = self.parse_hide_statement()
        elif self.check(TokenType.ADD):
            stmt = self.parse_add_to_list()
        elif self.check(TokenType.DELETE):
            stmt = self.parse_delete_from_list()
        elif self.check(TokenType.INSERT):
            stmt = self.parse_insert_in_list()
        elif self.check(TokenType.REPLACE):
            stmt = self.parse_replace_in_list()
        else:
            stmt = self.parse_block_call()
        
        if stmt:
            # Collect inline comment (same line as statement)
            inline_comment = self.collect_inline_comment()
            if inline_comment:
                stmt.comment = inline_comment
            if preceding_comments:
                stmt.preceding_comments = preceding_comments
        
        return stmt
    
    def parse_if_statement(self) -> IfStatement:
        token = self.expect(TokenType.IF, "Expected 'if'")
        pos = self.make_pos(token)
        
        condition = self.parse_expression()
        self.skip_newlines()
        then_body = self.parse_block()
        
        else_body = []
        self.skip_newlines()
        
        if self.match(TokenType.ELIF):
            # Convert elif to nested if in else
            self.pos -= 1  # Back up
            self.tokens[self.pos] = Token(TokenType.IF, 'if', self.tokens[self.pos].line, self.tokens[self.pos].column)
            else_body = [self.parse_if_statement()]
        elif self.match(TokenType.ELSE):
            self.skip_newlines()
            else_body = self.parse_block()
        
        return IfStatement(condition=condition, then_body=then_body, else_body=else_body, position=pos)
    
    def parse_repeat_statement(self) -> RepeatStatement:
        token = self.expect(TokenType.REPEAT, "Expected 'repeat'")
        pos = self.make_pos(token)
        
        count = self.parse_expression()
        self.skip_newlines()
        body = self.parse_block()
        
        return RepeatStatement(count=count, body=body, position=pos)
    
    def parse_forever_statement(self) -> ForeverStatement:
        token = self.expect(TokenType.FOREVER, "Expected 'forever'")
        pos = self.make_pos(token)
        
        self.skip_newlines()
        body = self.parse_block()
        
        return ForeverStatement(body=body, position=pos)
    
    def parse_while_statement(self) -> WhileStatement:
        token = self.expect(TokenType.WHILE, "Expected 'while'")
        pos = self.make_pos(token)
        
        condition = self.parse_expression()
        self.skip_newlines()
        body = self.parse_block()
        
        return WhileStatement(condition=condition, body=body, is_until=False, position=pos)
    
    def parse_until_statement(self) -> WhileStatement:
        token = self.expect(TokenType.UNTIL, "Expected 'until'")
        pos = self.make_pos(token)
        
        condition = self.parse_expression()
        self.skip_newlines()
        body = self.parse_block()
        
        return WhileStatement(condition=condition, body=body, is_until=True, position=pos)
    
    def parse_wait_statement(self) -> Statement:
        token = self.expect(TokenType.WAIT, "Expected 'wait'")
        pos = self.make_pos(token)
        
        if self.match(TokenType.UNTIL):
            condition = self.parse_expression()
            return WaitUntilStatement(condition=condition, position=pos)
        else:
            duration = self.parse_expression()
            if self.check(TokenType.IDENTIFIER) and self.current().value.lower() in ('secs', 'seconds'):
                self.advance()
            return WaitStatement(duration=duration, position=pos)
    
    def parse_stop_statement(self) -> StopStatement:
        token = self.expect(TokenType.STOP, "Expected 'stop'")
        pos = self.make_pos(token)
        
        stop_option = "all"
        if self.check(TokenType.STRING):
            stop_option = self.advance().value
        elif self.check(TokenType.IDENTIFIER):
            stop_option = self.advance().value
        
        return StopStatement(stop_option=stop_option, position=pos)
    
    def parse_return_statement(self) -> ReturnStatement:
        """Parse return statement."""
        token = self.expect(TokenType.RETURN, "Expected 'return'")
        pos = self.make_pos(token)
        
        value = None
        # Check if there's an expression following return
        # We need to be careful not to consume the next statement or '}'
        if not self.check(TokenType.RBRACE) and not self.check(TokenType.NEWLINE) and not self.check(TokenType.EOF):
             value = self.parse_expression()
        
        return ReturnStatement(value=value, position=pos)
    
    def parse_set_statement(self) -> Statement:
        token = self.expect(TokenType.SET, "Expected 'set'")
        pos = self.make_pos(token)
        
        if self.match(TokenType.INSTRUMENT):
            if self.check(TokenType.IDENTIFIER) and self.current().value.lower() == 'to':
                self.advance()
            value = self.parse_expression()
            return BlockCall(block_name="set_instrument", args=[value], fields={}, position=pos)
        elif self.match(TokenType.TEMPO):
            if self.check(TokenType.IDENTIFIER) and self.current().value.lower() == 'to':
                self.advance()
            value = self.parse_expression()
            return BlockCall(block_name="set_tempo", args=[value], fields={}, position=pos)
        elif self.match(TokenType.PEN):
            if self.check(TokenType.IDENTIFIER) and self.current().value.lower() == 'color':
                self.advance()
                if self.check(TokenType.IDENTIFIER) and self.current().value.lower() == 'to':
                    self.advance()
                value = self.parse_expression()
                return BlockCall(block_name="set_pen_color", args=[value], fields={}, position=pos)
            elif self.check(TokenType.IDENTIFIER) and self.current().value.lower() == 'size':
                self.advance()
                if self.check(TokenType.IDENTIFIER) and self.current().value.lower() == 'to':
                    self.advance()
                value = self.parse_expression()
                return BlockCall(block_name="set_pen_size", args=[value], fields={}, position=pos)
        
        name = self.expect_ident_or_kw("Expected var name").value
        
        if name == "size":  # maps to looks_setsizeto
            if not self.match(TokenType.ASSIGN):
                if self.check(TokenType.IDENTIFIER) and self.current().value.lower() == 'to':
                    self.advance()
            value = self.parse_expression()
            return BlockCall(block_name="set_size", args=[value], fields={}, position=pos)
        
        if name == "x":  # motion_setx
            if not self.match(TokenType.ASSIGN):
                if self.check(TokenType.IDENTIFIER) and self.current().value.lower() == 'to':
                    self.advance()
            value = self.parse_expression()
            return BlockCall(block_name="set_x", args=[value], fields={}, position=pos)
        
        if name == "y":  # motion_sety
            if not self.match(TokenType.ASSIGN):
                if self.check(TokenType.IDENTIFIER) and self.current().value.lower() == 'to':
                    self.advance()
            value = self.parse_expression()
            return BlockCall(block_name="set_y", args=[value], fields={}, position=pos)
        
        if not self.match(TokenType.ASSIGN):
            if self.check(TokenType.IDENTIFIER) and self.current().value.lower() == 'to':
                self.advance()
            else:
                self.expect(TokenType.ASSIGN, "Expected '=' or 'to'")
        
        value = self.parse_expression()
        
        return SetVariable(var_name=name, value=value, position=pos)
    
    def parse_change_statement(self) -> Statement:
        token = self.expect(TokenType.CHANGE, "Expected 'change'")
        pos = self.make_pos(token)
        
        if self.match(TokenType.TEMPO):
            if self.check(TokenType.IDENTIFIER) and self.current().value.lower() == 'by':
                self.advance()
            value = self.parse_expression()
            return BlockCall(block_name="change_tempo", args=[value], fields={}, position=pos)
        elif self.match(TokenType.PEN):
            if self.check(TokenType.IDENTIFIER) and self.current().value.lower() == 'size':
                self.advance()
                if self.check(TokenType.IDENTIFIER) and self.current().value.lower() == 'by':
                    self.advance()
                value = self.parse_expression()
                return BlockCall(block_name="change_pen_size", args=[value], fields={}, position=pos)
        
        name = self.expect_ident_or_kw("Expected var name").value
        
        if self.match(TokenType.IDENTIFIER) and self.tokens[self.pos - 1].value.lower() == 'by':
            pass
        elif not self.match(TokenType.PLUS) and not self.match(TokenType.ASSIGN):
            self.expect(TokenType.IDENTIFIER, "Expected 'by'")
        
        value = self.parse_expression()
        
        lower_name = name.lower()
        if lower_name == 'x':
            return BlockCall(block_name="change_x", args=[value], fields={}, position=pos)
        elif lower_name == 'y':
            return BlockCall(block_name="change_y", args=[value], fields={}, position=pos)
        elif lower_name == 'size':
            return BlockCall(block_name="change_size", args=[value], fields={}, position=pos)
        
        return ChangeVariable(var_name=name, value=value, position=pos)
    
    def parse_show_statement(self) -> Statement:
        token = self.expect(TokenType.SHOW, "Expected 'show'")
        pos = self.make_pos(token)
        
        if self.match(TokenType.VAR):
            name = self.expect(TokenType.IDENTIFIER, "Expected var name").value
            return ShowVariable(var_name=name, position=pos)
        elif self.match(TokenType.LIST):
            name = self.expect(TokenType.IDENTIFIER, "Expected list name").value
            return ShowList(list_name=name, position=pos)
        else:
            return BlockCall(block_name="show", position=pos)
    
    def parse_hide_statement(self) -> Statement:
        token = self.expect(TokenType.HIDE, "Expected 'hide'")
        pos = self.make_pos(token)
        
        if self.match(TokenType.VAR):
            name = self.expect(TokenType.IDENTIFIER, "Expected var name").value
            return HideVariable(var_name=name, position=pos)
        elif self.match(TokenType.LIST):
            name = self.expect(TokenType.IDENTIFIER, "Expected list name").value
            return HideList(list_name=name, position=pos)
        else:
            return BlockCall(block_name="hide", position=pos)
    
    def parse_add_to_list(self) -> ListOperation:
        token = self.expect(TokenType.ADD, "Expected 'add'")
        pos = self.make_pos(token)
        
        value = self.parse_expression()
        
        if self.check(TokenType.IDENTIFIER) and self.current().value.lower() == 'to':
            self.advance()
        
        list_name = self.expect(TokenType.IDENTIFIER, "Expected list name").value
        
        return ListOperation(operation="add", list_name=list_name, value=value, position=pos)
    
    def parse_delete_from_list(self) -> ListOperation:
        token = self.expect(TokenType.DELETE, "Expected 'delete'")
        pos = self.make_pos(token)
        
        if self.check(TokenType.IDENTIFIER) and self.current().value.lower() == 'all':
            self.advance()
            if self.check(TokenType.IDENTIFIER) and self.current().value.lower() in ('from', 'of'):
                self.advance()
            elif self.match(TokenType.FROM):
                pass
            
            list_name = self.expect(TokenType.IDENTIFIER, "Expected list name").value
            return ListOperation(operation="deleteAll", list_name=list_name, position=pos)
        
        index = self.parse_expression()
        
        if self.check(TokenType.IDENTIFIER) and self.current().value.lower() in ('from', 'of'):
            self.advance()
        elif self.match(TokenType.FROM):
            pass
        
        list_name = self.expect(TokenType.IDENTIFIER, "Expected list name").value
        
        return ListOperation(operation="delete", list_name=list_name, index=index, position=pos)
    
    def parse_insert_in_list(self) -> ListOperation:
        token = self.expect(TokenType.INSERT, "Expected 'insert'")
        pos = self.make_pos(token)
        
        value = self.parse_expression()
        
        if self.check(TokenType.IDENTIFIER) and self.current().value.lower() == 'at':
            self.advance()
        
        index = self.parse_expression()
        
        if self.check(TokenType.IDENTIFIER) and self.current().value.lower() in ('in', 'of'):
            self.advance()
        
        list_name = self.expect(TokenType.IDENTIFIER, "Expected list name").value
        
        return ListOperation(operation="insert", list_name=list_name, value=value, index=index, position=pos)
    
    def parse_replace_in_list(self) -> ListOperation:
        token = self.expect(TokenType.REPLACE, "Expected 'replace'")
        pos = self.make_pos(token)
        
        if self.check(TokenType.ITEM):
            self.advance()
        
        index = self.parse_expression()
        
        if self.check(TokenType.IDENTIFIER) and self.current().value.lower() in ('in', 'of'):
            self.advance()
        
        list_name = self.expect(TokenType.IDENTIFIER, "Expected list name").value
        
        if self.check(TokenType.IDENTIFIER) and self.current().value.lower() == 'with':
            self.advance()
        
        value = self.parse_expression()
        
        return ListOperation(operation="replace", list_name=list_name, value=value, index=index, position=pos)
    
    def parse_block_call(self) -> BlockCall:
        token = self.current()
        pos = self.make_pos(token)
        
        block_name = ""
        args = []
        fields = {}
        
        if self.match(TokenType.MOVE):
            block_name = "move"
            args.append(self.parse_expression())
            if self.check(TokenType.IDENTIFIER) and self.current().value.lower() == 'steps':
                self.advance()
        elif self.match(TokenType.TURN):
            if self.check(TokenType.IDENTIFIER):
                direction = self.current().value.lower()
                if direction in ('left', 'ccw'):
                    self.advance()
                    block_name = "turn_left"
                elif direction in ('right', 'cw'):
                    self.advance()
                    block_name = "turn_right"
                else:
                    block_name = "turn_right"
            else:
                block_name = "turn_right"
            args.append(self.parse_expression())
            if self.check(TokenType.IDENTIFIER) and self.current().value.lower() == 'degrees':
                self.advance()
        elif self.match(TokenType.GOTO):
            block_name = "goto"
            if self.check(TokenType.IDENTIFIER) and self.current().value.lower() == 'xy':
                self.advance()
                block_name = "goto_xy"
                args.append(self.parse_expression())
                self.match(TokenType.COMMA)
                args.append(self.parse_expression())
            elif self.check(TokenType.RANDOM):
                self.advance()
                fields['TO'] = '_random_'
            elif self.check(TokenType.IDENTIFIER) and self.current().value.lower() == 'mouse':
                self.advance()
                fields['TO'] = '_mouse_'
            else:
                target = self.parse_expression()
                if self.match(TokenType.COMMA):
                    # It's goto x, y
                    block_name = "goto_xy"
                    args.append(target)
                    args.append(self.parse_expression())
                elif isinstance(target, StringLiteral):
                    fields['TO'] = target.value
                else:
                    args.append(target)
        elif self.match(TokenType.GLIDE):
            args.append(self.parse_expression())  # duration
            if self.check(TokenType.IDENTIFIER) and self.current().value.lower() in ('secs', 'seconds', 'to'):
                self.advance()
            
            if self.check(TokenType.IDENTIFIER) and self.current().value.lower() == 'xy':
                self.advance()
                block_name = "glide_xy"
                args.append(self.parse_expression())  # x
                self.match(TokenType.COMMA)
                args.append(self.parse_expression())  # y
            else:
                block_name = "glide_to"
                target = self.parse_expression()
                if isinstance(target, StringLiteral):
                    fields['TO'] = target.value
                else:
                    args.append(target)
        elif self.match(TokenType.POINT):
            if self.check(TokenType.IDENTIFIER) and self.current().value.lower() in ('in', 'towards'):
                direction_type = self.advance().value.lower()
                if direction_type == 'in':
                    block_name = "point_direction"
                    if self.check(TokenType.IDENTIFIER) and self.current().value.lower() == 'direction':
                        self.advance()
                    args.append(self.parse_expression())
                else:
                    block_name = "point_towards"
                    target = self.parse_expression()
                    if isinstance(target, StringLiteral):
                        fields['TOWARDS'] = target.value
                    else:
                        args.append(target)
            else:
                block_name = "point_direction"
                args.append(self.parse_expression())
        elif self.match(TokenType.BOUNCE):
            block_name = "bounce_on_edge"
        elif self.match(TokenType.SAY):
            message = self.parse_expression()
            args.append(message)
            if self.match(TokenType.FOR) or (self.check(TokenType.IDENTIFIER) and self.current().value.lower() == 'for' and self.advance()):
                block_name = "say_for"
                args.append(self.parse_expression())
                if self.check(TokenType.IDENTIFIER) and self.current().value.lower() in ('secs', 'seconds'):
                    self.advance()
            else:
                block_name = "say"
        elif self.match(TokenType.THINK):
            message = self.parse_expression()
            args.append(message)
            if self.match(TokenType.FOR) or (self.check(TokenType.IDENTIFIER) and self.current().value.lower() == 'for' and self.advance()):
                block_name = "think_for"
                args.append(self.parse_expression())
                if self.check(TokenType.IDENTIFIER) and self.current().value.lower() in ('secs', 'seconds'):
                    self.advance()
            else:
                block_name = "think"
        elif self.match(TokenType.SWITCH):
            if self.check(TokenType.IDENTIFIER) and self.current().value.lower() == 'costume':
                self.advance()
                block_name = "switch_costume"
                if self.check(TokenType.IDENTIFIER) and self.current().value.lower() == 'to':
                    self.advance()
                args.append(self.parse_expression())
            elif self.match(TokenType.BACKDROP):
                block_name = "switch_backdrop"
                if self.check(TokenType.IDENTIFIER) and self.current().value.lower() == 'to':
                    self.advance()
                args.append(self.parse_expression())
            else:
                raise ParseError("Expected 'costume' or 'backdrop' after 'switch'", self.current())
        elif self.match(TokenType.NEXT):
            if self.check(TokenType.IDENTIFIER) and self.current().value.lower() == 'costume':
                self.advance()
                block_name = "next_costume"
            elif self.match(TokenType.BACKDROP):
                block_name = "next_backdrop"
            else:
                raise ParseError("Expected 'costume' or 'backdrop' after 'next'", self.current())
        elif self.match(TokenType.SIZE):
            if self.match(TokenType.ASSIGN):
                block_name = "set_size"
                args.append(self.parse_expression())
            elif self.match(TokenType.PLUS):
                block_name = "change_size"
                args.append(self.parse_expression())
            else:
                block_name = "set_size"
                args.append(self.parse_expression())
        elif self.match(TokenType.EFFECT):
            effect_name = self.expect(TokenType.IDENTIFIER, "Expected effect name").value
            fields['EFFECT'] = effect_name.upper()
            if self.match(TokenType.ASSIGN):
                block_name = "set_effect"
                args.append(self.parse_expression())
            elif self.match(TokenType.PLUS):
                block_name = "change_effect"
                args.append(self.parse_expression())
            else:
                block_name = "set_effect"
                args.append(self.parse_expression())
        elif self.match(TokenType.CLEAR):
            if self.check(TokenType.IDENTIFIER) and self.current().value.lower() == 'effects':
                self.advance()
                block_name = "clear_effects"
            else:
                block_name = "clear_effects"
        elif self.match(TokenType.LAYER):
            if self.check(TokenType.IDENTIFIER):
                action = self.advance().value.lower()
                if action == 'front':
                    block_name = "go_to_front"
                elif action == 'back':
                    block_name = "go_to_back"
                elif action == 'forward':
                    block_name = "go_forward_layers"
                    args.append(self.parse_expression())
                elif action == 'backward':
                    block_name = "go_backward_layers"
                    args.append(self.parse_expression())
        elif self.match(TokenType.PLAY):
            if self.match(TokenType.DRUM):
                # play drum (1) for (0.25) beats
                drum = self.parse_expression()
                args.append(drum)
                if self.match(TokenType.FOR):
                    pass
                elif self.check(TokenType.IDENTIFIER) and self.current().value.lower() == 'for':
                    self.advance()
                
                beats = self.parse_expression()
                args.append(beats)
                if self.check(TokenType.IDENTIFIER) and self.current().value.lower() == 'beats':
                    self.advance()
                block_name = "play_drum"
            elif self.match(TokenType.NOTE):
                # play note (60) for (0.5) beats
                note = self.parse_expression()
                args.append(note)
                if self.match(TokenType.FOR):
                    pass
                elif self.check(TokenType.IDENTIFIER) and self.current().value.lower() == 'for':
                    self.advance()
                
                beats = self.parse_expression()
                args.append(beats)
                if self.check(TokenType.IDENTIFIER) and self.current().value.lower() == 'beats':
                    self.advance()
                block_name = "play_note"
            elif self.check(TokenType.IDENTIFIER) and self.current().value.lower() == 'sound':
                self.advance()
                sound_name = self.parse_expression()
                args.append(sound_name)
                if self.check(TokenType.IDENTIFIER) and self.current().value.lower() == 'until':
                    self.advance()
                    if self.check(TokenType.IDENTIFIER) and self.current().value.lower() == 'done':
                        self.advance()
                    block_name = "play_sound_until_done"
                else:
                    block_name = "start_sound"
            else:
                block_name = "start_sound"
                args.append(self.parse_expression())
        elif self.match(TokenType.REST):
            # rest for (0.25) beats
            if self.match(TokenType.FOR):
                pass
            elif self.check(TokenType.IDENTIFIER) and self.current().value.lower() == 'for':
                self.advance()
            
            beats = self.parse_expression()
            args.append(beats)
            if self.check(TokenType.IDENTIFIER) and self.current().value.lower() == 'beats':
                self.advance()
            block_name = "rest_for_beats"
        elif self.match(TokenType.START):
            if self.check(TokenType.IDENTIFIER) and self.current().value.lower() == 'sound':
                self.advance()
                block_name = "start_sound"
                args.append(self.parse_expression())
        elif self.match(TokenType.STOP):
            if self.check(TokenType.IDENTIFIER) and self.current().value.lower() == 'all':
                self.advance()
                if self.check(TokenType.IDENTIFIER) and self.current().value.lower() == 'sounds':
                    self.advance()
                block_name = "stop_all_sounds"
        elif self.match(TokenType.VOLUME):
            if self.match(TokenType.ASSIGN):
                block_name = "set_volume"
                args.append(self.parse_expression())
            elif self.match(TokenType.PLUS):
                block_name = "change_volume"
                args.append(self.parse_expression())
        elif self.match(TokenType.BROADCAST):
            message = self.parse_expression()
            args.append(message)
            if self.match(TokenType.AND) or (self.check(TokenType.IDENTIFIER) and self.current().value.lower() == 'and' and self.advance()):
                if self.match(TokenType.WAIT) or (self.check(TokenType.IDENTIFIER) and self.current().value.lower() == 'wait' and self.advance()):
                    pass
                block_name = "broadcast_and_wait"
            else:
                block_name = "broadcast"
        elif self.match(TokenType.ASK):
            args.append(self.parse_expression())
            if self.match(TokenType.AND) or (self.check(TokenType.IDENTIFIER) and self.current().value.lower() == 'and' and self.advance()):
                if self.match(TokenType.WAIT) or (self.check(TokenType.IDENTIFIER) and self.current().value.lower() == 'wait' and self.advance()):
                    pass
            block_name = "ask_and_wait"
        elif self.match(TokenType.PEN):
            if self.check(TokenType.IDENTIFIER):
                action = self.current().value.lower()
                if action == 'down':
                    self.advance()
                    block_name = "pen_down"
                elif action == 'up':
                    self.advance()
                    block_name = "pen_up"
                elif action == 'clear':
                    self.advance()
                    block_name = "erase_all"
                elif action == 'stamp':
                    self.advance()
                    block_name = "stamp"
                elif action == 'color':
                    self.advance()
                    if self.match(TokenType.ASSIGN):
                        block_name = "set_pen_color"
                        args.append(self.parse_expression())
                    elif self.match(TokenType.PLUS):
                        block_name = "change_pen_param"
                        fields['colorParam'] = 'color'
                        args.append(self.parse_expression())
                elif action == 'size':
                    self.advance()
                    if self.match(TokenType.ASSIGN):
                        block_name = "set_pen_size"
                        args.append(self.parse_expression())
                    elif self.match(TokenType.PLUS):
                        block_name = "change_pen_size"
                        args.append(self.parse_expression())
        elif self.check(TokenType.IDENTIFIER):
            # Check for pen_down, pen_up, etc. if they are used as identifiers
            name = self.current().value
            if name == "pen_down":
                self.advance()
                block_name = "pen_down"
                if self.match(TokenType.LPAREN): self.expect(TokenType.RPAREN, "Expected ')'")
            elif name == "pen_up":
                self.advance()
                block_name = "pen_up"
                if self.match(TokenType.LPAREN): self.expect(TokenType.RPAREN, "Expected ')'")
            elif name == "stamp":
                self.advance()
                block_name = "stamp"
                if self.match(TokenType.LPAREN): self.expect(TokenType.RPAREN, "Expected ')'")
            elif name == "erase_all" or name == "pen_clear":
                self.advance()
                block_name = "erase_all"
                if self.match(TokenType.LPAREN): self.expect(TokenType.RPAREN, "Expected ')'")
            elif name == "set_pen_color":
                self.advance()
                block_name = "set_pen_color"
                if self.match(TokenType.LPAREN):
                    if not self.check(TokenType.RPAREN):
                        args.append(self.parse_expression())
                    self.expect(TokenType.RPAREN, "Expected ')'")
                return BlockCall(block_name=block_name, args=args, fields=fields, position=pos)
            elif name == "change_pen_color":
                self.advance()
                block_name = "change_pen_param"
                fields['colorParam'] = 'color'
                if self.match(TokenType.LPAREN):
                    if not self.check(TokenType.RPAREN):
                        args.append(self.parse_expression())
                    self.expect(TokenType.RPAREN, "Expected ')'")
                return BlockCall(block_name=block_name, args=args, fields=fields, position=pos)
            elif name == "set_pen_size":
                self.advance()
                block_name = "set_pen_size"
                if self.match(TokenType.LPAREN):
                    if not self.check(TokenType.RPAREN):
                        args.append(self.parse_expression())
                    self.expect(TokenType.RPAREN, "Expected ')'")
                return BlockCall(block_name=block_name, args=args, fields=fields, position=pos)
            elif name == "change_pen_size":
                self.advance()
                block_name = "change_pen_size"
                if self.match(TokenType.LPAREN):
                    if not self.check(TokenType.RPAREN):
                        args.append(self.parse_expression())
                    self.expect(TokenType.RPAREN, "Expected ')'")
                return BlockCall(block_name=block_name, args=args, fields=fields, position=pos)
            else:
                # Custom block call or extension block call
                block_name = self.expect(TokenType.IDENTIFIER, "Expected block name").value
                
                # Support dotted names for extension blocks (e.g., "SPsoundWaves.play_note")
                while self.match(TokenType.DOT):
                    # Accept identifier or keyword after dot (keywords like 'clear' are valid method names)
                    next_token = self.current()
                    if next_token.type == TokenType.IDENTIFIER:
                        next_part = self.advance().value
                    elif next_token.value is not None and isinstance(next_token.value, str):
                        # Accept keywords as method names in extension calls
                        next_part = self.advance().value
                    else:
                        raise ParseError("Expected identifier or keyword after '.'", next_token)
                    block_name = f"{block_name}.{next_part}"
                
                if self.match(TokenType.LPAREN):
                    if not self.check(TokenType.RPAREN):
                        args.append(self.parse_expression())
                        while self.match(TokenType.COMMA):
                            args.append(self.parse_expression())
                    self.expect(TokenType.RPAREN, "Expected ')'")
        elif self.match(TokenType.ERASE):
            if self.check(TokenType.IDENTIFIER) and self.current().value.lower() == 'all':
                self.advance()
            block_name = "erase_all"
        elif self.match(TokenType.STAMP):
            block_name = "stamp"
        elif self.match(TokenType.PLAY):
            # Check for music blocks
            if self.match(TokenType.DRUM):
                block_name = "play_drum"
                args.append(self.parse_expression())
                if self.match(TokenType.FOR) or (self.check(TokenType.IDENTIFIER) and self.current().value.lower() == 'for' and self.advance()):
                    args.append(self.parse_expression())
                    if self.check(TokenType.IDENTIFIER) and self.current().value.lower() == 'beats':
                        self.advance()
            elif self.match(TokenType.NOTE):
                block_name = "play_note"
                args.append(self.parse_expression())
                if self.match(TokenType.FOR) or (self.check(TokenType.IDENTIFIER) and self.current().value.lower() == 'for' and self.advance()):
                    args.append(self.parse_expression())
                    if self.check(TokenType.IDENTIFIER) and self.current().value.lower() == 'beats':
                        self.advance()
            elif self.check(TokenType.IDENTIFIER) and self.current().value.lower() == 'sound':
                self.advance()
                sound_name = self.parse_expression()
                args.append(sound_name)
                if self.check(TokenType.IDENTIFIER) and self.current().value.lower() == 'until':
                    self.advance()
                    if self.check(TokenType.IDENTIFIER) and self.current().value.lower() == 'done':
                        self.advance()
                    block_name = "play_sound_until_done"
                else:
                    block_name = "start_sound"
            else:
                block_name = "start_sound"
                args.append(self.parse_expression())
        elif self.match(TokenType.REST):
            block_name = "rest"
            if self.match(TokenType.FOR) or (self.check(TokenType.IDENTIFIER) and self.current().value.lower() == 'for' and self.advance()):
                args.append(self.parse_expression())
                if self.check(TokenType.IDENTIFIER) and self.current().value.lower() == 'beats':
                    self.advance()
        elif self.match(TokenType.SET):
            # Check for music set blocks
            if self.match(TokenType.INSTRUMENT):
                block_name = "set_instrument"
                if self.check(TokenType.IDENTIFIER) and self.current().value.lower() == 'to':
                    self.advance()
                args.append(self.parse_expression())
            elif self.match(TokenType.TEMPO):
                block_name = "set_tempo"
                if self.check(TokenType.IDENTIFIER) and self.current().value.lower() == 'to':
                    self.advance()
                args.append(self.parse_expression())
            else:
                # Regular set variable
                # We need to backtrack because parse_set_statement expects SET to be consumed
                # But here we already consumed SET.
                # Actually, parse_statement calls parse_set_statement if it sees SET.
                # So we are in parse_block_call which is the 'else' branch of parse_statement.
                # Wait, parse_statement checks for SET and calls parse_set_statement.
                # So we shouldn't be handling SET here unless it's NOT a variable set.
                # But parse_set_statement assumes it's a variable set.
                # We need to modify parse_statement to handle set instrument/tempo or modify parse_set_statement.
                pass
        elif self.match(TokenType.CHANGE):
            # Similar issue with CHANGE
            if self.match(TokenType.TEMPO):
                block_name = "change_tempo"
                if self.check(TokenType.IDENTIFIER) and self.current().value.lower() == 'by':
                    self.advance()
                args.append(self.parse_expression())
            else:
                pass
        elif self.match(TokenType.DRAG):
            if self.check(TokenType.IDENTIFIER) and self.current().value.lower() == 'mode':
                self.advance()
                block_name = "set_drag_mode"
                mode = self.expect(TokenType.STRING, "Expected drag mode").value
                fields['DRAG_MODE'] = mode
        elif self.match(TokenType.RESET):
            if self.check(TokenType.TIMER) or (self.check(TokenType.IDENTIFIER) and self.current().value.lower() == 'timer'):
                self.advance()
                block_name = "reset_timer"
        elif self.match(TokenType.CREATE):
            if self.check(TokenType.CLONE) or (self.check(TokenType.IDENTIFIER) and self.current().value.lower() == 'clone'):
                self.advance()
                block_name = "create_clone"
                if self.check(TokenType.IDENTIFIER) and self.current().value.lower() == 'of':
                    self.advance()
                if self.check(TokenType.IDENTIFIER) and self.current().value.lower() == 'myself':
                    self.advance()
                    fields['CLONE_OPTION'] = '_myself_'
                else:
                    target = self.parse_expression()
                    if isinstance(target, StringLiteral):
                        fields['CLONE_OPTION'] = target.value
                    else:
                        args.append(target)
        elif self.match(TokenType.LOG):
            # Handle 'log' as a block call (e.g. for logging library)
            block_name = "log"
            
            # Check for arguments in parentheses
            if self.match(TokenType.LPAREN):
                if not self.check(TokenType.RPAREN):
                    args.append(self.parse_expression())
                    while self.match(TokenType.COMMA):
                        args.append(self.parse_expression())
                self.expect(TokenType.RPAREN, "Expected ')'")
        elif self.check(TokenType.IDENTIFIER):
            # Custom block call or built-in block
            block_name = self.advance().value
            
            # Check for arguments in parentheses
            if self.match(TokenType.LPAREN):
                if not self.check(TokenType.RPAREN):
                    args.append(self.parse_expression())
                    while self.match(TokenType.COMMA):
                        args.append(self.parse_expression())
                self.expect(TokenType.RPAREN, "Expected ')'")
        else:
            raise ParseError(f"Expected statement, got {self.current().type.name}", self.current())
        
        return BlockCall(block_name=block_name, args=args, fields=fields, position=pos)
    
    # --- expressions ---
    
    def parse_expression(self) -> Expression:
        return self.parse_or_expr()
    
    def parse_or_expr(self) -> Expression:
        left = self.parse_and_expr()
        
        while self.match(TokenType.OR):
            right = self.parse_and_expr()
            left = BinaryOp(operator='or', left=left, right=right)
        
        return left
    
    def parse_and_expr(self) -> Expression:
        left = self.parse_comparison()
        
        while self.check(TokenType.AND):
            # special case: 'and wait' for ask/broadcast
            if self.peek().type == TokenType.WAIT:
                break
            if self.peek().type == TokenType.IDENTIFIER and self.peek().value.lower() == 'wait':
                break
                
            self.advance()
            right = self.parse_comparison()
            left = BinaryOp(operator='and', left=left, right=right)
        
        return left
    
    def parse_comparison(self) -> Expression:
        left = self.parse_addition()
        
        while True:
            if self.match(TokenType.EQ):
                right = self.parse_addition()
                left = BinaryOp(operator='==', left=left, right=right)
            elif self.match(TokenType.NEQ):
                right = self.parse_addition()
                left = BinaryOp(operator='!=', left=left, right=right)
            elif self.match(TokenType.LT):
                right = self.parse_addition()
                left = BinaryOp(operator='<', left=left, right=right)
            elif self.match(TokenType.GT):
                right = self.parse_addition()
                left = BinaryOp(operator='>', left=left, right=right)
            elif self.match(TokenType.LTE):
                right = self.parse_addition()
                left = BinaryOp(operator='<=', left=left, right=right)
            elif self.match(TokenType.GTE):
                right = self.parse_addition()
                left = BinaryOp(operator='>=', left=left, right=right)
            else:
                break
        
        return left
    
    def parse_addition(self) -> Expression:
        left = self.parse_multiplication()
        
        while True:
            if self.match(TokenType.PLUS):
                right = self.parse_multiplication()
                left = BinaryOp(operator='+', left=left, right=right)
            elif self.match(TokenType.MINUS):
                right = self.parse_multiplication()
                left = BinaryOp(operator='-', left=left, right=right)
            else:
                break
        
        return left
    
    def parse_multiplication(self) -> Expression:
        left = self.parse_unary()
        
        while True:
            if self.match(TokenType.STAR):
                right = self.parse_unary()
                left = BinaryOp(operator='*', left=left, right=right)
            elif self.match(TokenType.SLASH):
                right = self.parse_unary()
                left = BinaryOp(operator='/', left=left, right=right)
            elif self.match(TokenType.PERCENT, TokenType.MOD):
                right = self.parse_unary()
                left = BinaryOp(operator='mod', left=left, right=right)
            else:
                break
        
        return left
    
    def parse_unary(self) -> Expression:
        if self.match(TokenType.NOT):
            operand = self.parse_unary()
            return UnaryOp(operator='not', operand=operand)
        elif self.match(TokenType.MINUS):
            operand = self.parse_unary()
            return BinaryOp(operator='*', left=NumberLiteral(value=-1), right=operand)
        
        return self.parse_power()
    
    def parse_power(self) -> Expression:
        left = self.parse_call()
        
        if self.match(TokenType.CARET):
            right = self.parse_unary()
            return FunctionCall(func_name='pow', args=[left, right])
        
        return left
    
    def parse_call(self) -> Expression:
        expr = self.parse_primary()
        
        while True:
            if self.match(TokenType.LPAREN):
                args = []
                self.skip_newlines()
                if not self.check(TokenType.RPAREN):
                    args.append(self.parse_expression())
                    self.skip_newlines()
                    while self.match(TokenType.COMMA):
                        self.skip_newlines()
                        args.append(self.parse_expression())
                        self.skip_newlines()
                self.skip_newlines()
                self.expect(TokenType.RPAREN, "Expected ')'")
                
                if isinstance(expr, VariableRef):
                    expr = FunctionCall(func_name=expr.name, args=args)
                elif isinstance(expr, ReporterBlock):
                    if args:
                         raise ParseError("Reporters don't take args", self.current())
                else:
                    raise ParseError("Can only call functions", self.current())
            elif self.match(TokenType.LBRACKET):
                index = self.parse_expression()
                self.expect(TokenType.RBRACKET, "Expected ']'")
                
                if isinstance(expr, VariableRef):
                    expr = ListItemAccess(list_name=expr.name, index=index)
                else:
                    raise ParseError("Can only index lists", self.current())
            else:
                break
        
        return expr
    
    def parse_primary(self) -> Expression:
        token = self.current()
        
        if self.match(TokenType.NUMBER):
            return NumberLiteral(value=token.value)
        
        if self.match(TokenType.STRING):
            return StringLiteral(value=token.value)
        
        if self.match(TokenType.BOOLEAN):
            return BooleanLiteral(value=token.value)
        
        if self.match(TokenType.COLOR):
            return ColorLiteral(value=token.value)
        
        if self.match(TokenType.LAST):  # list index "last"
            return StringLiteral(value="last")
        
        if self.match(TokenType.LPAREN):
            expr = self.parse_expression()
            self.expect(TokenType.RPAREN, "Expected ')'")
            return expr
        
        if self.match(TokenType.RANDOM):
            self.expect(TokenType.LPAREN, "Expected '('")
            low = self.parse_expression()
            self.match(TokenType.COMMA)
            if self.check(TokenType.IDENTIFIER) and self.current().value.lower() == 'to':
                self.advance()
            high = self.parse_expression()
            self.expect(TokenType.RPAREN, "Expected ')'")
            return FunctionCall(func_name='random', args=[low, high])
        
        if self.match(TokenType.JOIN):
            self.expect(TokenType.LPAREN, "Expected '('")
            str1 = self.parse_expression()
            self.match(TokenType.COMMA)
            str2 = self.parse_expression()
            self.expect(TokenType.RPAREN, "Expected ')'")
            return FunctionCall(func_name='join', args=[str1, str2])
        
        if self.match(TokenType.LENGTH):
            self.expect(TokenType.LPAREN, "Expected '('")
            if self.check(TokenType.LIST):
                self.advance()
                list_name = self.expect(TokenType.IDENTIFIER, "Expected list name").value
                self.expect(TokenType.RPAREN, "Expected ')'")
                return ListLength(list_name=list_name)
            else:
                arg = self.parse_expression()
                self.expect(TokenType.RPAREN, "Expected ')'")
                return FunctionCall(func_name='length', args=[arg])
        
        if self.match(TokenType.LETTER):
            self.expect(TokenType.LPAREN, "Expected '('")
            index = self.parse_expression()
            self.match(TokenType.COMMA)
            if self.check(TokenType.IDENTIFIER) and self.current().value.lower() == 'of':
                self.advance()
            string = self.parse_expression()
            self.expect(TokenType.RPAREN, "Expected ')'")
            return FunctionCall(func_name='letter', args=[index, string])
        
        if self.match(TokenType.CONTAINS):
            self.expect(TokenType.LPAREN, "Expected '('")
            string = self.parse_expression()
            self.match(TokenType.COMMA)
            substring = self.parse_expression()
            self.expect(TokenType.RPAREN, "Expected ')'")
            return FunctionCall(func_name='contains', args=[string, substring])
        
        # Math functions and other keywords that can be variables
        for func_type in [TokenType.ROUND, TokenType.ABS, TokenType.FLOOR, TokenType.CEIL,
                         TokenType.SQRT, TokenType.SIN, TokenType.COS, TokenType.TAN,
                         TokenType.ASIN, TokenType.ACOS, TokenType.ATAN, TokenType.LN,
                         TokenType.LOG, TokenType.ANTILN, TokenType.ANTILOG,
                         TokenType.START, TokenType.STOP, TokenType.WAIT, TokenType.TIMER,
                         TokenType.SIZE, TokenType.VOLUME, TokenType.LOUDNESS,
                         TokenType.KEY, TokenType.FLAG, TokenType.CLONE, TokenType.MESSAGE,
                         TokenType.BACKDROP, TokenType.PITCH, TokenType.PAN]:
            if self.check(func_type):
                # Check if it's a function call (followed by LPAREN)
                if self.peek().type == TokenType.LPAREN:
                    self.advance()
                    self.expect(TokenType.LPAREN, "Expected '('")
                    arg = self.parse_expression()
                    self.expect(TokenType.RPAREN, "Expected ')'")
                    return FunctionCall(func_name=func_type.name.lower(), args=[arg])
                else:
                    # Treat as variable reference
                    token = self.advance()
                    return VariableRef(name=token.value)
        
        if self.match(TokenType.ITEM):
            self.expect(TokenType.LPAREN, "Expected '('")
            index = self.parse_expression()
            self.match(TokenType.COMMA)
            if self.check(TokenType.IDENTIFIER) and self.current().value.lower() == 'of':
                self.advance()
            list_name = self.expect(TokenType.IDENTIFIER, "Expected list name").value
            self.expect(TokenType.RPAREN, "Expected ')'")
            return ListItemAccess(list_name=list_name, index=index)
        
        if self.match(TokenType.INDEX):
            self.expect(TokenType.LPAREN, "Expected '('")
            item = self.parse_expression()
            self.match(TokenType.COMMA)
            if self.check(TokenType.IDENTIFIER) and self.current().value.lower() in ('in', 'of'):
                self.advance()
            list_name = self.expect(TokenType.IDENTIFIER, "Expected list name").value
            self.expect(TokenType.RPAREN, "Expected ')'")
            return ListIndexOf(list_name=list_name, item=item)
        
        if self.match(TokenType.TOUCHING):
            self.expect(TokenType.LPAREN, "Expected '('")
            if self.check(TokenType.COLOR):
                color = self.advance().value
                self.expect(TokenType.RPAREN, "Expected ')'")
                return ReporterBlock(block_name='touching_color', fields={'COLOR': color})
            else:
                target = self.parse_expression()
                self.expect(TokenType.RPAREN, "Expected ')'")
                if isinstance(target, StringLiteral):
                    return ReporterBlock(block_name='touching', fields={'TOUCHINGOBJECTMENU': target.value})
                return ReporterBlock(block_name='touching', args=[target])
        
        # Identifiers (variables, reporters, etc.)
        if self.match(TokenType.IDENTIFIER):
            name = token.value
            
            # Check for special reporter names
            lower_name = name.lower()
            special_reporters = {
                'x_position': 'x_position',
                'y_position': 'y_position',
                'direction': 'direction',
                'costume': 'costume_number',
                'backdrop': 'backdrop_number',
                'size': 'size',
                'volume': 'volume',
                'answer': 'answer',
                'mousex': 'mouse_x',
                'mousey': 'mouse_y',
                'mousedown': 'mouse_down',
                'timer': 'timer',
                'dayssince2000': 'days_since_2000',
                'username': 'username',
                'current_year': ('current', {'CURRENTMENU': 'YEAR'}),
                'current_month': ('current', {'CURRENTMENU': 'MONTH'}),
                'current_date': ('current', {'CURRENTMENU': 'DATE'}),
                'current_day_of_week': ('current', {'CURRENTMENU': 'DAYOFWEEK'}),
                'current_hour': ('current', {'CURRENTMENU': 'HOUR'}),
                'current_minute': ('current', {'CURRENTMENU': 'MINUTE'}),
                'current_second': ('current', {'CURRENTMENU': 'SECOND'}),
                # TurboWarp extensions
                'is_turbowarp': 'is_turbowarp',
                'is_compiled': 'is_compiled',
                'is_fenced': 'is_fenced',
            }
            
            if lower_name in special_reporters:
                val = special_reporters[lower_name]
                if isinstance(val, tuple):
                    return ReporterBlock(block_name=val[0], fields=val[1])
                return ReporterBlock(block_name=val)
            
            # Regular variable reference
            return VariableRef(name=name)
        
        raise ParseError(f"Unexpected token: {token.type.name}", token)


def parse(source: str, filename: str = "<input>") -> Program:
    """Convenience function to parse source code."""
    lexer = Lexer(source, filename)
    tokens = lexer.tokenize()
    parser = Parser(tokens, filename)
    return parser.parse()
