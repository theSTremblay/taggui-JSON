from PySide6.QtGui import QIcon


from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, Union, Tuple, List

@dataclass
class Image:
    path: Path
    dimensions: Optional[Tuple[int, int]]
    tags: List[str] = field(default_factory=list)
    thumbnail: Optional[QIcon] = None