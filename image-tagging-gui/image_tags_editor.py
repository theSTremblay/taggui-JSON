from pathlib import Path

from PySide6.QtCore import (QItemSelectionModel, QModelIndex,
                            QPersistentModelIndex, QSettings, QStringListModel,
                            QTimer, Qt, Slot)
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import (QAbstractItemView, QCompleter, QDockWidget,
                               QLabel, QLineEdit, QListView, QVBoxLayout,
                               QWidget)
from transformers import AutoTokenizer

from image import Image
from proxy_image_list_model import ProxyImageListModel
from settings import get_separator
from tag_counter_model import TagCounterModel

TOKENIZER_PATH = Path('../clip-vit-base-patch32')
MAX_TOKEN_COUNT = 75


class TagInputBox(QLineEdit):
    def __init__(self, image_tag_list_model: QStringListModel,
                 tag_counter_model: TagCounterModel):
        super().__init__()
        self.image_tag_list_model = image_tag_list_model

        self.completer = QCompleter(tag_counter_model)
        self.setCompleter(self.completer)
        self.setPlaceholderText('Add Tag')
        self.setStyleSheet('padding: 8px;')

        self.completer.activated.connect(lambda text: self.add_tag(text))
        # Clear the input box after the completer inserts the tag into it.
        self.completer.activated.connect(
            lambda: QTimer.singleShot(0, self.clear))

    def keyPressEvent(self, event: QKeyEvent):
        if not event.key() == Qt.Key_Return:
            super().keyPressEvent(event)
            return
        # If Ctrl+Enter is pressed and the completer is visible, add the first
        # tag in the completer popup.
        if (event.modifiers() == Qt.ControlModifier
                and self.completer.popup().isVisible()):
            first_tag = self.completer.popup().model().data(
                self.completer.model().index(0, 0), Qt.EditRole)
            self.add_tag(first_tag)
        # Otherwise, add the tag in the input box.
        else:
            self.add_tag(self.text())
        self.clear()
        self.completer.popup().hide()

    def add_tag(self, tag: str):
        if not tag:
            return
        # Add an empty tag and set it to the new tag.
        self.image_tag_list_model.insertRow(
            self.image_tag_list_model.rowCount())
        new_tag_index = self.image_tag_list_model.index(
            self.image_tag_list_model.rowCount() - 1)
        self.image_tag_list_model.setData(new_tag_index, tag)


class ImageTagsList(QListView):
    def __init__(self, image_tag_list_model: QStringListModel):
        super().__init__()
        self.image_tag_list_model = image_tag_list_model
        self.setModel(self.image_tag_list_model)
        self.setSelectionMode(
            QAbstractItemView.SelectionMode.ExtendedSelection)
        self.setSpacing(4)
        self.setWordWrap(True)
        self.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)

    def keyPressEvent(self, event: QKeyEvent):
        """Delete selected tags when the delete key is pressed."""
        if event.key() != Qt.Key_Delete:
            super().keyPressEvent(event)
            return
        # The selected indices must be converted to `QPersistentModelIndex`
        # objects to properly delete multiple tags.
        selected_indices = [QPersistentModelIndex(index) for index
                            in self.selectedIndexes()]
        for index in selected_indices:
            self.image_tag_list_model.removeRow(index.row())
        # The current index is set but not selected automatically after the
        # tags are deleted, so select it.
        self.setCurrentIndex(self.currentIndex())


class ImageTagsEditor(QDockWidget):
    def __init__(self, settings: QSettings,
                 proxy_image_list_model: ProxyImageListModel,
                 tag_counter_model: TagCounterModel,
                 image_tag_list_model: QStringListModel):
        super().__init__()
        self.settings = settings
        self.proxy_image_list_model = proxy_image_list_model
        self.image_tag_list_model = image_tag_list_model
        self.tokenizer = AutoTokenizer.from_pretrained(TOKENIZER_PATH)
        self.image_index = None

        # Each `QDockWidget` needs a unique object name for saving its state.
        self.setObjectName('image_tags_editor')
        self.setWindowTitle('Image Tags')
        self.setAllowedAreas(Qt.LeftDockWidgetArea | Qt.RightDockWidgetArea)
        self.tag_input_box = TagInputBox(self.image_tag_list_model,
                                         tag_counter_model)
        self.image_tags_list = ImageTagsList(self.image_tag_list_model)
        self.token_count_label = QLabel()
        # A container widget is required to use a layout with a `QDockWidget`.
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.addWidget(self.tag_input_box)
        layout.addWidget(self.image_tags_list)
        layout.addWidget(self.token_count_label)
        self.setWidget(container)

        # When a tag is added, select it and scroll to the bottom of the list.
        self.image_tag_list_model.rowsInserted.connect(
            lambda _, __, last_index:
            self.image_tags_list.selectionModel().select(
                self.image_tag_list_model.index(last_index),
                QItemSelectionModel.SelectionFlag.ClearAndSelect))
        self.image_tag_list_model.rowsInserted.connect(
            self.image_tags_list.scrollToBottom)
        # `rowsInserted` does not have to be connected because `dataChanged`
        # is emitted when a tag is added.
        self.image_tag_list_model.dataChanged.connect(self.count_tokens)
        self.image_tag_list_model.rowsRemoved.connect(self.count_tokens)

    @Slot()
    def count_tokens(self):
        caption = get_separator(self.settings).join(
            self.image_tag_list_model.stringList())
        # Subtract 2 for the `<|startoftext|>` and `<|endoftext|>` tokens.
        caption_token_count = len(self.tokenizer(caption).input_ids) - 2
        if caption_token_count > MAX_TOKEN_COUNT:
            self.token_count_label.setStyleSheet('color: red;')
        else:
            self.token_count_label.setStyleSheet('')
        self.token_count_label.setText(f'{caption_token_count} / '
                                       f'{MAX_TOKEN_COUNT} Tokens')

    @Slot()
    def load_image_tags(self, index: QModelIndex):
        # Store the index as a `QPersistentModelIndex` to make sure it stays
        # valid even when the image list is updated.
        persistent_index = QPersistentModelIndex(index)
        self.image_index = persistent_index
        image: Image = self.proxy_image_list_model.data(index, Qt.UserRole)
        self.image_tag_list_model.setStringList(image.tags)
        self.count_tokens()
