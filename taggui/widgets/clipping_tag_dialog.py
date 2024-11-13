from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel,
                               QMessageBox, QLineEdit, QPushButton, QWidget)
from PySide6.QtGui import QPixmap, QImage
from pathlib import Path

import json


class ClippingTagDialog(QDialog):
    tags_confirmed = Signal(dict, Path)  # Signal emitted when tags are confirmed

    def __init__(self, clipping_path: Path, parent=None, tag_sorter=None):
        super().__init__(parent)
        self.clipping_path = clipping_path
        self.tag_sorter = tag_sorter  # Store tag sorter
        self.setWindowTitle("Tag Clipping")
        self.setModal(True)

        # Initialize empty tags
        self.current_tags = {
            "characters": [],
            "settings": [],
            "actions": []
        }

        self.setup_ui()
        self.connect_signals()

    def setup_ui(self):
        layout = QVBoxLayout(self)

        # Image preview
        self.preview_label = QLabel()
        pixmap = QPixmap(str(self.clipping_path))
        scaled_pixmap = pixmap.scaled(400, 300, Qt.AspectRatioMode.KeepAspectRatio,
                                      Qt.TransformationMode.SmoothTransformation)
        self.preview_label.setPixmap(scaled_pixmap)
        layout.addWidget(self.preview_label)

        # Bulk input section with auto-sort
        if self.tag_sorter:
            bulk_layout = QHBoxLayout()
            self.bulk_input = QLineEdit()
            self.bulk_input.setPlaceholderText("Enter multiple tags separated by commas")
            self.sort_button = QPushButton("Auto-Sort Tags")
            self.loading_label = QLabel("Processing...")
            self.loading_label.hide()
            bulk_layout.addWidget(self.bulk_input)
            bulk_layout.addWidget(self.sort_button)
            layout.addLayout(bulk_layout)
            layout.addWidget(self.loading_label)

        # Input section
        inputs_widget = QWidget()
        inputs_layout = QVBoxLayout(inputs_widget)

        # Characters
        char_layout = QHBoxLayout()
        char_label = QLabel("Characters:")
        char_label.setMinimumWidth(100)
        self.character_input = QLineEdit()
        self.character_input.setPlaceholderText("Add character")
        char_layout.addWidget(char_label)
        char_layout.addWidget(self.character_input)
        inputs_layout.addLayout(char_layout)

        # Settings
        setting_layout = QHBoxLayout()
        setting_label = QLabel("Settings:")
        setting_label.setMinimumWidth(100)
        self.setting_input = QLineEdit()
        self.setting_input.setPlaceholderText("Add setting")
        setting_layout.addWidget(setting_label)
        setting_layout.addWidget(self.setting_input)
        inputs_layout.addLayout(setting_layout)

        # Actions
        action_layout = QHBoxLayout()
        action_label = QLabel("Actions:")
        action_label.setMinimumWidth(100)
        self.action_input = QLineEdit()
        self.action_input.setPlaceholderText("Add action")
        action_layout.addWidget(action_label)
        action_layout.addWidget(self.action_input)
        inputs_layout.addLayout(action_layout)

        layout.addWidget(inputs_widget)

        # Current tags display
        self.tag_display = QLabel("No tags added yet")
        self.tag_display.setWordWrap(True)
        layout.addWidget(self.tag_display)

        # Buttons
        button_layout = QHBoxLayout()
        self.save_button = QPushButton("Save")
        self.cancel_button = QPushButton("Cancel")
        button_layout.addWidget(self.save_button)
        button_layout.addWidget(self.cancel_button)
        layout.addLayout(button_layout)

        # Style
        self.setStyleSheet("""
            QLabel { padding: 5px; }
            QLineEdit { padding: 5px; }
            QPushButton { padding: 5px 15px; }
        """)

    def connect_signals(self):
        self.character_input.returnPressed.connect(lambda: self.add_tag("characters"))
        self.setting_input.returnPressed.connect(lambda: self.add_tag("settings"))
        self.action_input.returnPressed.connect(lambda: self.add_tag("actions"))

        if hasattr(self, 'sort_button'):
            self.sort_button.clicked.connect(self.auto_sort_tags)
            self.bulk_input.returnPressed.connect(self.auto_sort_tags)

        self.save_button.clicked.connect(self.handle_save)
        self.cancel_button.clicked.connect(self.reject)

    def add_tag(self, category: str):
        """Add a tag to the specified category"""
        if category == "characters":
            input_field = self.character_input
        elif category == "settings":
            input_field = self.setting_input
        elif category == "actions":
            input_field = self.action_input
        else:
            print(f"Warning: Unknown category {category}")
            return
        tag = input_field.text().strip()

        if tag:
            if tag not in self.current_tags[category]:
                self.current_tags[category].append(tag)
                input_field.clear()
                self.update_tag_display()
            else:
                input_field.clear()

    def auto_sort_tags(self):
        """Use the LLM to automatically sort tags"""
        if not self.tag_sorter:
            return

        text = self.bulk_input.text().strip()
        if not text:
            return

        # Show loading state
        self.loading_label.show()
        self.sort_button.setEnabled(False)
        self.bulk_input.setEnabled(False)

        try:
            # Split the input into individual tags
            tags = [tag.strip() for tag in text.split(',') if tag.strip()]

            # Use the tag sorter to categorize the tags
            categorized_tags = self.tag_sorter.sort_tags(tags)

            # Update the current tags
            for category, new_tags in categorized_tags.items():
                # Add new tags while avoiding duplicates
                self.current_tags[category].extend(
                    tag for tag in new_tags
                    if tag not in self.current_tags[category]
                )

            # Clear the input and update display
            self.bulk_input.clear()
            self.update_tag_display()

        except Exception as e:
            QMessageBox.warning(self, "Sorting Error", f"Failed to sort tags: {str(e)}")

        finally:
            # Reset UI state
            self.loading_label.hide()
            self.sort_button.setEnabled(True)
            self.bulk_input.setEnabled(True)

    def update_tag_display(self):
        """Update the tag display with clear category separation"""
        display_text = []

        # Add each category with its tags
        if self.current_tags["characters"]:
            display_text.append("Characters: " + ", ".join(self.current_tags["characters"]))
        if self.current_tags["settings"]:
            display_text.append("Settings: " + ", ".join(self.current_tags["settings"]))
        if self.current_tags["actions"]:
            display_text.append("Actions: " + ", ".join(self.current_tags["actions"]))

        if display_text:
            self.tag_display.setText("\n".join(display_text))
        else:
            self.tag_display.setText("No tags added yet")

        print("\nUpdated display text:")
        print("\n".join(display_text))

    def handle_save(self):
        """Handle saving of tags"""
        # Check for any unsaved input in text fields
        self.check_unsaved_inputs()

        # Format tags before emitting
        formatted_tags = {
            "characters": sorted(list(set(self.current_tags["characters"]))),
            "settings": sorted(list(set(self.current_tags["settings"]))),
            "actions": sorted(list(set(self.current_tags["actions"])))
        }

        # Emit the tags and path
        self.tags_confirmed.emit(formatted_tags, self.clipping_path)
        self.accept()

    def check_unsaved_inputs(self):
        """Check if there are any unsaved inputs in the text fields"""
        if self.character_input.text().strip():
            self.add_tag("characters")
        if self.setting_input.text().strip():
            self.add_tag("settings")
        if self.action_input.text().strip():
            self.add_tag("actions")

    def keyPressEvent(self, event):
        """Override key press event to handle Enter key"""
        if event.key() == Qt.Key.Key_Return or event.key() == Qt.Key.Key_Enter:
            # Don't let the dialog close on Enter
            return
        super().keyPressEvent(event)

    def sort_bulk_tags(self):
        """Handle sorting of bulk tags with improved debugging"""
        if not self.tag_sorter:
            return

        text = self.bulk_input.text().strip()
        if not text:
            return

        # Process the tags
        tags = [t.strip() for t in text.split(',') if t.strip()]
        if not tags:
            return

        print(f"\nProcessing input tags: {tags}")
        self.sort_button.setEnabled(False)
        QApplication.processEvents()

        try:
            # Sort tags
            result = self.tag_sorter.sort_tags(tags)

            # Show what we got back
            print("\nReceived classifications:")
            for category, category_tags in result.items():
                print(f"{category}: {category_tags}")

            # Update tags
            modified = False
            for category, new_tags in result.items():
                if new_tags:
                    print(f"\nAdding to {category}: {new_tags}")
                    self.current_tags[category].extend(new_tags)
                    self.current_tags[category] = list(dict.fromkeys(self.current_tags[category]))
                    modified = True

            if modified:
                self.update_tag_display()
                print("\nFinal tag state:")
                for category, tags in self.current_tags.items():
                    print(f"{category}: {tags}")

        except Exception as e:
            print(f"Error in sort_bulk_tags: {str(e)}")
            import traceback
            traceback.print_exc()
        finally:
            self.sort_button.setEnabled(True)

    def handle_sorted_tags(self, result: dict):
        """Handle the sorted tags result with better debugging"""
        try:
            print("\nReceived sorted tags:")
            print(json.dumps(result, indent=2))

            self.sort_button.setEnabled(True)

            # Validate the result structure
            if not isinstance(result, dict):
                print(f"Error: Expected dict, got {type(result)}")
                return

            expected_keys = {"characters", "settings", "actions"}
            if not all(key in result for key in expected_keys):
                print(f"Error: Missing expected keys. Got {result.keys()}")
                return

            # Merge with existing tags
            for category, tags in result.items():
                if not isinstance(tags, list):
                    print(f"Error: Expected list for {category}, got {type(tags)}")
                    continue

                self.current_tags[category].extend(tags)
                # Remove duplicates while preserving order
                self.current_tags[category] = list(dict.fromkeys(self.current_tags[category]))

            # Clear the input and update display
            self.bulk_input.clear()
            self.update_tag_display()

        except Exception as e:
            print(f"Error handling sorted tags: {str(e)}")
            import traceback
            traceback.print_exc()

    def handle_sorting_error(self, error_msg: str):
        """Handle sorting errors"""
        self.sort_button.setEnabled(True)
        QMessageBox.warning(self, "Sorting Error", error_msg)