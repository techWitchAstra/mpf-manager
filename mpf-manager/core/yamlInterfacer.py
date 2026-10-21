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
from pathlib import Path
from typing import Any

# Importation of the ruamel.yaml library matching MPF
from ruamel.yaml import YAML

# The following function sets up the YAML intepreter to be used for
# reading yaml files for our needs.
def _yaml() -> YAML:

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

# The following function loads the yaml files
def loadYAML(filePath: Path) -> Any:

    # The following if statement checks to see if the file path exists
    if not filePath.exists():
        return None

    # If presuming all above if statements do not return true, then we
    # load up the yaml file
    with filePath.open("r",encoding="utf-8") as yamlFile:
        return _yaml().load(yamlFile)

# The following function writes the yaml files
def writeYAML(dataToWrite: Any, filePath: Path, headerString: str | None = None) -> None:
