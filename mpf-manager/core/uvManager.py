"""Manager for building and running UV to manage the virtual 
Python/MPF Environments"""

#   uvManager - Responsible for managing virtual environments using uv
# 
#   Written by techWitchAstra
#
#   Code in this file may be adapted, re-written, or re-architected
#       from code from Claude.  None of the code in this file is a direct
#       result of AI agents, and has been overseen by a human by a human at all stages

from __future__ import annotations

# The following imports json, shell utility and sub process packages
# for later use
import json
import shutil
import subprocess

# Import the system path for usage
from pathlib import Path

# The following class helps process runtime errors related to UV
class UvNotFoundError(RuntimeError):
    pass