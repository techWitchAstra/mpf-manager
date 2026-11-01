"""Light groups: named sets of a machine's lights, kept with the machine, for choosing many lights at once"""

#   lightGroups - Responsible for groups of lights the user names, such as
#       "left ramp" or "inserts", which are kept in the machine folder so they
#       travel with it, along with the groups MPF's light tags make
#
#   Written by techWitchAstra
#
#   Code in this file may be adapted, re-written, or re-architected
#       from code from Claude.  None of the code in this file is a direct
#       result of AI agents, and has been overseen by a human at all stages

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from mpfmanager.core import yamlInterfacer

# The following is where a machine's light groups are kept, in a folder of MPF-Manager's own in the machine folder
GROUPS_FOLDER = ".mpf-manager"
GROUPS_FILE = "light_groups.yaml"
GROUPS_HEADER = "# Light groups made in MPF-Manager's Show Manager, by name, with the lights in each\n"
# The following marks the groups MPF's light tags make, which are read from the machine's config and not changed
TAG_PREFIX = "tag: "


# The following is a group of lights, by name, in the order they were added
@dataclass
class LightGroup:
    """A named group of lights"""

    name: str
    lights: list[str] = field(default_factory=list)
    isTag: bool = False

    @property
    def label(self) -> str:
        return f"{TAG_PREFIX}{self.name}" if self.isTag else self.name


def groupsPath(machinePath: Path) -> Path:
    return machinePath / GROUPS_FOLDER / GROUPS_FILE


# The following reads a machine's light groups, in the order they were made, leaving out any that cannot be read
def loadLightGroups(machinePath: Path | None) -> list[LightGroup]:
    if machinePath is None:
        return []
    data = yamlInterfacer.loadYAML(groupsPath(machinePath))
    if not isinstance(data, dict):
        return []
    groups = []
    for name, lights in data.items():
        lightNames = [str(light) for light in lights] if isinstance(lights, list) else []
        groups.append(LightGroup(str(name), list(dict.fromkeys(lightNames))))
    return groups


# The following writes a machine's light groups, leaving the groups MPF's tags make out, as those are in its config
def saveLightGroups(machinePath: Path, groups: list[LightGroup]) -> None:
    data = {group.name: list(group.lights) for group in groups if not group.isTag}
    yamlInterfacer.writeYAML(data, groupsPath(machinePath), GROUPS_HEADER)


# The following makes a group for each of MPF's light tags, from each light's tags, e.g. gi or playfield
def tagGroups(lightTags: dict[str, set[str]]) -> list[LightGroup]:
    groups: dict[str, list[str]] = {}
    for lightName, tags in lightTags.items():
        for tag in tags:
            groups.setdefault(tag, []).append(lightName)
    return [LightGroup(tag, sorted(lights), isTag=True) for tag, lights in sorted(groups.items())]
