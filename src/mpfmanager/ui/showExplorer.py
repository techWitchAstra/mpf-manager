"""Show explorer: the show viewer's list of shows, laid out as the folders and files they are in"""

#   showExplorer - Responsible for the tree of show files in the show viewer,
#       with a folder for each folder of the machine that holds shows, a file
#       for each show or config file, and the shows in each file, so it can
#       be seen where each show is kept
#
#   Written by techWitchAstra
#
#   Code in this file may be adapted, re-written, or re-architected
#       from code from Claude.  None of the code in this file is a direct
#       result of AI agents, and has been overseen by a human at all stages

from __future__ import annotations

from pathlib import Path
from typing import Any

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QPalette
from PySide6.QtWidgets import QStyle, QTreeWidget, QTreeWidgetItem, QTreeWidgetItemIterator, QWidget

from mpfmanager.ui.ribbon import symbolIcon

# The following are the data roles of a show's item: the show, the key its edits are kept by, and its label without
# the mark for changes not saved.  Folders and files keep their path in the folder role, and have no show
SHOW_ROLE = Qt.ItemDataRole.UserRole
KEY_ROLE = Qt.ItemDataRole.UserRole + 1
LABEL_ROLE = Qt.ItemDataRole.UserRole + 2
FOLDER_ROLE = Qt.ItemDataRole.UserRole + 3
FILE_ROLE = Qt.ItemDataRole.UserRole + 4

# The following is the folder that files opened from outside the machine are listed under
OTHER_FILES = "Other files"


# The following is the tree of show files.  A file holding one show named after the file is listed as just that show,
# and a file holding other shows, such as a config file, is listed with its shows under it
class ShowExplorer(QTreeWidget):
    showChanged = Signal()

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setHeaderHidden(True)
        self.setUniformRowHeights(True)
        self.setIndentation(14)
        self.machinePath: Path | None = None
        self.collapsedFolders: set[str] = set()
        self._nodes: dict[str, QTreeWidgetItem] = {}
        self._loneShows: dict[str, QTreeWidgetItem] = {}
        self._lastShow: QTreeWidgetItem | None = None
        self._keptFolders: set[str] = set()
        self.currentItemChanged.connect(self._currentChanged)
        self.itemCollapsed.connect(lambda item: self.collapsedFolders.add(item.data(0, FOLDER_ROLE)))
        self.itemExpanded.connect(lambda item: self.collapsedFolders.discard(item.data(0, FOLDER_ROLE)))
        style = self.style()
        self.folderIcon = style.standardIcon(QStyle.StandardPixmap.SP_DirIcon)
        self.fileIcon = style.standardIcon(QStyle.StandardPixmap.SP_FileIcon)
        self.showIcon = symbolIcon("✦")

    # The following empties the tree, ready for the shows of a machine folder
    def clearShows(self, machinePath: Path | None) -> None:
        self.machinePath = machinePath
        self._keptFolders: set[str] = set()
        self._nodes.clear()
        self._loneShows.clear()
        self._lastShow = None
        self.clear()

    # The following lists a show under its file, making the folders and file it is in
    def addShow(self, showFile: Path, show: Any, label: str, key: str) -> QTreeWidgetItem:
        item = QTreeWidgetItem([label])
        item.setIcon(0, self.showIcon)
        item.setToolTip(0, str(showFile))
        item.setData(0, SHOW_ROLE, show)
        item.setData(0, KEY_ROLE, key)
        item.setData(0, LABEL_ROLE, label)
        self._placeShow(item, showFile, getattr(show, "name", ""))
        return item

    # The following moves a show to the place of another file, such as when it is saved as a new file
    def moveShow(self, item: QTreeWidgetItem, showFile: Path) -> None:
        wasCurrent = self.currentShowItem() is item
        self.blockSignals(True)
        self._detach(item)
        item.setToolTip(0, str(showFile))
        show = item.data(0, SHOW_ROLE)
        self._placeShow(item, showFile, getattr(show, "name", ""))
        if wasCurrent:
            self.setCurrentItem(item)
        self.blockSignals(False)

    # The following lists a folder of the machine, which stays listed whether or not it has shows, so the machine's
    # folders can be seen, and a show made in one of them.  Folders without shows are drawn faintly
    def addFolder(self, folder: Path) -> QTreeWidgetItem | None:
        node = self._folderNode(folder)
        path = folder
        while node is not None:
            self._keptFolders.add(str(path))
            if node.data(0, SHOW_ROLE) is None and not self._hasShows(node):
                node.setForeground(0, self.palette().brush(QPalette.ColorRole.PlaceholderText))
                node.setToolTip(0, f"{path}\nNo shows in this folder yet")
            node, path = node.parent(), path.parent
        return self._nodes.get(str(folder))

    def _hasShows(self, node: QTreeWidgetItem) -> bool:
        for index in range(node.childCount()):
            child = node.child(index)
            if child is not None and (child.data(0, SHOW_ROLE) is not None or self._hasShows(child)):
                return True
        return False

    # The following returns the folder chosen in the tree, or the folder of the show chosen, e.g. to make a new show in
    def currentFolder(self) -> Path | None:
        item = self.currentItem()
        if item is None:
            return None
        if item.data(0, SHOW_ROLE) is not None:
            return Path(item.toolTip(0)).parent
        key = item.data(0, FOLDER_ROLE)
        if key is None or key == OTHER_FILES:
            return None
        path = Path(key)
        return path.parent if item.data(0, FILE_ROLE) else path

    # The following takes a show out of the tree, along with folders and files it leaves empty
    def removeShow(self, item: QTreeWidgetItem) -> None:
        self.blockSignals(True)
        self._detach(item)
        self.blockSignals(False)
        if self._lastShow is item:
            self._lastShow = None

    # The following returns the shows listed for a file
    def showItemsOfFile(self, showFile: Path) -> list[QTreeWidgetItem]:
        return [item for item in self.showItems() if item.toolTip(0) == str(showFile)]

    # The following returns the shows, in the order they are listed
    def showItems(self) -> list[QTreeWidgetItem]:
        items = []
        iterator = QTreeWidgetItemIterator(self)
        while (item := iterator.value()) is not None:
            if item.data(0, SHOW_ROLE) is not None:
                items.append(item)
            iterator += 1
        return items

    # The following returns the show chosen.  Choosing a folder or file, e.g. to fold it, keeps the show chosen before
    def currentShowItem(self) -> QTreeWidgetItem | None:
        current = self.currentItem()
        if current is not None and current.data(0, SHOW_ROLE) is not None:
            return current
        return self._lastShow

    # The following chooses a show, telling the window unless it is filling the tree
    def selectShowItem(self, item: QTreeWidgetItem, notify: bool = True) -> None:
        if not notify:
            self._lastShow = item
        self.blockSignals(not notify)
        self.setCurrentItem(item)
        self.blockSignals(False)

    def _currentChanged(self, current: QTreeWidgetItem | None, _previous: QTreeWidgetItem | None) -> None:
        if current is not None and current.data(0, SHOW_ROLE) is not None and current is not self._lastShow:
            self._lastShow = current
            self.showChanged.emit()

    # The following places a show's item: on its own where its file holds just it, or under its file
    def _placeShow(self, item: QTreeWidgetItem, showFile: Path, showName: str) -> None:
        folderNode = self._folderNode(showFile.parent)
        fileKey = str(showFile)
        fileNode = self._nodes.get(fileKey)
        if fileNode is None and showName == showFile.stem and fileKey not in self._loneShows:
            self._addFileChild(folderNode, item, showFile)
            self._loneShows[fileKey] = item
            self._showFolderHasShows(folderNode)
            return
        if fileNode is None:
            fileNode = self._makeNode(folderNode, showFile.name, fileKey, self.fileIcon, showFile)
            # A show listed on its own for the file moves under the file now that the file has more shows
            loneShow = self._loneShows.get(fileKey)
            if loneShow is not None:
                self._detach(loneShow)
                fileNode.addChild(loneShow)
        fileNode.addChild(item)
        fileNode.setExpanded(fileKey not in self.collapsedFolders)
        self._showFolderHasShows(fileNode)

    # The following draws a folder that now has a show as usual, along with the folders it is in
    def _showFolderHasShows(self, node: QTreeWidgetItem | None) -> None:
        while node is not None:
            node.setData(0, Qt.ItemDataRole.ForegroundRole, None)
            key = node.data(0, FOLDER_ROLE)
            if key is not None:
                node.setToolTip(0, key)
            node = node.parent()

    # The following returns the node of a folder, making it and the folders it is in.  Folders of the machine are
    # listed under the machine, and others under Other files, by their full path
    def _folderNode(self, folder: Path) -> QTreeWidgetItem | None:
        if self.machinePath is not None and folder.is_relative_to(self.machinePath):
            node = self._makeNode(None, self.machinePath.name, str(self.machinePath), self.folderIcon)
            path = self.machinePath
            for part in folder.relative_to(self.machinePath).parts:
                path = path / part
                node = self._makeNode(node, part, str(path), self.folderIcon)
            return node
        otherNode = self._makeNode(None, OTHER_FILES, OTHER_FILES, self.folderIcon)
        return self._makeNode(otherNode, str(folder), str(folder), self.folderIcon)

    def _makeNode(
        self, parent: QTreeWidgetItem | None, label: str, key: str, icon, showFile: Path | None = None
    ) -> QTreeWidgetItem:
        node = self._nodes.get(key)
        if node is not None:
            return node
        node = QTreeWidgetItem([label])
        node.setIcon(0, icon)
        node.setData(0, FOLDER_ROLE, key)
        node.setToolTip(0, key)
        node.setData(0, FILE_ROLE, showFile is not None)
        if showFile is None:
            self._addChild(parent, node)
        else:
            self._addFileChild(parent, node, showFile)
        node.setExpanded(key not in self.collapsedFolders)
        self._nodes[key] = node
        return node

    # The following adds a file, or a show listed for its file, to a folder in the order of the files' names, so a
    # file added later, e.g. by saving, is listed where it would be when the shows are read again
    def _addFileChild(self, parent: QTreeWidgetItem | None, item: QTreeWidgetItem, showFile: Path) -> None:
        if parent is None:
            self.addTopLevelItem(item)
            return
        for index in range(parent.childCount()):
            sibling = parent.child(index)
            if sibling is None:
                continue
            isFileEntry = sibling.data(0, SHOW_ROLE) is not None or sibling.data(0, FILE_ROLE)
            if isFileEntry and str(showFile).lower() < sibling.toolTip(0).lower():
                parent.insertChild(index, item)
                return
        parent.addChild(item)

    def _addChild(self, parent: QTreeWidgetItem | None, item: QTreeWidgetItem) -> None:
        if parent is None:
            self.addTopLevelItem(item)
        else:
            parent.addChild(item)

    # The following takes an item out of the tree, along with folders and files left empty
    def _detach(self, item: QTreeWidgetItem) -> None:
        if self._loneShows.get(item.toolTip(0)) is item:
            del self._loneShows[item.toolTip(0)]
        parent = item.parent()
        if parent is None:
            self.takeTopLevelItem(self.indexOfTopLevelItem(item))
            return
        parent.removeChild(item)
        if parent.childCount() == 0 and parent.data(0, FOLDER_ROLE) not in self._keptFolders:
            self._nodes.pop(parent.data(0, FOLDER_ROLE), None)
            self._detach(parent)
