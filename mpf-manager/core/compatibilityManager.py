#   compatabilityManager - Responsible for finding the latest python
#       versions that are compatable with MPF, to help setup the virtual
#       environment.
# 
#   Written by techWitchAstra
#
#   Code in this file may be adapted, re-written, or re-architected
#       from code from Claude.  None of the code in this file is a direct
#       result of AI agents, and has been overseen by a human

from __future__ import annotations

# Importation of JSON, SSL, and URL library objects for retrieving the
#   package JSON to find the compatable python versions
import json
import ssl
import urllib.error
import urllib.request

# Importation of libraries to make callable objects and classes for data
from collections.abc import Callable
from dataclasses import dataclass

# Importation of two different options for SSL Certificates
import certifi
import truststore

from packaging.specifiers import InvalidSpecifier, SpecifierSet
from packaging.version import InvalidVersion, Version


# Definition of PYPI_URL to be called when retrieving the JSON for checking
PYPI_URL = "https://pypi.org/pypi/{package}/json"

PYTHON_VERSION_OPTIONS = ["3.8", "3.9", "3.10", "3.11", "3.12", "3.13", "3.14"]

# MPF Add-Ons that can be utilized alongside MPF's core framework
# Currently Supported (in Utility)
# - mpf-mc (Legacy Media Controller)
# - mpf-monitor (Tool for virtually interacting with a machine)
MPF_ADD_ONS = {
    "mpf-mc": "Legacy Media Controller for MPF versions 0.57 and earlier",
    "mpf-monitor": "Tool for virtually testing a MPF project" 
}
