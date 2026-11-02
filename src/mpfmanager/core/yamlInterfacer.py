"""Ruamel.yaml based yaml interpreter and associated functions"""

#   yamlInterfacer - Responsible for imporation and exportation of yaml
#       files and data as necessary to accomplish tasks in the application
#
#   Written by techWitchAstra
#
#   Code in this file may be adapted, re-written, or re-architected
#       from code from Claude.  None of the code in this file is a direct
#       result of AI agents, and has been overseen by a human at all stages

from __future__ import annotations

# Importation for paths as well as being able to import the Any type
import re
from pathlib import Path
from typing import Any

# Importation of the ruamel.yaml library matching MPF
from ruamel.yaml import YAML
from ruamel.yaml.comments import CommentedMap, CommentedSeq
from ruamel.yaml.error import CommentMark
from ruamel.yaml.tokens import CommentToken


# The following function sets up the YAML intepreter to be used for
# reading yaml files for our needs.
def _yaml() -> YAML:
    """Yaml Processor"""

    # Configuration of YAML processor, including type of yaml in relation
    # to comments, indentation settings for the yaml, preferences for
    # flow style, and line width.
    # For MPF we want to use round trip to preserve comment location,
    # default flow style off since it accepts multiple, and we want
    # to have a long width to allow for long single lines
    yamlInterpreter = YAML(typ="rt")
    yamlInterpreter.indent(mapping=2, sequence=4, offset=2)
    yamlInterpreter.default_flow_style = False
    yamlInterpreter.width = 4096
    return yamlInterpreter


# The following function sets up the YAML interpreter for writing MPF show files, which are a list of steps
# written from the start of the line as MPF's own shows are, e.g. "- duration: 1s"
def showYAML() -> YAML:
    """Yaml Processor for show files"""

    yamlInterpreter = _yaml()
    yamlInterpreter.indent(mapping=2, sequence=2, offset=0)
    return yamlInterpreter


# The following function loads the yaml files
def loadYAML(filePath: Path) -> Any:
    """Function for loading YAML files based on a filepath"""

    # The following if statement checks to see if the file path exists
    if not filePath.exists():
        return None

    # If presuming all above if statements do not return true, then we
    # load up the yaml file
    with filePath.open("r", encoding="utf-8") as yamlFile:
        return _yaml().load(yamlFile)


# The following function loads yaml files keeping every value as text
def loadYAMLText(filePath: Path) -> Any:
    """Function for loading YAML files with all values left as strings, based on a filepath"""

    # The following if statement checks to see if the file path exists
    if not filePath.exists():
        return None

    # The base loader keeps every value as a string, so colors such as 000000
    # and words such as on and off are not turned into numbers or booleans
    with filePath.open("r", encoding="utf-8") as yamlFile:
        return YAML(typ="base").load(yamlFile)


# The following matches the start of a top level section of a yaml file, e.g. "shows:"
_TOP_LEVEL_KEY = re.compile(r"^([A-Za-z_][\w-]*)\s*:")


# The following function loads only some top level sections of a yaml file, with all values left as strings.
# Reading just the sections needed is much faster for large config files, such as an MPF mode's slides and widgets
def loadYAMLTextSections(filePath: Path, sectionNames: set[str]) -> Any:
    """Function for loading only the named top level sections of a YAML file as text"""

    # The following if statement checks to see if the file path exists
    if not filePath.exists():
        return None

    # The following keeps the lines of the wanted sections, which run from their key to the next top level key
    keptLines: list[str] = []
    keepingSection = False
    for line in filePath.read_text(encoding="utf-8").splitlines():
        keyMatch = _TOP_LEVEL_KEY.match(line)
        if keyMatch:
            keepingSection = keyMatch.group(1) in sectionNames
        elif line.startswith(("---", "...")) or line[:1] not in ("", " ", "\t", "#", "-"):
            # Anything else at the start of a line, such as a document marker or quoted key, is not a wanted section,
            # while list items can start at the start of a line, as in a config: list
            keepingSection = False
        if keepingSection:
            keptLines.append(line)
    return YAML(typ="base").load("\n".join(keptLines)) or {}


# The following function writes the yaml files
def writeYAML(
    dataToWrite: Any, filePath: Path, headerString: str | None = None, yamlInterpreter: YAML | None = None
) -> None:
    """Function for writing YAML files based on data, a file path, a header string, and optionally the
    YAML processor to write with"""

    # The following checks to see if the parent directories exist,
    # and creates it if not
    filePath.parent.mkdir(parents=True, exist_ok=True)

    # The following creates a temporary file to work in
    tmpFile = filePath.with_suffix(filePath.suffix + ".tmp")

    # The following try attempts to write the data to the file
    try:
        # The following opens the temp file
        with tmpFile.open("w", encoding="utf-8") as fileObject:
            # The following checks if a header string exists
            if headerString:
                # If a header string did exist, it is written first
                fileObject.write(headerString.rstrip("\n") + "\n")

            # The YAML Data is then written to the file
            (yamlInterpreter or _yaml()).dump(dataToWrite, fileObject)

        # The temp file then is moved to be the actual file
        tmpFile.replace(filePath)

    # The following catches any exceptions and does not write them to
    # the file
    except BaseException:
        tmpFile.unlink(missing_ok=True)
        raise


# The following functions work with the comments ruamel.yaml keeps when it reads a file with round trip.  A comment is
# kept with the item before it: a comment at the end of a line is kept with that line's item, and comments on the
# lines after an item are kept with that same item, at the deepest last item under it.  So comments written between
# two steps of a show are kept with the last light (or other setting) of the step before


# The following returns where in a list or mapping an item's comment is kept
def _commentIndex(container: Any) -> int:
    return 0 if isinstance(container, CommentedSeq) else 2


def _isBlock(node: Any) -> bool:
    return isinstance(node, (CommentedMap, CommentedSeq)) and len(node) > 0 and not node.fa.flow_style()


# The following finds the deepest last item under an item, which is where comments after the item are kept
def _lastCommentSlot(container: Any, key: Any) -> tuple[Any, Any]:
    value = container[key]
    while _isBlock(value):
        container, key = value, (len(value) - 1 if isinstance(value, CommentedSeq) else list(value)[-1])
        value = container[key]
    return container, key


def _commentToken(container: Any, key: Any) -> CommentToken | None:
    entry = container.ca.items.get(key) if hasattr(container, "ca") else None
    index = _commentIndex(container)
    return entry[index] if entry and len(entry) > index else None


# The following returns the comments on the lines after an item, such as the comments above the next item
def followingComments(container: Any, key: Any) -> list[str]:
    """Function for listing the whole line comments that follow an item"""

    token = _commentToken(*_lastCommentSlot(container, key))
    return token.value.partition("\n")[2].splitlines(keepends=True) if token is not None else []


# The following takes away the comments on the lines after an item, and returns them, e.g. so they can be moved to
# wherever the item's place is taken.  A comment at the end of the item's line is left with the item
def takeFollowingComments(container: Any, key: Any) -> list[str]:
    """Function for taking the whole line comments that follow an item"""

    lines = followingComments(container, key)
    token = _commentToken(*_lastCommentSlot(container, key))
    if token is not None:
        token.value = token.value.partition("\n")[0] + "\n"
    return lines


# The following returns the comments of an item and everything under it, for an item that is being taken out, as
# whole line comments.  Comments at the ends of lines describe the lines taken out, so they are only kept if asked for
def itemComments(container: Any, key: Any, keepEndOfLine: bool) -> list[str]:
    """Function for listing the comments of an item and everything under it"""

    lines: list[str] = []
    token = _commentToken(container, key)
    if token is not None:
        endOfLine, _, following = token.value.partition("\n")
        if keepEndOfLine and endOfLine.strip():
            lines.append(endOfLine.strip() + "\n")
        lines += following.splitlines(keepends=True)
    value = container[key]
    for childKey in (
        range(len(value)) if isinstance(value, CommentedSeq) else value if isinstance(value, CommentedMap) else []
    ):
        lines += itemComments(value, childKey, keepEndOfLine)
    return lines


# The following adds whole line comments after an item, after any comments already there
def appendComments(container: Any, key: Any, lines: list[str]) -> None:
    """Function for adding whole line comments after an item"""

    if not lines:
        return
    slotContainer, slotKey = _lastCommentSlot(container, key)
    token = _commentToken(slotContainer, slotKey)
    if token is None:
        entry = slotContainer.ca.items.setdefault(slotKey, [None, None, None, None])
        entry[_commentIndex(slotContainer)] = CommentToken("\n" + "".join(lines), CommentMark(0), None)
        return
    token.value = (token.value if token.value.endswith("\n") else token.value + "\n") + "".join(lines)


# The following returns the comments written before the start of a list or mapping, such as a file's header
def startComments(node: Any) -> list[str]:
    """Function for listing the comments before a list or mapping"""

    comment = node.ca.comment if isinstance(node, (CommentedMap, CommentedSeq)) else None
    if not comment or len(comment) < 2 or not comment[1]:
        return []
    return [token.value for token in comment[1]]


# The following sets the comments written before the start of a list or mapping
def setStartComments(node: CommentedMap | CommentedSeq, lines: list[str]) -> None:
    """Function for setting the comments before a list or mapping"""

    tokens = [CommentToken(line.lstrip() if line.strip() else "\n", CommentMark(0), None) for line in lines]
    node.ca.comment = [None, tokens] if tokens else None


# The following sets the comments written on the lines before a key of a mapping, indented to the key
def setCommentsBefore(container: CommentedMap, key: Any, lines: list[str], indent: int) -> None:
    """Function for setting the comments before a key of a mapping"""

    tokens = [CommentToken(line.lstrip() if line.strip() else "\n", CommentMark(indent), None) for line in lines]
    entry = container.ca.items.setdefault(key, [None, None, None, None])
    entry[1] = tokens or None
