# Token types and lexer for Felis

from enum import Enum, auto
from dataclasses import dataclass
from typing import List, Optional, Any
import re


class TokenType(Enum):
    NUMBER = auto()
    STRING = auto()
    BOOLEAN = auto()
    COLOR = auto()
    IDENTIFIER = auto()
    
    # structure
    SPRITE = auto()
    STAGE = auto()
    COSTUMES = auto()
    SOUNDS = auto()
    DEFINE = auto()
    WARP = auto()
    
    # events
    ON = auto()
    FLAG = auto()
    KEY = auto()
    CLICKED = auto()
    BACKDROP = auto()
    LOUDNESS = auto()
    TIMER = auto()
    MESSAGE = auto()
    CLONE = auto()
    
    # control flow
    IF = auto()
    ELSE = auto()
    ELIF = auto()
    REPEAT = auto()
    FOREVER = auto()
    WHILE = auto()
    UNTIL = auto()
    FOR = auto()
    WAIT = auto()
    STOP = auto()
    RETURN = auto()
    
    # vars
    VAR = auto()
    CLOUD = auto()
    LIST = auto()
    SET = auto()
    CHANGE = auto()
    SHOW = auto()
    HIDE = auto()
    
    # motion
    MOVE = auto()
    TURN = auto()
    GOTO = auto()
    GLIDE = auto()
    POINT = auto()
    BOUNCE = auto()
    
    # looks
    SAY = auto()
    THINK = auto()
    SWITCH = auto()
    NEXT = auto()
    SIZE = auto()
    EFFECT = auto()
    CLEAR = auto()
    LAYER = auto()
    
    # sound
    PLAY = auto()
    START = auto()
    VOLUME = auto()
    PITCH = auto()
    PAN = auto()
    
    # pen
    PEN = auto()
    STAMP = auto()
    ERASE = auto()
    
    # music
    DRUM = auto()
    NOTE = auto()
    REST = auto()
    INSTRUMENT = auto()
    TEMPO = auto()
    
    # sensing
    TOUCHING = auto()
    ASK = auto()
    RESET = auto()
    DRAG = auto()
    
    # operators
    AND = auto()
    OR = auto()
    NOT = auto()
    MOD = auto()
    ROUND = auto()
    ABS = auto()
    FLOOR = auto()
    CEIL = auto()
    SQRT = auto()
    SIN = auto()
    COS = auto()
    TAN = auto()
    ASIN = auto()
    ACOS = auto()
    ATAN = auto()
    LN = auto()
    LOG = auto()
    ANTILN = auto()
    ANTILOG = auto()
    LENGTH = auto()
    LETTER = auto()
    CONTAINS = auto()
    JOIN = auto()
    RANDOM = auto()
    
    # misc
    BROADCAST = auto()
    CREATE = auto()
    DELETE = auto()
    ADD = auto()
    INSERT = auto()
    REPLACE = auto()
    ITEM = auto()
    INDEX = auto()
    LAST = auto()
    
    # imports
    IMPORT = auto()
    FROM = auto()
    AS = auto()
    EXPORT = auto()
    LIBRARY = auto()
    
    # symbols
    PLUS = auto()
    MINUS = auto()
    STAR = auto()
    SLASH = auto()
    PERCENT = auto()
    CARET = auto()
    EQ = auto()
    NEQ = auto()
    LT = auto()
    GT = auto()
    LTE = auto()
    GTE = auto()
    ASSIGN = auto()
    
    # delimiters
    LPAREN = auto()
    RPAREN = auto()
    LBRACE = auto()
    RBRACE = auto()
    LBRACKET = auto()
    RBRACKET = auto()
    COMMA = auto()
    COLON = auto()
    SEMICOLON = auto()
    DOT = auto()
    ARROW = auto()
    AT = auto()
    HASH = auto()
    NEWLINE = auto()
    EOF = auto()
    COMMENT = auto()
    EXCLUDED_COMMENT = auto()  # Comments that don't appear in compiled Scratch project


@dataclass
class Token:
    type: TokenType
    value: Any
    line: int
    column: int
    
    def __repr__(self):
        return f"Token({self.type.name}, {self.value!r}, {self.line}:{self.column})"


class LexerError(Exception):
    def __init__(self, message: str, line: int, column: int, source: str = None, filename: str = "<input>", suggestion: str = None):
        self.message = message
        self.line = line
        self.column = column
        self.source = source
        self.filename = filename
        self.suggestion = suggestion
        super().__init__(self._fmt())
    
    def _fmt(self) -> str:
        out = [f"\n\033[1;31mLexer Error\033[0m in {self.filename}:{self.line}:{self.column}"]
        out.append(f"  {self.message}")
        
        if self.source:
            src_lines = self.source.split('\n')
            if 0 < self.line <= len(src_lines):
                start = max(0, self.line - 2)
                end = min(len(src_lines), self.line + 1)
                out.append("")
                for i in range(start, end):
                    ln = i + 1
                    pfx = "\033[1;31m>\033[0m " if ln == self.line else "  "
                    out.append(f"{pfx}{ln:4d} | {src_lines[i]}")
                    if ln == self.line:
                        out.append(" " * (7 + self.column - 1) + "\033[1;31m^\033[0m")
        
        if self.suggestion:
            out.append(f"\n\033[1;33mHint:\033[0m {self.suggestion}")
        
        return "\n".join(out)


class Lexer:
    KEYWORDS = {
        'sprite': TokenType.SPRITE,
        'stage': TokenType.STAGE,
        'costumes': TokenType.COSTUMES,
        'sounds': TokenType.SOUNDS,
        'define': TokenType.DEFINE,
        'warp': TokenType.WARP,
        'on': TokenType.ON,
        'flag': TokenType.FLAG,
        'key': TokenType.KEY,
        'clicked': TokenType.CLICKED,
        'backdrop': TokenType.BACKDROP,
        'loudness': TokenType.LOUDNESS,
        'timer': TokenType.TIMER,
        'message': TokenType.MESSAGE,
        'clone': TokenType.CLONE,
        'if': TokenType.IF,
        'else': TokenType.ELSE,
        'elif': TokenType.ELIF,
        'repeat': TokenType.REPEAT,
        'forever': TokenType.FOREVER,
        'while': TokenType.WHILE,
        'until': TokenType.UNTIL,
        'for': TokenType.FOR,
        'wait': TokenType.WAIT,
        'stop': TokenType.STOP,
        'return': TokenType.RETURN,
        'var': TokenType.VAR,
        'cloud': TokenType.CLOUD,
        'list': TokenType.LIST,
        'set': TokenType.SET,
        'change': TokenType.CHANGE,
        'show': TokenType.SHOW,
        'hide': TokenType.HIDE,
        'move': TokenType.MOVE,
        'turn': TokenType.TURN,
        'goto': TokenType.GOTO,
        'glide': TokenType.GLIDE,
        'point': TokenType.POINT,
        'bounce': TokenType.BOUNCE,
        'say': TokenType.SAY,
        'think': TokenType.THINK,
        'switch': TokenType.SWITCH,
        'next': TokenType.NEXT,
        'size': TokenType.SIZE,
        'effect': TokenType.EFFECT,
        'clear': TokenType.CLEAR,
        'layer': TokenType.LAYER,
        'play': TokenType.PLAY,
        'start': TokenType.START,
        'volume': TokenType.VOLUME,
        'pitch': TokenType.PITCH,
        'pan': TokenType.PAN,
        'pen': TokenType.PEN,
        'stamp': TokenType.STAMP,
        'erase': TokenType.ERASE,
        'drum': TokenType.DRUM,
        'note': TokenType.NOTE,
        'rest': TokenType.REST,
        'instrument': TokenType.INSTRUMENT,
        'tempo': TokenType.TEMPO,
        'touching': TokenType.TOUCHING,
        'ask': TokenType.ASK,
        'reset': TokenType.RESET,
        'drag': TokenType.DRAG,
        'and': TokenType.AND,
        'or': TokenType.OR,
        'not': TokenType.NOT,
        'mod': TokenType.MOD,
        'round': TokenType.ROUND,
        'abs': TokenType.ABS,
        'floor': TokenType.FLOOR,
        'ceil': TokenType.CEIL,
        'sqrt': TokenType.SQRT,
        'sin': TokenType.SIN,
        'cos': TokenType.COS,
        'tan': TokenType.TAN,
        'asin': TokenType.ASIN,
        'acos': TokenType.ACOS,
        'atan': TokenType.ATAN,
        'ln': TokenType.LN,
        'log': TokenType.LOG,
        'antiln': TokenType.ANTILN,
        'antilog': TokenType.ANTILOG,
        'length': TokenType.LENGTH,
        'letter': TokenType.LETTER,
        'contains': TokenType.CONTAINS,
        'join': TokenType.JOIN,
        'random': TokenType.RANDOM,
        'broadcast': TokenType.BROADCAST,
        'create': TokenType.CREATE,
        'delete': TokenType.DELETE,
        'add': TokenType.ADD,
        'insert': TokenType.INSERT,
        'replace': TokenType.REPLACE,
        'item': TokenType.ITEM,
        'index': TokenType.INDEX,
        'last': TokenType.LAST,
        'import': TokenType.IMPORT,
        'from': TokenType.FROM,
        'as': TokenType.AS,
        'export': TokenType.EXPORT,
        'library': TokenType.LIBRARY,
        'true': TokenType.BOOLEAN,
        'false': TokenType.BOOLEAN,
    }
    
    def __init__(self, source: str, filename: str = "<input>"):
        self.source = source
        self.filename = filename
        self.pos = 0
        self.line = 1
        self.column = 1
        self.tokens: List[Token] = []
        
    def current_char(self) -> Optional[str]:
        if self.pos >= len(self.source):
            return None
        return self.source[self.pos]
    
    def peek(self, offset: int = 1) -> Optional[str]:
        pos = self.pos + offset
        if pos >= len(self.source):
            return None
        return self.source[pos]
    
    def advance(self) -> Optional[str]:
        char = self.current_char()
        self.pos += 1
        if char == '\n':
            self.line += 1
            self.column = 1
        else:
            self.column += 1
        return char
    
    def skip_whitespace(self):
        while self.current_char() and self.current_char() in ' \t\r':
            self.advance()
    
    def skip_comment(self):
        if self.current_char() == '/' and self.peek() == '/':
            while self.current_char() and self.current_char() != '\n':
                self.advance()
        elif self.current_char() == '/' and self.peek() == '*':
            self.advance()  # skip /
            self.advance()  # skip *
            while self.current_char():
                if self.current_char() == '*' and self.peek() == '/':
                    self.advance()  # skip *
                    self.advance()  # skip /
                    break
                self.advance()
        elif self.current_char() == '#':
            while self.current_char() and self.current_char() != '\n':
                self.advance()
    
    def read_comment(self) -> Optional[Token]:
        """Read a comment and return it as a token instead of skipping.
        
        Comment types:
        - // comment     -> COMMENT (shows in Scratch)
        - /* comment */  -> COMMENT (shows in Scratch, multi-line)
        - # comment      -> COMMENT (shows in Scratch)
        - /// comment    -> EXCLUDED_COMMENT (doesn't show in Scratch)
        - //* comment */ -> EXCLUDED_COMMENT (doesn't show in Scratch, multi-line)
        """
        start_line = self.line
        start_col = self.column
        
        if self.current_char() == '/' and self.peek() == '/':
            self.advance()  # skip first /
            self.advance()  # skip second /
            
            # Check for excluded comment (///)
            is_excluded = self.current_char() == '/'
            if is_excluded:
                self.advance()  # skip third /
            
            # Skip optional leading space
            if self.current_char() == ' ':
                self.advance()
            
            comment_text = ""
            while self.current_char() and self.current_char() != '\n':
                comment_text += self.current_char()
                self.advance()
            
            token_type = TokenType.EXCLUDED_COMMENT if is_excluded else TokenType.COMMENT
            return Token(token_type, comment_text.rstrip(), start_line, start_col)
            
        elif self.current_char() == '#':
            self.advance()  # skip #
            
            # Check for excluded comment (##)
            is_excluded = self.current_char() == '#'
            if is_excluded:
                self.advance()  # skip second #
            
            # Skip optional leading space
            if self.current_char() == ' ':
                self.advance()
            
            comment_text = ""
            while self.current_char() and self.current_char() != '\n':
                comment_text += self.current_char()
                self.advance()
            
            token_type = TokenType.EXCLUDED_COMMENT if is_excluded else TokenType.COMMENT
            return Token(token_type, comment_text.rstrip(), start_line, start_col)
            
        elif self.current_char() == '/' and self.peek() == '*':
            self.advance()  # skip /
            self.advance()  # skip *
            
            # Check for excluded comment (/**)
            is_excluded = self.current_char() == '*'
            if is_excluded:
                self.advance()  # skip second *
                # Handle edge case: /***/ is just an excluded empty comment
                if self.current_char() == '/':
                    self.advance()
                    return Token(TokenType.EXCLUDED_COMMENT, "", start_line, start_col)
            
            comment_text = ""
            while self.current_char():
                if self.current_char() == '*' and self.peek() == '/':
                    self.advance()  # skip *
                    self.advance()  # skip /
                    break
                comment_text += self.current_char()
                self.advance()
            
            token_type = TokenType.EXCLUDED_COMMENT if is_excluded else TokenType.COMMENT
            return Token(token_type, comment_text.strip(), start_line, start_col)
        return None
    
    def read_string(self) -> Token:
        quote = self.current_char()
        start_line = self.line
        start_col = self.column
        self.advance()  # skip opening quote
        
        value = ""
        while self.current_char() and self.current_char() != quote:
            if self.current_char() == '\\':
                self.advance()
                escape_char = self.current_char()
                if escape_char == 'n':
                    value += '\n'
                elif escape_char == 't':
                    value += '\t'
                elif escape_char == 'r':
                    value += '\r'
                elif escape_char == '\\':
                    value += '\\'
                elif escape_char == quote:
                    value += quote
                else:
                    value += escape_char
                self.advance()
            else:
                value += self.current_char()
                self.advance()
        
        if not self.current_char():
            raise LexerError(
                "Unterminated string", 
                start_line, start_col,
                source=self.source,
                filename=self.filename,
                suggestion=f"Add a closing {quote} to complete the string"
            )
        
        self.advance()  # skip closing quote
        return Token(TokenType.STRING, value, start_line, start_col)
    
    def read_number(self) -> Token:
        start_line = self.line
        start_col = self.column
        value = ""
        
        # Handle negative numbers
        if self.current_char() == '-':
            value += self.advance()
        
        while self.current_char() and (self.current_char().isdigit() or self.current_char() == '.'):
            if self.current_char() == '.' and '.' in value:
                break
            value += self.advance()
        
        # Scientific notation
        if self.current_char() and self.current_char().lower() == 'e':
            value += self.advance()
            if self.current_char() and self.current_char() in '+-':
                value += self.advance()
            while self.current_char() and self.current_char().isdigit():
                value += self.advance()
        
        num_value = float(value) if '.' in value or 'e' in value.lower() else int(value)
        return Token(TokenType.NUMBER, num_value, start_line, start_col)
    
    def read_identifier(self) -> Token:
        start_line = self.line
        start_col = self.column
        value = ""
        
        while self.current_char() and (self.current_char().isalnum() or self.current_char() == '_'):
            value += self.advance()
        
        # Check if it's a keyword
        lower_value = value.lower()
        if lower_value in self.KEYWORDS:
            token_type = self.KEYWORDS[lower_value]
            if token_type == TokenType.BOOLEAN:
                return Token(token_type, lower_value == 'true', start_line, start_col)
            return Token(token_type, value, start_line, start_col)
        
        return Token(TokenType.IDENTIFIER, value, start_line, start_col)
    
    def read_color(self) -> Token:
        start_line = self.line
        start_col = self.column
        self.advance()  # skip #
        
        value = ""
        while self.current_char() and self.current_char() in '0123456789abcdefABCDEF':
            value += self.advance()
        
        if len(value) not in (3, 6, 8):
            raise LexerError(
                f"Invalid color code: #{value}", 
                start_line, start_col,
                source=self.source,
                filename=self.filename,
                suggestion="Color codes must be 3 (RGB), 6 (RRGGBB), or 8 (RRGGBBAA) hex digits. Example: #ff0000"
            )
        
        return Token(TokenType.COLOR, f"#{value}", start_line, start_col)
    
    def tokenize(self) -> List[Token]:
        while self.current_char():
            # Skip whitespace (but not newlines)
            self.skip_whitespace()
            
            if not self.current_char():
                break
            
            char = self.current_char()
            start_line = self.line
            start_col = self.column
            
            # Comments - capture them as tokens instead of skipping
            if char == '/' and self.peek() in '/*':
                comment_token = self.read_comment()
                if comment_token:
                    self.tokens.append(comment_token)
                continue
            if char == '#' and not (self.peek() and self.peek() in '0123456789abcdefABCDEF'):
                comment_token = self.read_comment()
                if comment_token:
                    self.tokens.append(comment_token)
                continue
            
            # Newlines
            if char == '\n':
                self.tokens.append(Token(TokenType.NEWLINE, '\n', start_line, start_col))
                self.advance()
                continue
            
            # Strings
            if char in '"\'':
                self.tokens.append(self.read_string())
                continue
            
            # Numbers
            if char.isdigit() or (char == '-' and self.peek() and self.peek().isdigit()):
                self.tokens.append(self.read_number())
                continue
            
            # Colors (hex)
            if char == '#' and self.peek() and self.peek() in '0123456789abcdefABCDEF':
                self.tokens.append(self.read_color())
                continue
            
            # Identifiers and keywords
            if char.isalpha() or char == '_':
                self.tokens.append(self.read_identifier())
                continue
            
            # Two-character operators
            two_char = char + (self.peek() or '')
            if two_char == '==':
                self.advance()
                self.advance()
                self.tokens.append(Token(TokenType.EQ, '==', start_line, start_col))
                continue
            if two_char == '!=':
                self.advance()
                self.advance()
                self.tokens.append(Token(TokenType.NEQ, '!=', start_line, start_col))
                continue
            if two_char == '<=':
                self.advance()
                self.advance()
                self.tokens.append(Token(TokenType.LTE, '<=', start_line, start_col))
                continue
            if two_char == '>=':
                self.advance()
                self.advance()
                self.tokens.append(Token(TokenType.GTE, '>=', start_line, start_col))
                continue
            if two_char == '->':
                self.advance()
                self.advance()
                self.tokens.append(Token(TokenType.ARROW, '->', start_line, start_col))
                continue
            
            # single char tokens
            SINGLE = {
                '+': TokenType.PLUS, '-': TokenType.MINUS, '*': TokenType.STAR, '/': TokenType.SLASH,
                '%': TokenType.PERCENT, '^': TokenType.CARET, '<': TokenType.LT, '>': TokenType.GT,
                '=': TokenType.ASSIGN, '(': TokenType.LPAREN, ')': TokenType.RPAREN,
                '{': TokenType.LBRACE, '}': TokenType.RBRACE, '[': TokenType.LBRACKET,
                ']': TokenType.RBRACKET, ',': TokenType.COMMA, ':': TokenType.COLON,
                ';': TokenType.SEMICOLON, '.': TokenType.DOT, '@': TokenType.AT,
            }
            
            if char in SINGLE:
                self.advance()
                self.tokens.append(Token(SINGLE[char], char, start_line, start_col))
                continue
            
            # common mistakes
            hint = None
            if char == '`': hint = "Use ' or \" for strings"
            elif char == '&': hint = "Use 'and' for logical AND"
            elif char == '|': hint = "Use 'or' for logical OR"
            elif char == '!': hint = "Use 'not' for NOT, or '!=' for not-equal"
            
            raise LexerError(f"Unexpected char: {char!r}", start_line, start_col,
                           source=self.source, filename=self.filename, suggestion=hint)
        
        self.tokens.append(Token(TokenType.EOF, None, self.line, self.column))
        return self.tokens


def tokenize(source: str, filename: str = "<input>") -> List[Token]:
    return Lexer(source, filename).tokenize()
