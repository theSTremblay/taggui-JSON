from PySide6.QtCore import (QItemSelectionModel, QModelIndex, QStringListModel,
                            QTimer, Qt, Signal, Slot)
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import (QAbstractItemView, QCompleter, QDockWidget,
                               QLabel, QLineEdit, QListView, QMessageBox,
                               QVBoxLayout, QWidget)
from transformers import PreTrainedTokenizerBase

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

    def __init__(self, tag_counter_model: TagCounterModel, image_list: ImageList = None):  # Add image_list parameter
        super().__init__()
        self.tag_counter_model = tag_counter_model
        self.image_list = image_list  # Store image_list reference
        self.tag_separator = ','  # Default separator

        layout = QVBoxLayout(self)

        # Characters input
        self.characters_input = QLineEdit()
        self.characters_input.setPlaceholderText('Add Characters')
        self.characters_input.returnPressed.connect(self.emit_tags)

        # Setting input
        self.setting_input = QLineEdit()
        self.setting_input.setPlaceholderText('Add Setting')
        self.setting_input.returnPressed.connect(self.emit_tags)

        # Actions input
        self.actions_input = QLineEdit()
        self.actions_input.setPlaceholderText('Add Actions')
        self.actions_input.returnPressed.connect(self.emit_tags)

        layout.addWidget(self.characters_input)
        layout.addWidget(self.setting_input)
        layout.addWidget(self.actions_input)

    def emit_tags(self):
        if not self.image_list:
            return

        # Get selected image indices
        selected_indices = self.image_list.get_selected_image_indices()
        if not selected_indices:
            return

        # Collect and format tags
        flat_tags = []

        # Process characters
        characters = self.characters_input.text().strip()
        if characters:
            for tag in characters.split(self.tag_separator):
                if tag.strip():
                    flat_tags.append(f"character:{tag.strip()}")

        # Process settings
        settings = self.setting_input.text().strip()
        if settings:
            for tag in settings.split(self.tag_separator):
                if tag.strip():
                    flat_tags.append(f"setting:{tag.strip()}")

        # Process actions
        actions = self.actions_input.text().strip()
        if actions:
            for tag in actions.split(self.tag_separator):
                if tag.strip():
                    flat_tags.append(f"action:{tag.strip()}")

        if flat_tags:
            # Emit the tags and selected indices
            self.tags_addition_requested.emit(flat_tags, selected_indices)
            self.clear_inputs()

    def clear_inputs(self):
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

        # Pass image_list to JSONTagInputBox
        self.tag_input_box = JSONTagInputBox(self.tag_counter_model, self.image_list)

        # Connect the signal to our new json handler instead of the model's add_tags
        self.tag_input_box.tags_addition_requested.connect(self.handle_json_tags)

        self.image_tags_list = JSONImageTagsList(self.image_tag_list_model)
        self.token_count_label = QLabel()

        container = QWidget()
        layout = QVBoxLayout(container)
        layout.addWidget(self.tag_input_box)
        layout.addWidget(self.image_tags_list)
        layout.addWidget(self.token_count_label)
        self.setWidget(container)

        # Connect signals
        self.image_tag_list_model.rowsInserted.connect(
            lambda _, __, last_index:
            self.image_tags_list.selectionModel().select(
                self.image_tag_list_model.index(last_index),
                QItemSelectionModel.SelectionFlag.ClearAndSelect))
        self.image_tag_list_model.rowsInserted.connect(
            self.image_tags_list.scrollToBottom)
        self.image_tag_list_model.modelReset.connect(self.count_tokens)
        self.image_tag_list_model.dataChanged.connect(self.count_tokens)

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
        """Handle new tags being added."""
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

        # Update JSON files for each selected image
        for index in image_indices:
            # Get the image from the source model using proper index mapping
            source_index = self.proxy_image_list_model.mapToSource(index)
            image: Image = self.proxy_image_list_model.sourceModel().data(
                source_index, Qt.ItemDataRole.UserRole)

            if image is None or not hasattr(image, 'path'):
                continue

            try:
                # Read existing tags from JSON file
                existing_tags = self.read_json_tags_from_disk(image.path)

                # Merge with new tags
                for category in ["characters", "settings", "actions"]:
                    existing_tags[category].extend(new_tags[category])
                    # Remove duplicates while preserving order
                    existing_tags[category] = list(dict.fromkeys(existing_tags[category]))

                # Write the merged tags back to disk
                self.write_json_tags_to_disk(image.path, existing_tags)

                # Update current tags if this is the selected image
                if self.image_index and source_index == self.image_index:
                    self.current_json_tags = existing_tags
                    self.update_display()

            except Exception as e:
                print(f"Error processing tags for {image.path}: {str(e)}")
                continue

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

    # def write_json_tags_to_disk(self, image_path: Path, tags: Dict[str, List[str]]):
    #     """Write tags to a JSON file."""
    #     try:
    #         # Explicitly use .json extension
    #         json_path = image_path.with_suffix('.json')
    #         # Write formatted JSON
    #         with json_path.open('w', encoding='utf-8') as f:
    #             json.dump({
    #                 "characters": sorted(list(set(tags["characters"]))),
    #                 "settings": sorted(list(set(tags["settings"]))),
    #                 "actions": sorted(list(set(tags["actions"])))
    #             }, f, indent=2, ensure_ascii=False)
    #     except OSError as e:
    #         error_message_box = QMessageBox()
    #         error_message_box.setWindowTitle('Error')
    #         error_message_box.setIcon(QMessageBox.Icon.Critical)
    #         error_message_box.setText(f'Failed to save JSON tags for {image_path}: {str(e)}')
    #         error_message_box.exec()

    # def read_json_tags_from_disk(self, image_path: Path) -> Dict[str, List[str]]:
    #     """Read tags from a JSON file."""
    #     try:
    #         json_path = image_path.with_suffix('.json')
    #         if json_path.exists():
    #             with json_path.open('r', encoding='utf-8') as f:
    #                 data = json.load(f)
    #                 # Ensure proper structure
    #                 return {
    #                     "characters": list(set(data.get("characters", []))),
    #                     "settings": list(set(data.get("settings", []))),
    #                     "actions": list(set(data.get("actions", [])))
    #                 }
    #     except (OSError, json.JSONDecodeError) as e:
    #         print(f"Error reading JSON tags from {json_path}: {str(e)}")

        # Return empty tag structure if file doesn't exist or there's an error
        return {
            "characters": [],
            "settings": [],
            "actions": []
        }



    def update_display(self):
        """Update the display with current JSON tags."""
        # Convert JSON tags to display format
        display_tags = []
        for category, tags in self.current_json_tags.items():
            for tag in tags:
                display_tags.append(f"{category[:-1]}:{tag}")

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

    # @Slot()
    # def load_image_tags(self, proxy_image_index: QModelIndex):
    #     self.image_index = self.proxy_image_list_model.mapToSource(
    #         proxy_image_index)
    #     image: Image = self.proxy_image_list_model.data(
    #         proxy_image_index, Qt.ItemDataRole.UserRole)
    #     current_string_list = self.image_tag_list_model.stringList()
    #     if current_string_list == image.tags:
    #         return
    #     self.image_tag_list_model.setStringList(image.tags)
    #     self.count_tokens()
    #     if self.image_tags_list.hasFocus():
    #         self.select_first_tag()
    @Slot()
    def load_image_tags(self, proxy_image_index: QModelIndex):
        """Load JSON tags for the selected image."""
        if not proxy_image_index.isValid():
            return

        self.image_index = self.proxy_image_list_model.mapToSource(proxy_image_index)

        # Get image from source model
        source_model = self.proxy_image_list_model.sourceModel()
        image: Image = source_model.data(self.image_index, Qt.ItemDataRole.UserRole)

        if image is None:
            print(f"Warning: Could not get image data for index {proxy_image_index.row()}")
            return

        # Read JSON tags from disk
        self.current_json_tags = self.read_json_tags_from_disk(image.path)
        self.update_display()

        if self.image_tags_list.hasFocus():
            self.select_first_tag()

    # @Slot(list, list)
    # def handle_json_tags(self, tags: List[str], image_indices: List[QModelIndex]):
    #     """Handle new tags being added."""
    #     if not image_indices:
    #         return
    #
    #     # Process tags into categories
    #     new_tags = {
    #         "characters": [],
    #         "settings": [],
    #         "actions": []
    #     }
    #
    #     # Categorize the tags
    #     for tag in tags:
    #         if tag.startswith("character:"):
    #             new_tags["characters"].append(tag.replace("character:", "").strip())
    #         elif tag.startswith("setting:"):
    #             new_tags["settings"].append(tag.replace("setting:", "").strip())
    #         elif tag.startswith("action:"):
    #             new_tags["actions"].append(tag.replace("action:", "").strip())
    #
    #     # Update JSON files for each selected image
    #     for index in image_indices:
    #         # Get the image from the source model using proper index mapping
    #         source_index = self.proxy_image_list_model.mapToSource(index)
    #         image: Image = self.proxy_image_list_model.sourceModel().data(
    #             source_index, Qt.ItemDataRole.UserRole)
    #
    #         if image is None or not hasattr(image, 'path'):
    #             print(f"Warning: Could not get valid image data for index {index.row()}")
    #             continue
    #
    #         try:
    #             # Read existing tags
    #             existing_tags = self.read_json_tags_from_disk(image.path)
    #
    #             # Merge with new tags, ensuring uniqueness
    #             merged_tags = {
    #                 "characters": list(set(existing_tags["characters"] + new_tags["characters"])),
    #                 "settings": list(set(existing_tags["settings"] + new_tags["settings"])),
    #                 "actions": list(set(existing_tags["actions"] + new_tags["actions"]))
    #             }
    #
    #             # Write back to disk
    #             self.write_json_tags_to_disk(image.path, merged_tags)
    #
    #             # Update display if this is the current image
    #             if self.image_index and source_index == self.image_index:
    #                 self.current_json_tags = merged_tags
    #                 self.update_display()
    #
    #         except Exception as e:
    #             print(f"Error processing tags for {image.path}: {str(e)}")
    #             continue


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
# class JSONTagInputBox(QWidget):
#     tags_addition_requested = Signal(dict)
#
#     def __init__(self, tag_counter_model: TagCounterModel, tag_separator: str = ','):
#         super().__init__()
#         self.tag_counter_model = tag_counter_model
#         self.tag_separator = tag_separator
#
#         layout = QVBoxLayout(self)
#
#         # Characters input
#         self.characters_input = QLineEdit()
#         self.characters_input.setPlaceholderText('Add Characters')
#         self.characters_input.returnPressed.connect(self.emit_tags)
#
#         # Setting input
#         self.setting_input = QLineEdit()
#         self.setting_input.setPlaceholderText('Add Setting')
#         self.setting_input.returnPressed.connect(self.emit_tags)
#
#         # Actions input
#         self.actions_input = QLineEdit()
#         self.actions_input.setPlaceholderText('Add Actions')
#         self.actions_input.returnPressed.connect(self.emit_tags)
#
#         # Add to layout
#         layout.addWidget(self.characters_input)
#         layout.addWidget(self.setting_input)
#         layout.addWidget(self.actions_input)
#
#         self.setLayout(layout)
#
#     def emit_tags(self):
#         tags = {
#             'characters': self.characters_input.text().split(self.tag_separator),
#             'settings': self.setting_input.text().split(self.tag_separator),
#             'actions': self.actions_input.text().split(self.tag_separator)
#         }
#         try:
#
#             self.tags_addition_requested.emit(tags)
#             self.clear_inputs()
#         except Exception as e:
#             print(e)
#
#     def clear_inputs(self):
#         self.characters_input.clear()
#         self.setting_input.clear()
#         self.actions_input.clear()
#
#
#     def keyPressEvent(self, event: QKeyEvent):
#         if event.key() in (Qt.Key_Return, Qt.Key_Enter):
#             active_input = self.focusWidget()
#             if isinstance(active_input, QLineEdit):
#                 self.emit_tags()
#
#     def add_tag(self, tag: str):
#         if not tag:
#             return
#         tags = tag.split(self.tag_separator)
#
#         # Separate the tags into categories
#         characters = [tag for tag in tags if "character" in tag.lower()]
#         settings = [tag for tag in tags if "setting" in tag.lower()]
#         actions = [tag for tag in tags if "action" in tag.lower()]
#
#         # Prepare the JSON object
#         json_tags = {
#             "characters": characters,
#             "settings": settings,
#             "actions": actions
#         }
#
#         # Print the JSON object to the console (or handle it as needed)
#         print(json_tags)
#
#         selected_image_indices = self.image_list.get_selected_image_indices()
#         selected_image_count = len(selected_image_indices)
#         if len(tags) == 1 and selected_image_count == 1:
#             # Add an empty tag and set it to the new tag.
#             self.image_tag_list_model.insertRow(
#                 self.image_tag_list_model.rowCount())
#             new_tag_index = self.image_tag_list_model.index(
#                 self.image_tag_list_model.rowCount() - 1)
#             self.image_tag_list_model.setData(new_tag_index, tag)
#             return
#         if selected_image_count > 1:
#             if len(tags) > 1:
#                 question = (f'Add tags to {selected_image_count} selected '
#                             f'images?')
#             else:
#                 question = (f'Add tag "{tags[0]}" to {selected_image_count} '
#                             f'selected images?')
#             reply = get_confirmation_dialog_reply(title='Add Tag',
#                                                   question=question)
#             if reply != QMessageBox.StandardButton.Yes:
#                 return
#         self.tags_addition_requested.emit(tags, selected_image_indices)


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
        if event.key() not in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            super().keyPressEvent(event)
            return
        # If Ctrl+Enter is pressed and the completer is visible, add the first
        # tag in the completer popup.
        if (event.modifiers() == Qt.KeyboardModifier.ControlModifier
                and self.completer.popup().isVisible()):
            first_tag = self.completer.popup().model().data(
                self.completer.model().index(0, 0), Qt.ItemDataRole.EditRole)
            self.add_tag(first_tag)
        # Otherwise, add the tag in the input box.
        else:
            self.add_tag(self.text())
        self.clear()
        self.completer.popup().hide()

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


# class JSONTagInputBox(QLineEdit):
#     tags_addition_requested = Signal(list, list)
#
#     def __init__(self, image_tag_list_model: QStringListModel,
#                  tag_counter_model: TagCounterModel, image_list: ImageList,
#                  tag_separator: str):
#         super().__init__()
#         self.image_tag_list_model = image_tag_list_model
#         self.image_list = image_list
#         self.tag_separator = tag_separator
#
#         self.completer = QCompleter(tag_counter_model)
#         self.setCompleter(self.completer)
#         self.setPlaceholderText('Add Tag')
#         self.setStyleSheet('padding: 8px;')
#
#         self.completer.activated.connect(lambda text: self.add_tag(text))
#         # Clear the input box after the completer inserts the tag into it.
#         self.completer.activated.connect(
#             lambda: QTimer.singleShot(0, self.clear))
#
#     def keyPressEvent(self, event: QKeyEvent):
#         if event.key() not in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
#             super().keyPressEvent(event)
#             return
#         # If Ctrl+Enter is pressed and the completer is visible, add the first
#         # tag in the completer popup.
#         if (event.modifiers() == Qt.KeyboardModifier.ControlModifier
#                 and self.completer.popup().isVisible()):
#             first_tag = self.completer.popup().model().data(
#                 self.completer.model().index(0, 0), Qt.ItemDataRole.EditRole)
#             self.add_tag(first_tag)
#         # Otherwise, add the tag in the input box.
#         else:
#             self.add_tag(self.text())
#         self.clear()
#         self.completer.popup().hide()
#
#     def add_tag(self, tag: str):
#         if not tag:
#             return
#         tags = tag.split(self.tag_separator)
#         selected_image_indices = self.image_list.get_selected_image_indices()
#         selected_image_count = len(selected_image_indices)
#         if len(tags) == 1 and selected_image_count == 1:
#             # Add an empty tag and set it to the new tag.
#             self.image_tag_list_model.insertRow(
#                 self.image_tag_list_model.rowCount())
#             new_tag_index = self.image_tag_list_model.index(
#                 self.image_tag_list_model.rowCount() - 1)
#             self.image_tag_list_model.setData(new_tag_index, tag)
#             return
#         if selected_image_count > 1:
#             if len(tags) > 1:
#                 question = (f'Add tags to {selected_image_count} selected '
#                             f'images?')
#             else:
#                 question = (f'Add tag "{tags[0]}" to {selected_image_count} '
#                             f'selected images?')
#             reply = get_confirmation_dialog_reply(title='Add Tag',
#                                                   question=question)
#             if reply != QMessageBox.StandardButton.Yes:
#                 return
#         self.tags_addition_requested.emit(tags, selected_image_indices)


class JSONImageTagsList(QListView):
    def __init__(self, image_tag_list_model: QStringListModel):
        super().__init__()
        self.image_tag_list_model = image_tag_list_model
        self.setModel(self.image_tag_list_model)
        self.setItemDelegate(TextEditItemDelegate(self))
        self.setSelectionMode(
            QAbstractItemView.SelectionMode.ExtendedSelection)
        self.setWordWrap(True)
        self.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)

    def keyPressEvent(self, event: QKeyEvent):
        """Delete selected tags when the delete key is pressed."""
        if event.key() != Qt.Key.Key_Delete:
            super().keyPressEvent(event)
            return
        rows_to_remove = [index.row() for index in self.selectedIndexes()]
        if not rows_to_remove:
            return
        remaining_tags = [tag for i, tag
                          in enumerate(self.image_tag_list_model.stringList())
                          if i not in rows_to_remove]
        self.image_tag_list_model.setStringList(remaining_tags)
        min_removed_row = min(rows_to_remove)
        remaining_row_count = self.image_tag_list_model.rowCount()
        if min_removed_row < remaining_row_count:
            self.select_tag(min_removed_row)
        elif remaining_row_count:
            # Select the last tag.
            self.select_tag(remaining_row_count - 1)

    def select_tag(self, row: int):
        # If the current index is not set, using the arrow keys to navigate
        # through the tags after selecting the tag will not work.
        self.setCurrentIndex(self.image_tag_list_model.index(row))
        self.selectionModel().select(
            self.image_tag_list_model.index(row),
            QItemSelectionModel.SelectionFlag.ClearAndSelect)


# class JsonTagsEditor(QDockWidget):
#     def __init__(self, proxy_image_list_model: ProxyImageListModel,
#                  tag_counter_model: TagCounterModel,
#                  image_tag_list_model: QStringListModel, image_list: ImageList,
#                  tokenizer: PreTrainedTokenizerBase, tag_separator: str):
#         super().__init__()
#         self.proxy_image_list_model = proxy_image_list_model
#         self.image_tag_list_model = image_tag_list_model
#         self.tokenizer = tokenizer
#         self.tag_separator = tag_separator
#         self.image_index = None
#         self.image_list = image_list  # Add this line to store image_list reference
#         self.tag_counter_model = tag_counter_model
#
#         # Each `QDockWidget` needs a unique object name for saving its state.
#         self.setObjectName('json_tags_editor')
#         self.setWindowTitle('JSON Tags')
#
#         self.tag_input_box = JSONTagInputBox(self.tag_counter_model)
#         self.tag_input_box.tags_addition_requested.connect(self.handle_tags_addition)
#         self.image_tags_list = JSONImageTagsList(self.image_tag_list_model)
#         self.token_count_label = QLabel()
#
#         # A container widget is required to use a layout with a `QDockWidget`.
#         container = QWidget()
#         layout = QVBoxLayout(container)
#         layout.addWidget(self.tag_input_box)
#         layout.addWidget(self.image_tags_list)
#         layout.addWidget(self.token_count_label)
#         self.setWidget(container)
#
#         # Connect signals
#         self.image_tag_list_model.rowsInserted.connect(
#             lambda _, __, last_index:
#             self.image_tags_list.selectionModel().select(
#                 self.image_tag_list_model.index(last_index),
#                 QItemSelectionModel.SelectionFlag.ClearAndSelect))
#         self.image_tag_list_model.rowsInserted.connect(
#             self.image_tags_list.scrollToBottom)
#         self.image_tag_list_model.modelReset.connect(self.count_tokens)
#         self.image_tag_list_model.dataChanged.connect(self.count_tokens)
#
#     @Slot(dict)
#     def handle_tags_addition(self, tags_dict):
#         """Handle the addition of tags from the JSON tag input box"""
#         # Get selected images
#         selected_image_indices = self.image_list.get_selected_image_indices()
#         if not selected_image_indices:
#             return
#
#         # Convert the dictionary of tags into a flat list with prefixes
#         flat_tags = []
#         for category, tag_list in tags_dict.items():
#             # Remove empty strings and strip whitespace
#             cleaned_tags = [tag.strip() for tag in tag_list if tag.strip()]
#             # Add category prefix to each tag
#             categorized_tags = [f"{category[:-1]}:{tag}" for tag in cleaned_tags]
#             flat_tags.extend(categorized_tags)
#
#         if not flat_tags:
#             return
#
#         # If multiple images are selected, show confirmation dialog
#         if len(selected_image_indices) > 1:
#             question = f'Add {len(flat_tags)} tags to {len(selected_image_indices)} selected images?'
#             reply = get_confirmation_dialog_reply(title='Add Tags', question=question)
#             if reply != QMessageBox.StandardButton.Yes:
#                 return
#
#         # Add the tags using the image_list_model's add_tags method
#         self.proxy_image_list_model.sourceModel().add_tags(flat_tags, selected_image_indices)
#
#     @Slot()
#     def count_tokens(self):
#         caption = self.tag_separator.join(
#             self.image_tag_list_model.stringList())
#         caption_token_count = len(self.tokenizer(caption).input_ids) - 2
#         if caption_token_count > MAX_TOKEN_COUNT:
#             self.token_count_label.setStyleSheet('color: red;')
#         else:
#             self.token_count_label.setStyleSheet('')
#         self.token_count_label.setText(f'{caption_token_count} / '
#                                        f'{MAX_TOKEN_COUNT} Tokens')
#
#     def select_first_tag(self):
#         if self.image_tag_list_model.rowCount() == 0:
#             return
#         self.image_tags_list.select_tag(0)
#
#     def select_last_tag(self):
#         tag_count = self.image_tag_list_model.rowCount()
#         if tag_count == 0:
#             return
#         self.image_tags_list.select_tag(tag_count - 1)
#
#     @Slot()
#     def load_image_tags(self, proxy_image_index: QModelIndex):
#         self.image_index = self.proxy_image_list_model.mapToSource(
#             proxy_image_index)
#         image: Image = self.proxy_image_list_model.data(
#             proxy_image_index, Qt.ItemDataRole.UserRole)
#         current_string_list = self.image_tag_list_model.stringList()
#         if current_string_list == image.tags:
#             return
#         self.image_tag_list_model.setStringList(image.tags)
#         self.count_tokens()
#         if self.image_tags_list.hasFocus():
#             self.select_first_tag()
#
#     @Slot()
#     def reload_image_tags_if_changed(self, first_changed_index: QModelIndex,
#                                      last_changed_index: QModelIndex):
#         if (first_changed_index.row() <= self.image_index.row()
#                 <= last_changed_index.row()):
#             proxy_image_index = self.proxy_image_list_model.mapFromSource(
#                 self.image_index)
#             self.load_image_tags(proxy_image_index)

# class JsonTagsEditor(QDockWidget):
#     def __init__(self, proxy_image_list_model: ProxyImageListModel,
#                  tag_counter_model: TagCounterModel,
#                  image_tag_list_model: QStringListModel, image_list: ImageList,
#                  tokenizer: PreTrainedTokenizerBase, tag_separator: str):
#         super().__init__()
#         self.proxy_image_list_model = proxy_image_list_model
#         self.image_tag_list_model = image_tag_list_model
#         self.tokenizer = tokenizer
#         self.tag_separator = tag_separator
#         self.image_index = None
#
#         self.tag_counter_model = tag_counter_model
#
#
#         # Each `QDockWidget` needs a unique object name for saving its state.
#         self.setObjectName('json_tags_editor')
#         self.setWindowTitle('JSON Tags')
#
#         self.tag_input_box = JSONTagInputBox(self.tag_counter_model)
#         self.tag_input_box.tags_addition_requested.connect(self.handle_tags_addition)
#         self.image_tags_list = JSONImageTagsList(self.image_tag_list_model)
#         self.token_count_label = QLabel()
#         # A container widget is required to use a layout with a `QDockWidget`.
#         container = QWidget()
#         layout = QVBoxLayout(container)
#         layout.addWidget(self.tag_input_box)
#         layout.addWidget(self.image_tags_list)
#         layout.addWidget(self.token_count_label)
#         self.setWidget(container)
#
#         # When a tag is added, select it and scroll to the bottom of the list.
#         self.image_tag_list_model.rowsInserted.connect(
#             lambda _, __, last_index:
#             self.image_tags_list.selectionModel().select(
#                 self.image_tag_list_model.index(last_index),
#                 QItemSelectionModel.SelectionFlag.ClearAndSelect))
#         self.image_tag_list_model.rowsInserted.connect(
#             self.image_tags_list.scrollToBottom)
#         # `rowsInserted` does not have to be connected because `dataChanged`
#         # is emitted when a tag is added.
#         self.image_tag_list_model.modelReset.connect(self.count_tokens)
#         self.image_tag_list_model.dataChanged.connect(self.count_tokens)
#         self.tag_input_box.tags_addition_requested.connect(
#             self.handle_tags_addition)
#
#     @Slot()
#     def count_tokens(self):
#         caption = self.tag_separator.join(
#             self.image_tag_list_model.stringList())
#         # Subtract 2 for the `` and `` tokens.
#         caption_token_count = len(self.tokenizer(caption).input_ids) - 2
#         if caption_token_count > MAX_TOKEN_COUNT:
#             self.token_count_label.setStyleSheet('color: red;')
#         else:
#             self.token_count_label.setStyleSheet('')
#         self.token_count_label.setText(f'{caption_token_count} / '
#                                        f'{MAX_TOKEN_COUNT} Tokens')
#
#     @Slot()
#     def select_first_tag(self):
#         if self.image_tag_list_model.rowCount() == 0:
#             return
#         self.image_tags_list.select_tag(0)
#
#     @Slot()
#     def load_image_tags(self, proxy_image_index: QModelIndex):
#         self.image_index = self.proxy_image_list_model.mapToSource(
#             proxy_image_index)
#         image: Image = self.proxy_image_list_model.data(
#             proxy_image_index, Qt.ItemDataRole.UserRole)
#         current_string_list = self.image_tag_list_model.stringList()
#         if current_string_list == image.tags:
#             return
#         self.image_tag_list_model.setStringList(image.tags)
#         self.count_tokens()
#         if self.image_tags_list.hasFocus():
#             self.select_first_tag()
#
#     @Slot()
#     def reload_image_tags_if_changed(self, first_changed_index: QModelIndex,
#                                      last_changed_index: QModelIndex):
#         """
#         Reload the tags for the current image if its index is in the range of
#         changed indices.
#         """
#         if (first_changed_index.row() <= self.image_index.row()
#                 <= last_changed_index.row()):
#             proxy_image_index = self.proxy_image_list_model.mapFromSource(
#                 self.image_index)
#             self.load_image_tags(proxy_image_index)
#
#     #@Slot(list, list)
#     #def handle_tags_addition(self, tags, selected_image_indices):
#     #    # Add further processing or interaction logic for added tags here.
#     #    print(f"Tags added: {tags}")
#     #    print(f"Selected indices: {selected_image_indices}")
#     @Slot(dict)
#     def handle_tags_addition(self, tags):
#         print(f"Characters: {tags['characters']}")
#         print(f"Settings: {tags['settings']}")
#         print(f"Actions: {tags['actions']}")
#
#         #self.add_tags_json(tags=tags)
#
#
#     def add_tags_json(self, tags: list[str]):
#         """Add one or more tags to one or more images."""
#         if not self.image_index:
#             return
#         action_name = f'Add {pluralize("Tag", len(tags))}'
#         #should_ask_for_confirmation = len(self.image_index) > 1
#         #self.add_to_undo_stack(action_name, should_ask_for_confirmation)
#
#
#         image_index = self.image_index
#         image: Image = self.data(image_index, Qt.ItemDataRole.UserRole)
#         image.tags.extend(tags)
#         self.write_image_tags_to_disk(image)
#         min_image_index = min(image_indices, key=lambda index: index.row())
#         max_image_index = max(image_indices, key=lambda index: index.row())
#         self.dataChanged.emit(min_image_index, max_image_index)
#
#
#     def write_image_tags_to_disk(self, image: Image):
#         try:
#             image.path.with_suffix('.txt').write_text(
#                 self.tag_separator.join(image.tags), encoding='utf-8',
#                 errors='replace')
#         except OSError:
#             error_message_box = QMessageBox()
#             error_message_box.setWindowTitle('Error')
#             error_message_box.setIcon(QMessageBox.Icon.Critical)
#             error_message_box.setText(f'Failed to save tags for {image.path}.')
#             error_message_box.exec()