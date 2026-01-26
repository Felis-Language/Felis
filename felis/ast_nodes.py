# AST node types for Felis

from dataclasses import dataclass, field
from typing import List, Optional, Any, Union
from enum import Enum, auto


class NodeType(Enum):
    PROGRAM = auto()
    SPRITE = auto()
    STAGE = auto()
    COSTUME = auto()
    SOUND = auto()
    VARIABLE = auto()
    LIST_VAR = auto()
    CUSTOM_BLOCK = auto()
    EVENT_HANDLER = auto()
    BLOCK_STATEMENT = auto()
    EXPRESSION = auto()
    IMPORT = auto()
    EXPORT = auto()
    LIBRARY = auto()


@dataclass(kw_only=True)
class Position:
    line: int
    column: int
    filename: str = "<input>"


@dataclass(kw_only=True)
class ASTNode:
    position: Optional[Position] = None


# --- program structure ---

@dataclass(kw_only=True)
class Program(ASTNode):
    sprites: List['Sprite'] = field(default_factory=list)
    stage: Optional['Stage'] = None
    imports: List['ImportStatement'] = field(default_factory=list)
    exports: List['ExportStatement'] = field(default_factory=list)
    is_library: bool = False
    library_name: Optional[str] = None


@dataclass(kw_only=True)
class Sprite(ASTNode):
    name: str
    display_name: Optional[str] = None 
    costumes: List['Costume'] = field(default_factory=list)
    sounds: List['Sound'] = field(default_factory=list)
    variables: List['VariableDecl'] = field(default_factory=list)
    lists: List['ListDecl'] = field(default_factory=list)
    custom_blocks: List['CustomBlock'] = field(default_factory=list)
    event_handlers: List['EventHandler'] = field(default_factory=list)
    x: float = 0
    y: float = 0
    size: float = 100
    direction: float = 90
    visible: bool = True
    rotation_style: str = "all around"
    layer_order: int = 1


@dataclass(kw_only=True)
class Stage(ASTNode):
    backdrops: List['Costume'] = field(default_factory=list)
    sounds: List['Sound'] = field(default_factory=list)
    variables: List['VariableDecl'] = field(default_factory=list)
    lists: List['ListDecl'] = field(default_factory=list)
    custom_blocks: List['CustomBlock'] = field(default_factory=list)
    event_handlers: List['EventHandler'] = field(default_factory=list)
    tempo: int = 60
    video_transparency: int = 50
    video_state: str = "off"


@dataclass(kw_only=True)
class Costume(ASTNode):
    name: str
    file: Optional[str] = None
    rotation_center_x: Optional[float] = None  # inferred from asset if None
    rotation_center_y: Optional[float] = None


@dataclass(kw_only=True)
class Sound(ASTNode):
    """A sound asset."""
    name: str
    file: Optional[str] = None


# --- statements ---

@dataclass(kw_only=True)
class Statement(ASTNode):
    comment: Optional[str] = None 
    preceding_comments: List[str] = field(default_factory=list)


@dataclass(kw_only=True)
class VariableDecl(Statement):
    name: str
    display_name: Optional[str] = None
    initial_value: Any = 0
    is_local: bool = True
    is_cloud: bool = False


@dataclass(kw_only=True)
class ListDecl(Statement):
    name: str
    display_name: Optional[str] = None 
    initial_values: List[Any] = field(default_factory=list)
    is_local: bool = True


@dataclass(kw_only=True)
class CustomBlockParam(ASTNode):
    name: str
    display_name: Optional[str] = None 
    param_type: str = "string"


@dataclass(kw_only=True)
class CustomBlock(ASTNode):
    name: str
    display_name: Optional[str] = None 
    params: List[CustomBlockParam] = field(default_factory=list)
    body: List['Statement'] = field(default_factory=list)
    warp: bool = False  # run without screen refresh
    comment: Optional[str] = None
    preceding_comments: List[str] = field(default_factory=list)


class EventType(Enum):
    FLAG_CLICKED = auto()
    KEY_PRESSED = auto()
    SPRITE_CLICKED = auto()
    STAGE_CLICKED = auto()
    BACKDROP_SWITCHES = auto()
    LOUDNESS_GREATER = auto()
    TIMER_GREATER = auto()
    MESSAGE_RECEIVED = auto()
    CLONE_STARTS = auto()


@dataclass(kw_only=True)
class EventHandler(ASTNode):
    event_type: EventType
    event_param: Optional[Any] = None
    body: List['Statement'] = field(default_factory=list)
    comment: Optional[str] = None
    preceding_comments: List[str] = field(default_factory=list)


@dataclass(kw_only=True)
class BlockCall(Statement):
    block_name: str
    args: List['Expression'] = field(default_factory=list)
    fields: dict = field(default_factory=dict)


@dataclass(kw_only=True)
class IfStatement(Statement):
    condition: 'Expression'
    then_body: List[Statement] = field(default_factory=list)
    else_body: List[Statement] = field(default_factory=list)


@dataclass(kw_only=True)
class RepeatStatement(Statement):
    count: 'Expression'
    body: List[Statement] = field(default_factory=list)


@dataclass(kw_only=True)
class ForeverStatement(Statement):
    body: List[Statement] = field(default_factory=list)


@dataclass(kw_only=True)
class WhileStatement(Statement):
    condition: 'Expression'
    body: List[Statement] = field(default_factory=list)
    is_until: bool = False


@dataclass(kw_only=True)
class WaitStatement(Statement):
    duration: 'Expression'


@dataclass(kw_only=True)
class WaitUntilStatement(Statement):
    condition: 'Expression'


@dataclass(kw_only=True)
class StopStatement(Statement):
    stop_option: str = "all"


@dataclass(kw_only=True)
class ReturnStatement(Statement):
    value: Optional['Expression'] = None


@dataclass(kw_only=True)
class SetVariable(Statement):
    var_name: str
    value: 'Expression'


@dataclass(kw_only=True)
class ChangeVariable(Statement):
    var_name: str
    value: 'Expression'


@dataclass(kw_only=True)
class ShowVariable(Statement):
    var_name: str


@dataclass(kw_only=True)
class HideVariable(Statement):
    var_name: str


@dataclass(kw_only=True)
class ListOperation(Statement):
    operation: str  # add, delete, deleteAll, insert, replace
    list_name: str
    value: Optional['Expression'] = None
    index: Optional['Expression'] = None


@dataclass(kw_only=True)
class ShowList(Statement):
    list_name: str


@dataclass(kw_only=True)
class HideList(Statement):
    list_name: str


# --- expressions ---

@dataclass(kw_only=True)
class Expression(ASTNode):
    pass


@dataclass(kw_only=True)
class NumberLiteral(Expression):
    value: float


@dataclass(kw_only=True)
class StringLiteral(Expression):
    value: str


@dataclass(kw_only=True)
class BooleanLiteral(Expression):
    value: bool


@dataclass(kw_only=True)
class ColorLiteral(Expression):
    value: str


@dataclass(kw_only=True)
class VariableRef(Expression):
    name: str


@dataclass(kw_only=True)
class ListRef(Expression):
    name: str


@dataclass(kw_only=True)
class ListItemAccess(Expression):
    list_name: str
    index: Expression


@dataclass(kw_only=True)
class ListLength(Expression):
    list_name: str


@dataclass(kw_only=True)
class ListContains(Expression):
    list_name: str
    item: Expression


@dataclass(kw_only=True)
class ListIndexOf(Expression):
    list_name: str
    item: Expression


@dataclass(kw_only=True)
class BinaryOp(Expression):
    operator: str
    left: Expression
    right: Expression


@dataclass(kw_only=True)
class UnaryOp(Expression):
    operator: str
    operand: Expression


@dataclass(kw_only=True)
class FunctionCall(Expression):
    func_name: str
    args: List[Expression] = field(default_factory=list)


@dataclass(kw_only=True)
class FieldValue(Expression):
    field_name: str
    value: Any


@dataclass(kw_only=True)
class ReporterBlock(Expression):
    block_name: str
    args: List[Expression] = field(default_factory=list)
    fields: dict = field(default_factory=dict)


# --- imports/exports ---

@dataclass(kw_only=True)
class ImportStatement(ASTNode):
    library_path: str
    items: List[str] = field(default_factory=list)
    alias: Optional[str] = None


@dataclass(kw_only=True)
class ExportStatement(ASTNode):
    items: List[str] = field(default_factory=list)


@dataclass(kw_only=True)
class LibraryDecl(ASTNode):
    name: str
