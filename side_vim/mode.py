"""The vim modes."""

from enum import Enum


class Mode(Enum):
    NORMAL = "normal"
    INSERT = "insert"
    VISUAL = "visual"
    VISUAL_LINE = "visual line"
