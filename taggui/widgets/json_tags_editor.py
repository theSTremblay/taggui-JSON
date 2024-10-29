from PySide6.QtCore import (QItemSelectionModel, QModelIndex, QStringListModel,
                            QTimer, Qt, Signal, Slot)
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import (QAbstractItemView, QCompleter, QDockWidget,
                               QLabel, QLineEdit, QListView, QMessageBox,
                               QVBoxLayout, QWidget)

from PySide6.QtCore import QEvent, QRect, QSize, Qt, Signal
from PySide6.QtGui import QBrush, QColor, QPen
from PySide6.QtWidgets import (QStyledItemDelegate, QStyle, QLineEdit,
                              QStyleOptionViewItem)

from transformers import PreTrainedTokenizerBase
import json  # Add this import


from models.proxy_image_list_model import ProxyImageListModel
from models.tag_counter_model import TagCounterModel
from utils.image import Image
from utils.text_edit_item_delegate import TextEditItemDelegate
from utils.utils import get_confirmation_dialog_reply
from widgets.image_list import ImageList

from utils.utils import get_confirmation_dialog_reply, pluralize
from pathlib import Path
import json
from typing import Dict, List


MAX_TOKEN_COUNT = 75


# JSONTagInputBox class modifications
class JSONTagInputBox(QWidget):
    tags_addition_requested = Signal(list, list)  # Change signal to match expected parameters

    def __init__(self, tag_counter_model: TagCounterModel, image_list: ImageList = None):
        super().__init__()
        self.tag_counter_model = tag_counter_model
        self.image_list = image_list
        self.tag_separator = ','

        layout = QVBoxLayout(self)

        # Characters input
        self.characters_input = QLineEdit()
        self.characters_input.setPlaceholderText('Add Characters')
        self.characters_input.returnPressed.connect(lambda: self.emit_tags(force=True))

        # Setting input
        self.setting_input = QLineEdit()
        self.setting_input.setPlaceholderText('Add Setting')
        self.setting_input.returnPressed.connect(lambda: self.emit_tags(force=True))

        # Actions input
        self.actions_input = QLineEdit()
        self.actions_input.setPlaceholderText('Add Actions')
        self.actions_input.returnPressed.connect(lambda: self.emit_tags(force=True))

        layout.addWidget(self.characters_input)
        layout.addWidget(self.setting_input)
        layout.addWidget(self.actions_input)

    def emit_tags(self, force=False):
        """
        Emit the tags from all input fields.
        force: if True, will emit tags even if they might be duplicates
        """
        if not self.image_list:
            return

        # Get selected image indices
        selected_indices = self.image_list.get_selected_image_indices()
        if not selected_indices:
            return

        # Collect and format tags
        flat_tags = []

        # Process each input field
        inputs = {
            "character": self.characters_input.text().strip(),
            "setting": self.setting_input.text().strip(),
            "action": self.actions_input.text().strip()
        }

        for category, text in inputs.items():
            if text:
                for tag in text.split(self.tag_separator):
                    tag = tag.strip()
                    if tag:
                        flat_tags.append(f"{category}:{tag}")

        if flat_tags:
            # Always emit if we have tags and force is True
            self.tags_addition_requested.emit(flat_tags, selected_indices)
            self.clear_inputs()

        # Clear inputs even if no tags were emitted
        self.clear_inputs()

    def clear_inputs(self):
        """Clear all input fields."""
        self.characters_input.clear()
        self.setting_input.clear()
        self.actions_input.clear()


# JsonTagsEditor class modifications
class JsonTagsEditor(QDockWidget):
    def __init__(self, proxy_image_list_model: ProxyImageListModel,
                 tag_counter_model: TagCounterModel,
                 image_tag_list_model: QStringListModel,
                 image_list: ImageList,
                 tokenizer: PreTrainedTokenizerBase,
                 tag_separator: str):
        super().__init__()
        self.proxy_image_list_model = proxy_image_list_model
        self.image_tag_list_model = image_tag_list_model
        self.tokenizer = tokenizer
        self.tag_separator = tag_separator
        self.image_index = None
        self.image_list = image_list
        self.tag_counter_model = tag_counter_model

        # Initialize current_json_tags with empty structure
        self.init_current_json_tags()

        self.setObjectName('json_tags_editor')
        self.setWindowTitle('JSON Tags')

        # Create components
        self.tag_input_box = JSONTagInputBox(self.tag_counter_model, self.image_list)
        self.image_tags_list = JSONImageTagsList(self.image_tag_list_model)
        self.token_count_label = QLabel()

        # Set up connections
        self.tag_input_box.tags_addition_requested.connect(self.handle_json_tags)
        self.image_tags_list.tag_deletion_requested.connect(self.handle_tag_deletion)
        self.image_tags_list.tag_edited.connect(self.handle_tag_edited)

        # Debug print to verify signal connection
        print("Connecting tag deletion signal")

        # Create layout
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.addWidget(self.tag_input_box)
        layout.addWidget(self.image_tags_list)
        layout.addWidget(self.token_count_label)
        self.setWidget(container)

        # Connect model signals
        self.image_tag_list_model.rowsInserted.connect(
            lambda _, __, last_index:
            self.image_tags_list.selectionModel().select(
                self.image_tag_list_model.index(last_index),
                QItemSelectionModel.SelectionFlag.ClearAndSelect))
        self.image_tag_list_model.rowsInserted.connect(
            self.image_tags_list.scrollToBottom)
        self.image_tag_list_model.modelReset.connect(self.count_tokens)
        self.image_tag_list_model.dataChanged.connect(self.count_tokens)

    def handle_tag_edited(self, old_tag: str, new_tag: str):
        """Handle when a tag is edited"""
        if not self.image_index:
            return

        try:
            source_model = self.proxy_image_list_model.sourceModel()
            image: Image = source_model.data(self.image_index, Qt.ItemDataRole.UserRole)

            if not image:
                return

            # Read current tags
            current_tags = self.read_json_tags_from_disk(image.path)

            # Parse old and new tags
            old_category, old_value = old_tag.split(':', 1)
            new_category, new_value = new_tag.split(':', 1)

            # Update the appropriate category
            if old_category == 'character':
                current_tags["characters"].remove(old_value)
                if new_category == 'character':
                    current_tags["characters"].append(new_value)
            elif old_category == 'setting':
                current_tags["settings"].remove(old_value)
                if new_category == 'setting':
                    current_tags["settings"].append(new_value)
            elif old_category == 'action':
                current_tags["actions"].remove(old_value)
                if new_category == 'action':
                    current_tags["actions"].append(new_value)

            # Write updated tags and refresh display
            self.write_json_tags_to_disk(image.path, current_tags)
            self.current_json_tags = current_tags
            self.update_display()

        except Exception as e:
            print(f"Error editing tag: {str(e)}")

    def handle_tag_deletion(self, tags_to_delete: list):
        """Handle deletion of tags from the JSON structure."""
        if not self.image_index:
            return

        try:
            # Get the current image
            source_model = self.proxy_image_list_model.sourceModel()
            image: Image = source_model.data(self.image_index, Qt.ItemDataRole.UserRole)

            if not image:
                return

            # Read current tags
            current_tags = self.read_json_tags_from_disk(image.path)
            was_modified = False

            # Process each tag for deletion
            for tag in tags_to_delete:
                try:
                    category, value = tag.split(':', 1)
                    json_category = f"{category}s"  # Convert to plural for JSON keys

                    if json_category in current_tags and value in current_tags[json_category]:
                        current_tags[json_category].remove(value)
                        was_modified = True

                except ValueError:
                    print(f"Invalid tag format: {tag}")
                    continue

            if was_modified:
                # Write updated tags back to disk
                self.write_json_tags_to_disk(image.path, current_tags)

                # Update the current tags
                self.current_json_tags = current_tags
                self.update_display()

                print(f"Tags deleted: {tags_to_delete}")  # Debug print

        except Exception as e:
            print(f"Error deleting tags: {str(e)}")
            import traceback
            traceback.print_exc()

    @Slot()
    def count_tokens(self):
        """Count the total tokens in the current tags."""
        caption = self.tag_separator.join(
            self.image_tag_list_model.stringList())
        # Subtract 2 for the `<|startoftext|>` and `<|endoftext|>` tokens
        caption_token_count = len(self.tokenizer(caption).input_ids) - 2
        if caption_token_count > MAX_TOKEN_COUNT:
            self.token_count_label.setStyleSheet('color: red;')
        else:
            self.token_count_label.setStyleSheet('')
        self.token_count_label.setText(f'{caption_token_count} / '
                                       f'{MAX_TOKEN_COUNT} Tokens')

    @Slot(list, list)
    def handle_json_tags(self, tags: List[str], image_indices: List[QModelIndex]):
        """Handle new JSON tags being added."""
        if not image_indices:
            return

        # Process tags into categories
        new_tags = {
            "characters": [],
            "settings": [],
            "actions": []
        }

        # Categorize the tags
        for tag in tags:
            if tag.startswith("character:"):
                new_tags["characters"].append(tag.replace("character:", "").strip())
            elif tag.startswith("setting:"):
                new_tags["settings"].append(tag.replace("setting:", "").strip())
            elif tag.startswith("action:"):
                new_tags["actions"].append(tag.replace("action:", "").strip())

        # Get the currently selected image
        current_image_index = self.image_index
        if not current_image_index:
            return

        try:
            # Get the current image
            source_model = self.proxy_image_list_model.sourceModel()
            current_image: Image = source_model.data(current_image_index, Qt.ItemDataRole.UserRole)

            if not current_image or not hasattr(current_image, 'path'):
                return

            # Read existing JSON tags
            existing_tags = self.read_json_tags_from_disk(current_image.path)

            # Merge with new tags
            merged_tags = {
                "characters": existing_tags["characters"] + new_tags["characters"],
                "settings": existing_tags["settings"] + new_tags["settings"],
                "actions": existing_tags["actions"] + new_tags["actions"]
            }

            # Remove duplicates while preserving order
            merged_tags = {
                key: list(dict.fromkeys(value))
                for key, value in merged_tags.items()
            }

            # Write the merged tags to disk
            self.write_json_tags_to_disk(current_image.path, merged_tags)

            # Update current tags and display
            self.current_json_tags = merged_tags
            self.update_display()

        except Exception as e:
            print(f"Error processing JSON tags: {str(e)}")
            import traceback
            traceback.print_exc()

    def write_json_tags_to_disk(self, image_path: Path, tags: Dict[str, List[str]]):
        """Write tags to a JSON file."""
        try:
            # Explicitly use .json extension
            json_path = image_path.with_suffix('.json')
            # Format the tags nicely
            formatted_tags = {
                "characters": sorted(list(set(tags["characters"]))),
                "settings": sorted(list(set(tags["settings"]))),
                "actions": sorted(list(set(tags["actions"])))
            }
            # Write formatted JSON with nice indentation
            with json_path.open('w', encoding='utf-8') as f:
                json.dump(formatted_tags, f, indent=2, ensure_ascii=False)
        except OSError as e:
            print(f"Error saving JSON tags: {str(e)}")

    def read_json_tags_from_disk(self, image_path: Path) -> Dict[str, List[str]]:
        """Read tags from a JSON file."""
        empty_tags = {
            "characters": [],
            "settings": [],
            "actions": []
        }
        try:
            json_path = image_path.with_suffix('.json')
            if json_path.exists():
                with json_path.open('r', encoding='utf-8') as f:
                    data = json.load(f)
                    return {
                        "characters": list(data.get("characters", [])),
                        "settings": list(data.get("settings", [])),
                        "actions": list(data.get("actions", []))
                    }
        except (OSError, json.JSONDecodeError) as e:
            print(f"Error reading JSON tags: {str(e)}")
        return empty_tags

    def init_current_json_tags(self):
        """Initialize or reset current JSON tags structure."""
        self.current_json_tags = {
            "characters": [],
            "settings": [],
            "actions": []
        }
        return {
            "characters": [],
            "settings": [],
            "actions": []
        }

    def update_display(self):
        """Update display with only JSON tags"""
        display_tags = []
        for category, tags in self.current_json_tags.items():
            category_singular = category[:-1]  # Remove 's' from plural form
            for tag in tags:
                display_tags.append(f"{category_singular}:{tag}")

        # Update the model with only JSON tags
        self.image_tag_list_model.setStringList(display_tags)
        self.count_tokens()

    @Slot()
    def select_first_tag(self):
        if self.image_tag_list_model.rowCount() == 0:
            return
        self.image_tags_list.select_tag(0)

    def select_last_tag(self):
        tag_count = self.image_tag_list_model.rowCount()
        if tag_count == 0:
            return
        self.image_tags_list.select_tag(tag_count - 1)

    @Slot()
    def load_image_tags(self, proxy_image_index: QModelIndex):
        """Load only JSON tags"""
        if not proxy_image_index.isValid():
            return

        self.image_index = self.proxy_image_list_model.mapToSource(proxy_image_index)

        # Get image from source model
        source_model = self.proxy_image_list_model.sourceModel()
        image: Image = source_model.data(self.image_index, Qt.ItemDataRole.UserRole)

        if image is None:
            return

        # Only load tags from .json file
        try:
            json_path = image.path.with_suffix('.json')
            if json_path.exists():
                with json_path.open('r', encoding='utf-8') as f:
                    self.current_json_tags = json.load(f)
            else:
                self.current_json_tags = self.init_current_json_tags()
        except (OSError, json.JSONDecodeError) as e:
            print(f"Error reading JSON tags: {str(e)}")
            self.current_json_tags = self.init_current_json_tags()

        self.update_display()

        if self.image_tags_list.hasFocus():
            self.select_first_tag()



    @Slot()
    def reload_image_tags_if_changed(self, first_changed_index: QModelIndex,
                                     last_changed_index: QModelIndex):
        """
        Reload the tags for the current image if its index is in the range of
        changed indices.
        """
        if (first_changed_index.row() <= self.image_index.row()
                <= last_changed_index.row()):
            proxy_image_index = self.proxy_image_list_model.mapFromSource(
                self.image_index)
            self.load_image_tags(proxy_image_index)


class TagInputBox(QLineEdit):
    tags_addition_requested = Signal(list, list)

    def __init__(self, image_tag_list_model: QStringListModel,
                 tag_counter_model: TagCounterModel, image_list: ImageList,
                 tag_separator: str):
        super().__init__()
        self.image_tag_list_model = image_tag_list_model
        self.image_list = image_list
        self.tag_separator = tag_separator

        self.completer = QCompleter(tag_counter_model)
        self.setCompleter(self.completer)
        self.setPlaceholderText('Add Tag')
        self.setStyleSheet('padding: 8px;')

        self.completer.activated.connect(lambda text: self.add_tag(text))
        # Clear the input box after the completer inserts the tag into it.
        self.completer.activated.connect(
            lambda: QTimer.singleShot(0, self.clear))

    def keyPressEvent(self, event: QKeyEvent):
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self.emit_tags(force=True)
            event.accept()
        else:
            super().keyPressEvent(event)

    def add_tag(self, tag: str):
        if not tag:
            return
        tags = tag.split(self.tag_separator)
        selected_image_indices = self.image_list.get_selected_image_indices()
        selected_image_count = len(selected_image_indices)
        if len(tags) == 1 and selected_image_count == 1:
            # Add an empty tag and set it to the new tag.
            self.image_tag_list_model.insertRow(
                self.image_tag_list_model.rowCount())
            new_tag_index = self.image_tag_list_model.index(
                self.image_tag_list_model.rowCount() - 1)
            self.image_tag_list_model.setData(new_tag_index, tag)
            return
        if selected_image_count > 1:
            if len(tags) > 1:
                question = (f'Add tags to {selected_image_count} selected '
                            f'images?')
            else:
                question = (f'Add tag "{tags[0]}" to {selected_image_count} '
                            f'selected images?')
            reply = get_confirmation_dialog_reply(title='Add Tag',
                                                  question=question)
            if reply != QMessageBox.StandardButton.Yes:
                return
        self.tags_addition_requested.emit(tags, selected_image_indices)


class JSONImageTagsList(QListView):
    tag_deletion_requested = Signal(list)
    tag_edited = Signal(str, str)  # Signal for when a tag is edited (old_tag, new_tag)

    def __init__(self, image_tag_list_model: QStringListModel):
        super().__init__()
        self.image_tag_list_model = image_tag_list_model
        self.setModel(self.image_tag_list_model)

        # Make items editable
        self.setEditTriggers(QAbstractItemView.EditTrigger.DoubleClicked |
                             QAbstractItemView.EditTrigger.EditKeyPressed |
                             QAbstractItemView.EditTrigger.SelectedClicked)

        # Custom delegate for editing and delete button
        self.delegate = JSONTagItemDelegate(self)
        self.setItemDelegate(self.delegate)

        # Connect delegate signals
        print("Connecting delegate signals")  # Debug print
        self.delegate.deleteClicked.connect(self.handle_delete_clicked)

        self.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.setWordWrap(True)
        self.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)

        # Connect delegate signals directly to handle tag deletion


    def keyPressEvent(self, event: QKeyEvent):
        """Delete selected tags when the delete key is pressed."""
        if event.key() != Qt.Key.Key_Delete:
            super().keyPressEvent(event)
            return

        # Get selected tags
        selected_tags = []
        for index in self.selectedIndexes():
            tag = self.image_tag_list_model.data(index, Qt.ItemDataRole.DisplayRole)
            if tag:
                selected_tags.append(tag)

        if selected_tags:
            # Emit signal with selected tags
            self.tag_deletion_requested.emit(selected_tags)

    def select_tag(self, row: int):
        self.setCurrentIndex(self.model().index(row))
        self.selectionModel().select(
            self.model().index(row),
            QItemSelectionModel.SelectionFlag.ClearAndSelect)

    def handle_delete_clicked(self, index):
        """Handle delete button click"""
        print("Delete clicked received")  # Debug print
        tag = self.model().data(index, Qt.ItemDataRole.DisplayRole)
        if tag:
            print(f"Emitting deletion request for tag: {tag}")  # Debug print
            self.tag_deletion_requested.emit([tag])

    def handle_tag_edited(self, index, new_text):
        """Handle when a tag is edited"""
        old_tag = self.image_tag_list_model.data(index, Qt.ItemDataRole.DisplayRole)
        if old_tag and new_text and old_tag != new_text:
            self.tag_edited.emit(old_tag, new_text)


class JSONTagItemDelegate(QStyledItemDelegate):
    deleteClicked = Signal(QModelIndex)
    tagEdited = Signal(QModelIndex, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.button_padding = 4
        self.delete_button_width = 20

    def paint(self, painter, option, index):
        # Save the original rect
        original_rect = option.rect

        # Adjust rect for text
        text_rect = QRect(original_rect)
        text_rect.setWidth(original_rect.width() - self.delete_button_width - 2 * self.button_padding)
        text_option = QStyleOptionViewItem(option)
        text_option.rect = text_rect

        # Draw the text part
        super().paint(painter, text_option, index)

        # Draw delete button
        button_rect = QRect(
            original_rect.right() - self.delete_button_width - self.button_padding,
            original_rect.top() + self.button_padding,
            self.delete_button_width,
            original_rect.height() - 2 * self.button_padding
        )

        # Handle hover state
        is_hovered = bool(option.state & QStyle.State_MouseOver)
        if is_hovered:
            painter.setPen(QPen(QColor("#ff4444")))
            painter.setBrush(QBrush(QColor("#661111")))
        else:
            painter.setPen(QPen(QColor("#cccccc")))
            painter.setBrush(QBrush(QColor("#444444")))

        painter.drawRect(button_rect)

        # Draw X
        painter.setPen(QPen(QColor("white")))
        painter.drawText(button_rect, Qt.AlignCenter, "×")

    def editorEvent(self, event, model, option, index):
        if event.type() == QEvent.Type.MouseButtonRelease:
            button_rect = QRect(
                option.rect.right() - self.delete_button_width - self.button_padding,
                option.rect.top() + self.button_padding,
                self.delete_button_width,
                option.rect.height() - 2 * self.button_padding
            )

            if button_rect.contains(event.pos()):
                print(f"Delete button clicked at index {index.row()}")  # Debug print
                self.deleteClicked.emit(index)
                return True
        return super().editorEvent(event, model, option, index)