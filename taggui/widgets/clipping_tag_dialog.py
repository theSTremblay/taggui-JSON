from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel,
                               QLineEdit, QPushButton, QWidget)
from PySide6.QtGui import QPixmap, QImage
from pathlib import Path

import json


class ClippingTagDialog(QDialog):
    tags_confirmed = Signal(dict, Path)  # Signal emitted when tags are confirmed

    def __init__(self, clipping_path: Path, parent=None):
        super().__init__(parent)
        self.clipping_path = clipping_path
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

        # Input section
        inputs_widget = QWidget()
        inputs_layout = QVBoxLayout(inputs_widget)

        # Characters
        char_layout = QHBoxLayout()
        char_label = QLabel("Characters:")
        char_label.setMinimumWidth(100)
        # Changed from char_input to character_input to match getattr call
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

        self.save_button.clicked.connect(self.handle_save)
        self.cancel_button.clicked.connect(self.reject)

    def add_tag(self, category: str):
        """Add a tag to the specified category"""
        if category == "characters":
            input_field = self.character_input
        elif category == "settings":
            input_field = self.setting_input
        else:  # actions
            input_field = self.action_input

        tag = input_field.text().strip()

        if tag:
            if tag not in self.current_tags[category]:
                self.current_tags[category].append(tag)
                input_field.clear()
                self.update_tag_display()
            else:
                input_field.clear()

    def update_tag_display(self):
        """Update the display of current tags"""
        display_text = []

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

    def handle_save(self):
        """Handle saving of tags"""
        # Also check if there's any unsaved input in the text fields
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