from pathlib import Path
from typing import List, Optional  # Add this import
import json  # Add this import


from PySide6.QtCore import QKeyCombination, QModelIndex, QUrl, Qt, Slot
from PySide6.QtGui import (QAction, QCloseEvent, QDesktopServices, QIcon,
                           QKeySequence, QPixmap, QShortcut)
from PySide6.QtWidgets import (QApplication, QFileDialog, QMainWindow,
                               QMessageBox, QStackedWidget, QVBoxLayout,
                               QWidget)
from transformers import AutoTokenizer

from dialogs.batch_reorder_tags_dialog import BatchReorderTagsDialog
from dialogs.find_and_replace_dialog import FindAndReplaceDialog
from dialogs.settings_dialog import SettingsDialog
from models.image_list_model import ImageListModel
from models.image_tag_list_model import ImageTagListModel
from models.proxy_image_list_model import ProxyImageListModel
from models.tag_counter_model import TagCounterModel
from utils.big_widgets import BigPushButton
from utils.image import Image
from utils.key_press_forwarder import KeyPressForwarder
from utils.settings import DEFAULT_SETTINGS, get_settings, get_tag_separator
from utils.shortcut_remover import ShortcutRemover
from utils.utils import get_resource_path, pluralize
from widgets.all_tags_editor import AllTagsEditor
from widgets.auto_captioner import AutoCaptioner
from widgets.image_list import ImageList
from widgets.image_tags_editor import ImageTagsEditor
from widgets.json_tags_editor import JsonTagsEditor
from widgets.image_viewer import ImageViewer

ICON_PATH = Path('images/icon.ico')
GITHUB_REPOSITORY_URL = 'https://github.com/jhc13/taggui'
TOKENIZER_DIRECTORY_PATH = Path('clip-vit-base-patch32')


class MainWindow(QMainWindow):
    def __init__(self, app: QApplication):
        super().__init__()
        self.app = app
        self.settings = get_settings()
        image_list_image_width = self.settings.value(
            'image_list_image_width',
            defaultValue=DEFAULT_SETTINGS['image_list_image_width'], type=int)
        tag_separator = get_tag_separator()
        self.image_list_model = ImageListModel(image_list_image_width,
                                               tag_separator)
        tokenizer = AutoTokenizer.from_pretrained(
            get_resource_path(TOKENIZER_DIRECTORY_PATH))
        self.proxy_image_list_model = ProxyImageListModel(
            self.image_list_model, tokenizer, tag_separator)
        self.image_list_model.proxy_image_list_model = (
            self.proxy_image_list_model)
        self.tag_counter_model = TagCounterModel()
        self.image_tag_list_model = ImageTagListModel()

        #self.text_tag_list_model = ImageTagListModel()
        self.json_tag_list_model = ImageTagListModel()

        self.setWindowIcon(QIcon(QPixmap(get_resource_path(ICON_PATH))))
        # Not setting this results in some ugly colors.
        self.setPalette(self.app.style().standardPalette())
        # The font size must be set before creating the widgets to ensure that
        # everything has the correct font size.
        self.set_font_size()
        self.image_viewer = ImageViewer(self.proxy_image_list_model)
        self.create_central_widget()
        self.image_list = ImageList(self.proxy_image_list_model,
                                    tag_separator, image_list_image_width)
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea,
                           self.image_list)
        self.image_tags_editor = ImageTagsEditor(
            self.proxy_image_list_model, self.tag_counter_model,
            self.image_tag_list_model, self.image_list, tokenizer,
            tag_separator)
        self.json_tags_editor = JsonTagsEditor(
            self.proxy_image_list_model, self.tag_counter_model,
            self.json_tag_list_model, self.image_list, tokenizer,
            tag_separator)



        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea,
                           self.json_tags_editor)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea,
                           self.image_tags_editor)
        self.all_tags_editor = AllTagsEditor(self.tag_counter_model)
        self.tag_counter_model.all_tags_list = (self.all_tags_editor
                                                .all_tags_list)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea,
                           self.all_tags_editor)
        self.auto_captioner = AutoCaptioner(self.image_list_model,
                                            self.image_list)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea,
                           self.auto_captioner)
        self.tabifyDockWidget(self.all_tags_editor, self.auto_captioner)
        self.all_tags_editor.raise_()
        # Set default widths for the dock widgets.
        # Temporarily set a size for the window so that the dock widgets can be
        # expanded to their default widths. If the window geometry was
        # previously saved, it will be restored later.
        self.resize(image_list_image_width * 8,
                    int(image_list_image_width * 4.5))
        self.resizeDocks([self.image_list, self.image_tags_editor,
                          self.all_tags_editor],
                         [int(image_list_image_width * 2.5)] * 3,
                         Qt.Orientation.Horizontal)
        # Disable some widgets until a directory is loaded.
        self.image_tags_editor.tag_input_box.setDisabled(True)
        self.auto_captioner.start_cancel_button.setDisabled(True)
        self.reload_directory_action = QAction('Reload Directory', parent=self)
        self.reload_directory_action.setDisabled(True)
        self.undo_action = QAction('Undo', parent=self)
        self.redo_action = QAction('Redo', parent=self)
        self.toggle_image_list_action = QAction('Images', parent=self)
        self.toggle_image_tags_editor_action = QAction('Image Tags',
                                                       parent=self)
        self.toggle_all_tags_editor_action = QAction('All Tags', parent=self)
        self.toggle_auto_captioner_action = QAction('Auto-Captioner',
                                                    parent=self)
        self.create_menus()

        self.image_list_selection_model = (self.image_list.list_view
                                           .selectionModel())
        self.image_list_model.image_list_selection_model = (
            self.image_list_selection_model)
        self.connect_image_list_signals()
        self.connect_image_tags_editor_signals()
        self.connect_all_tags_editor_signals()
        self.connect_auto_captioner_signals()
        # Forward any unhandled image changing key presses to the image list.
        key_press_forwarder = KeyPressForwarder(
            parent=self, target=self.image_list.list_view,
            keys_to_forward=(Qt.Key.Key_Up, Qt.Key.Key_Down, Qt.Key.Key_PageUp,
                             Qt.Key.Key_PageDown, Qt.Key.Key_Home,
                             Qt.Key.Key_End))
        self.installEventFilter(key_press_forwarder)
        # Remove the Ctrl+Z shortcut from text input boxes to prevent it from
        # conflicting with the undo action.
        ctrl_z = QKeyCombination(Qt.KeyboardModifier.ControlModifier,
                                 key=Qt.Key.Key_Z)
        ctrl_y = QKeyCombination(Qt.KeyboardModifier.ControlModifier,
                                 key=Qt.Key.Key_Y)
        shortcut_remover = ShortcutRemover(parent=self,
                                           shortcuts=(ctrl_z, ctrl_y))
        self.image_list.filter_line_edit.installEventFilter(shortcut_remover)
        self.image_tags_editor.tag_input_box.installEventFilter(
            shortcut_remover)
        self.all_tags_editor.filter_line_edit.installEventFilter(
            shortcut_remover)
        # Set keyboard shortcuts.
        focus_filter_images_box_shortcut = QShortcut(
            QKeySequence('Alt+F'), self)
        focus_filter_images_box_shortcut.activated.connect(
            self.image_list.raise_)
        focus_filter_images_box_shortcut.activated.connect(
            self.image_list.filter_line_edit.setFocus)
        focus_add_tag_box_shortcut = QShortcut(QKeySequence('Alt+A'), self)
        focus_add_tag_box_shortcut.activated.connect(
            self.image_tags_editor.raise_)
        focus_add_tag_box_shortcut.activated.connect(
            self.image_tags_editor.tag_input_box.setFocus)
        focus_image_tags_list_shortcut = QShortcut(QKeySequence('Alt+I'), self)
        focus_image_tags_list_shortcut.activated.connect(
            self.image_tags_editor.raise_)
        focus_image_tags_list_shortcut.activated.connect(
            self.image_tags_editor.image_tags_list.setFocus)
        focus_image_tags_list_shortcut.activated.connect(
            self.image_tags_editor.select_first_tag)

        focus_add_tag_box_shortcut.activated.connect(
            self.json_tags_editor.raise_)
        focus_add_tag_box_shortcut.activated.connect(
            self.json_tags_editor.tag_input_box.setFocus)
        focus_image_tags_list_shortcut = QShortcut(QKeySequence('Alt+I'), self)
        focus_image_tags_list_shortcut.activated.connect(
            self.json_tags_editor.raise_)
        focus_image_tags_list_shortcut.activated.connect(
            self.json_tags_editor.image_tags_list.setFocus)
        focus_image_tags_list_shortcut.activated.connect(
            self.json_tags_editor.select_first_tag)
        focus_search_tags_box_shortcut = QShortcut(QKeySequence('Alt+S'), self)
        focus_search_tags_box_shortcut.activated.connect(
            self.all_tags_editor.raise_)
        focus_search_tags_box_shortcut.activated.connect(
            self.all_tags_editor.filter_line_edit.setFocus)
        focus_caption_button_shortcut = QShortcut(QKeySequence('Alt+C'), self)
        focus_caption_button_shortcut.activated.connect(
            self.auto_captioner.raise_)
        focus_caption_button_shortcut.activated.connect(
            self.auto_captioner.start_cancel_button.setFocus)
        go_to_previous_image_shortcut = QShortcut(QKeySequence('Ctrl+Up'),
                                                  self)
        go_to_previous_image_shortcut.activated.connect(
            self.image_list.go_to_previous_image)
        go_to_next_image_shortcut = QShortcut(QKeySequence('Ctrl+Down'), self)
        go_to_next_image_shortcut.activated.connect(
            self.image_list.go_to_next_image)

        jump_to_first_untagged_image_shortcut = QShortcut(
            QKeySequence('Ctrl+J'), self)
        jump_to_first_untagged_image_shortcut.activated.connect(
            self.image_list.jump_to_first_untagged_image)

        self.restore()
        self.image_tags_editor.tag_input_box.setFocus()
        self.json_tags_editor.tag_input_box.setFocus()

    def closeEvent(self, event: QCloseEvent):
        """Save the window geometry and state before closing."""
        self.settings.setValue('geometry', self.saveGeometry())
        self.settings.setValue('window_state', self.saveState())
        super().closeEvent(event)

    def set_font_size(self):
        font = self.app.font()
        font_size = self.settings.value(
            'font_size', defaultValue=DEFAULT_SETTINGS['font_size'], type=int)
        font.setPointSize(font_size)
        self.app.setFont(font)

    def create_central_widget(self):
        central_widget = QStackedWidget()
        # Put the button inside a widget so that it will not fill up the entire
        # space.
        load_directory_widget = QWidget()
        load_directory_button = BigPushButton('Load Directory...')
        load_directory_button.clicked.connect(self.select_and_load_directory)
        QVBoxLayout(load_directory_widget).addWidget(
            load_directory_button, alignment=Qt.AlignmentFlag.AlignCenter)
        central_widget.addWidget(load_directory_widget)
        central_widget.addWidget(self.image_viewer)
        self.setCentralWidget(central_widget)

    def load_directory(self, path: Path, select_index: int = 0):
        self.settings.setValue('directory_path', str(path))
        self.setWindowTitle(path.name)
        self.image_list_model.load_directory(path)
        self.image_list.filter_line_edit.clear()
        self.all_tags_editor.filter_line_edit.clear()
        # Clear the current index first to make sure that the `currentChanged`
        # signal is emitted even if the image at the index is already selected.
        self.image_list_selection_model.clearCurrentIndex()
        self.image_list.list_view.setCurrentIndex(
            self.proxy_image_list_model.index(select_index, 0))
        self.centralWidget().setCurrentWidget(self.image_viewer)
        self.reload_directory_action.setDisabled(False)
        self.image_tags_editor.tag_input_box.setDisabled(False)
        self.json_tags_editor.tag_input_box.setDisabled(False)
        self.auto_captioner.start_cancel_button.setDisabled(False)

    @Slot()
    def select_and_load_directory(self):
        # Use the last loaded directory as the initial directory.
        if self.settings.contains('directory_path'):
            initial_directory_path = self.settings.value('directory_path')
        else:
            initial_directory_path = ''
        load_directory_path = QFileDialog.getExistingDirectory(
            parent=self, caption='Select directory to load images from',
            dir=initial_directory_path)
        if not load_directory_path:
            return
        self.load_directory(Path(load_directory_path))

    @Slot()
    def reload_directory(self):
        # Save the filter text and the index of the selected image to restore
        # them after reloading the directory.
        filter_text = self.image_list.filter_line_edit.text()
        select_index_key = ('image_index'
                            if self.proxy_image_list_model.filter is None
                            else 'filtered_image_index')
        select_index = self.settings.value(select_index_key, type=int) or 0
        self.load_directory(Path(self.settings.value('directory_path',
                                                     type=str)))
        self.image_list.filter_line_edit.setText(filter_text)
        # If the selected image index is out of bounds due to images being
        # deleted, select the last image.
        if select_index >= self.proxy_image_list_model.rowCount():
            select_index = self.proxy_image_list_model.rowCount() - 1
        self.image_list.list_view.setCurrentIndex(
            self.proxy_image_list_model.index(select_index, 0))

    @Slot()
    def show_settings_dialog(self):
        settings_dialog = SettingsDialog(parent=self)
        settings_dialog.exec()

    @Slot()
    def show_find_and_replace_dialog(self):
        find_and_replace_dialog = FindAndReplaceDialog(
            parent=self, image_list_model=self.image_list_model)
        find_and_replace_dialog.exec()

    @Slot()
    def show_batch_reorder_tags_dialog(self):
        batch_reorder_tags_dialog = BatchReorderTagsDialog(
            parent=self, image_list_model=self.image_list_model,
            tag_counter_model=self.tag_counter_model)
        batch_reorder_tags_dialog.exec()

    @Slot()
    def remove_duplicate_tags(self):
        removed_tag_count = self.image_list_model.remove_duplicate_tags()
        message_box = QMessageBox()
        message_box.setWindowTitle('Remove Duplicate Tags')
        message_box.setIcon(QMessageBox.Icon.Information)
        if not removed_tag_count:
            text = 'No duplicate tags were found.'
        else:
            text = (f'Removed {removed_tag_count} duplicate '
                    f'{pluralize("tag", removed_tag_count)}.')
        message_box.setText(text)
        message_box.exec()

    @Slot()
    def remove_empty_tags(self):
        removed_tag_count = self.image_list_model.remove_empty_tags()
        message_box = QMessageBox()
        message_box.setWindowTitle('Remove Empty Tags')
        message_box.setIcon(QMessageBox.Icon.Information)
        if not removed_tag_count:
            text = 'No empty tags were found.'
        else:
            text = (f'Removed {removed_tag_count} empty '
                    f'{pluralize("tag", removed_tag_count)}.')
        message_box.setText(text)
        message_box.exec()

    def create_menus(self):
        menu_bar = self.menuBar()

        file_menu = menu_bar.addMenu('File')
        load_directory_action = QAction('Load Directory...', parent=self)
        load_directory_action.setShortcut(QKeySequence('Ctrl+L'))
        load_directory_action.triggered.connect(self.select_and_load_directory)
        file_menu.addAction(load_directory_action)
        self.reload_directory_action.setShortcut(QKeySequence('Ctrl+Shift+L'))
        self.reload_directory_action.triggered.connect(self.reload_directory)
        file_menu.addAction(self.reload_directory_action)




        settings_action = QAction('Settings...', parent=self)
        settings_action.setShortcut(QKeySequence('Ctrl+Alt+S'))
        settings_action.triggered.connect(self.show_settings_dialog)
        file_menu.addAction(settings_action)
        exit_action = QAction('Exit', parent=self)
        exit_action.setShortcut(QKeySequence('Ctrl+W'))
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)

        next_dir_action = QAction('Next Directory', parent=self)
        next_dir_action.setShortcut(QKeySequence(Qt.KeyboardModifier.ControlModifier |
                                                 Qt.KeyboardModifier.AltModifier |
                                                 Qt.Key.Key_Right))
        next_dir_action.triggered.connect(self.navigate_to_next_directory)
        file_menu.addAction(next_dir_action)

        prev_dir_action = QAction('Previous Directory', parent=self)
        prev_dir_action.setShortcut(QKeySequence(Qt.KeyboardModifier.ControlModifier |
                                                 Qt.KeyboardModifier.AltModifier |
                                                 Qt.Key.Key_Left))
        prev_dir_action.triggered.connect(self.navigate_to_previous_directory)
        file_menu.addAction(prev_dir_action)

        edit_menu = menu_bar.addMenu('Edit')
        self.undo_action.setShortcut(QKeySequence('Ctrl+Z'))
        self.undo_action.triggered.connect(self.image_list_model.undo)
        self.undo_action.setDisabled(True)
        edit_menu.addAction(self.undo_action)
        self.redo_action.setShortcut(QKeySequence('Ctrl+Y'))
        self.redo_action.triggered.connect(self.image_list_model.redo)
        self.redo_action.setDisabled(True)
        edit_menu.addAction(self.redo_action)
        find_and_replace_action = QAction('Find and Replace...', parent=self)
        find_and_replace_action.setShortcut(QKeySequence('Ctrl+R'))
        find_and_replace_action.triggered.connect(
            self.show_find_and_replace_dialog)
        edit_menu.addAction(find_and_replace_action)
        batch_reorder_tags_action = QAction('Batch Reorder Tags...',
                                            parent=self)
        batch_reorder_tags_action.setShortcut(QKeySequence('Ctrl+B'))
        batch_reorder_tags_action.triggered.connect(
            self.show_batch_reorder_tags_dialog)
        edit_menu.addAction(batch_reorder_tags_action)
        remove_duplicate_tags_action = QAction('Remove Duplicate Tags',
                                               parent=self)
        remove_duplicate_tags_action.setShortcut(QKeySequence('Ctrl+D'))
        remove_duplicate_tags_action.triggered.connect(
            self.remove_duplicate_tags)
        edit_menu.addAction(remove_duplicate_tags_action)
        remove_empty_tags_action = QAction('Remove Empty Tags', parent=self)
        remove_empty_tags_action.setShortcut(QKeySequence('Ctrl+E'))
        remove_empty_tags_action.triggered.connect(
            self.remove_empty_tags)
        edit_menu.addAction(remove_empty_tags_action)


        # Add new action for JSON Tags editor
        self.toggle_json_tags_editor_action = QAction('JSON Tags', parent=self)

        view_menu = menu_bar.addMenu('View')
        self.toggle_image_list_action.setCheckable(True)
        self.toggle_image_tags_editor_action.setCheckable(True)
        self.toggle_json_tags_editor_action.setCheckable(True)
        self.toggle_all_tags_editor_action.setCheckable(True)
        self.toggle_auto_captioner_action.setCheckable(True)
        self.toggle_image_list_action.triggered.connect(
            lambda is_checked: self.image_list.setVisible(is_checked))
        self.toggle_image_tags_editor_action.triggered.connect(
            lambda is_checked: self.image_tags_editor.setVisible(is_checked))
        self.toggle_json_tags_editor_action.triggered.connect(  # Connect the new action
            lambda is_checked: self.json_tags_editor.setVisible(is_checked))
        self.toggle_all_tags_editor_action.triggered.connect(
            lambda is_checked: self.all_tags_editor.setVisible(is_checked))
        self.toggle_auto_captioner_action.triggered.connect(
            lambda is_checked: self.auto_captioner.setVisible(is_checked))
        view_menu.addAction(self.toggle_image_list_action)
        view_menu.addAction(self.toggle_image_tags_editor_action)
        view_menu.addAction(self.toggle_json_tags_editor_action)
        view_menu.addAction(self.toggle_all_tags_editor_action)
        view_menu.addAction(self.toggle_auto_captioner_action)

        help_menu = menu_bar.addMenu('Help')
        open_github_repository_action = QAction('GitHub', parent=self)
        open_github_repository_action.triggered.connect(
            lambda: QDesktopServices.openUrl(QUrl(GITHUB_REPOSITORY_URL)))
        help_menu.addAction(open_github_repository_action)




    @Slot()
    def update_undo_and_redo_actions(self):
        if self.image_list_model.undo_stack:
            undo_action_name = self.image_list_model.undo_stack[-1].action_name
            self.undo_action.setText(f'Undo "{undo_action_name}"')
            self.undo_action.setDisabled(False)
        else:
            self.undo_action.setText('Undo')
            self.undo_action.setDisabled(True)
        if self.image_list_model.redo_stack:
            redo_action_name = self.image_list_model.redo_stack[-1].action_name
            self.redo_action.setText(f'Redo "{redo_action_name}"')
            self.redo_action.setDisabled(False)
        else:
            self.redo_action.setText('Redo')
            self.redo_action.setDisabled(True)

    @Slot()
    def set_image_list_filter(self):
        filter_ = self.image_list.filter_line_edit.parse_filter_text()
        self.proxy_image_list_model.filter = filter_
        # Apply the new filter.
        self.proxy_image_list_model.invalidateFilter()
        if filter_ is None:
            all_tags_list_selection_model = (self.all_tags_editor
                                             .all_tags_list.selectionModel())
            all_tags_list_selection_model.clearSelection()
            # Clear the current index.
            self.all_tags_editor.all_tags_list.setCurrentIndex(QModelIndex())
            # Select the previously selected image in the unfiltered image
            # list.
            select_index = self.settings.value('image_index', type=int) or 0
            self.image_list.list_view.setCurrentIndex(
                self.proxy_image_list_model.index(select_index, 0))
        else:
            # Select the first image.
            self.image_list.list_view.setCurrentIndex(
                self.proxy_image_list_model.index(0, 0))

    @Slot()
    def save_image_index(self, proxy_image_index: QModelIndex):
        """Save the index of the currently selected image."""
        settings_key = ('image_index'
                        if self.proxy_image_list_model.filter is None
                        else 'filtered_image_index')
        self.settings.setValue(settings_key, proxy_image_index.row())

    def connect_image_list_signals(self):
        self.image_list.filter_line_edit.textChanged.connect(
            self.set_image_list_filter)
        self.image_list_selection_model.currentChanged.connect(
            self.save_image_index)
        self.image_list_selection_model.currentChanged.connect(
            self.image_list.update_image_index_label)
        self.image_list_selection_model.currentChanged.connect(
            self.image_viewer.load_image)
        self.image_list_selection_model.currentChanged.connect(
            self.image_tags_editor.load_image_tags)
        self.image_list_selection_model.currentChanged.connect(
            self.json_tags_editor.load_image_tags)
        self.image_list_model.modelReset.connect(
            lambda: self.tag_counter_model.count_tags(
                self.image_list_model.images))
        self.image_list_model.dataChanged.connect(
            lambda: self.tag_counter_model.count_tags(
                self.image_list_model.images))
        self.image_list_model.dataChanged.connect(
            self.image_tags_editor.reload_image_tags_if_changed)
        self.image_list_model.dataChanged.connect(
            self.json_tags_editor.reload_image_tags_if_changed)
        self.image_list_model.update_undo_and_redo_actions_requested.connect(
            self.update_undo_and_redo_actions)
        # Rows are inserted or removed from the proxy image list model when the
        # filter is changed.
        self.proxy_image_list_model.rowsInserted.connect(
            lambda: self.image_list.update_image_index_label(
                self.image_list.list_view.currentIndex()))
        self.proxy_image_list_model.rowsRemoved.connect(
            lambda: self.image_list.update_image_index_label(
                self.image_list.list_view.currentIndex()))
        self.image_list.list_view.directory_reload_requested.connect(
            self.reload_directory)
        self.image_list.list_view.tags_paste_requested.connect(
            self.image_list_model.add_tags)
        # Connecting the signal directly without `isVisible()` causes the menu
        # item to be unchecked when the widget is an inactive tab.
        self.image_list.visibilityChanged.connect(
            lambda: self.toggle_image_list_action.setChecked(
                self.image_list.isVisible()))
        self.image_list_model.dataChanged.connect(
            self.json_tags_editor.reload_image_tags_if_changed)

    @Slot()
    def update_image_tags(self):
        """Update both regular tags and JSON tags."""
        image_index = self.image_tags_editor.image_index
        if image_index is None:
            return

        # Update regular tags
        image: Image = self.image_list_model.data(image_index,
                                                  Qt.ItemDataRole.UserRole)
        old_tags = image.tags
        new_tags = self.image_tag_list_model.stringList()

        if old_tags == new_tags:
            return

        old_tags_count = len(old_tags)
        new_tags_count = len(new_tags)

        if new_tags_count > old_tags_count:
            self.image_list_model.add_to_undo_stack(
                action_name='Add Tag', should_ask_for_confirmation=False)
        elif new_tags_count == old_tags_count:
            if set(new_tags) == set(old_tags):
                self.image_list_model.add_to_undo_stack(
                    action_name='Reorder Tags',
                    should_ask_for_confirmation=False)
            else:
                self.image_list_model.add_to_undo_stack(
                    action_name='Rename Tag',
                    should_ask_for_confirmation=False)
        elif old_tags_count - new_tags_count == 1:
            self.image_list_model.add_to_undo_stack(
                action_name='Delete Tag', should_ask_for_confirmation=False)
        else:
            self.image_list_model.add_to_undo_stack(
                action_name='Delete Tags', should_ask_for_confirmation=False)

        self.image_list_model.update_image_tags(image_index, new_tags)


    def connect_image_tags_editor_signals(self):

        #New
        self.image_tag_list_model.modelReset.connect(self.update_text_tags)
        self.image_tag_list_model.dataChanged.connect(self.update_text_tags)
        self.image_tag_list_model.rowsMoved.connect(self.update_text_tags)

        # Regular tag editor visibility
        self.image_tags_editor.visibilityChanged.connect(
            lambda: self.toggle_image_tags_editor_action.setChecked(
                self.image_tags_editor.isVisible()))

        # JSON tag editor visibility
        self.json_tags_editor.visibilityChanged.connect(
            lambda: self.toggle_json_tags_editor_action.setChecked(
                self.json_tags_editor.isVisible()))

        # Connect tag addition signals to separate handlers
        self.image_tags_editor.tag_input_box.tags_addition_requested.connect(
            self.add_text_tags)
        self.json_tags_editor.tag_input_box.tags_addition_requested.connect(
            self.add_json_tags)

    @Slot(list, list)
    def add_text_tags(self, tags: List[str], image_indices: List[QModelIndex]):
        """Handle adding text tags"""
        self.image_list_model.add_tags(tags, image_indices)
        self.image_tags_editor.select_last_tag()

    def read_json_tags(self, image_path: Path) -> dict:
        """Read JSON tags from file"""
        empty_tags = {
            "characters": [],
            "settings": [],
            "actions": []
        }

        try:
            json_path = image_path.with_suffix('.json')
            if json_path.exists():
                with json_path.open('r', encoding='utf-8') as f:
                    return json.load(f)
        except (OSError, json.JSONDecodeError) as e:
            print(f"Error reading JSON tags: {str(e)}")

        return empty_tags

    @Slot(list, list)
    def add_json_tags(self, tags: List[str], image_indices: List[QModelIndex]):
        """Handle adding JSON tags"""
        if not image_indices:
            return

        current_image_index = image_indices[0]  # Use the first selected image
        image: Image = self.image_list_model.data(current_image_index, Qt.ItemDataRole.UserRole)

        if not image:
            return

        try:
            # Read existing JSON tags
            json_tags = self.read_json_tags(image.path)

            # Process new tags
            for tag in tags:
                if tag.startswith("character:"):
                    value = tag.replace("character:", "").strip()
                    if value not in json_tags["characters"]:
                        json_tags["characters"].append(value)
                elif tag.startswith("setting:"):
                    value = tag.replace("setting:", "").strip()
                    if value not in json_tags["settings"]:
                        json_tags["settings"].append(value)
                elif tag.startswith("action:"):
                    value = tag.replace("action:", "").strip()
                    if value not in json_tags["actions"]:
                        json_tags["actions"].append(value)

            # Save updated JSON tags
            self.write_json_tags(image.path, json_tags)

            # Update the JSON tags display
            self.json_tags_editor.current_json_tags = json_tags
            self.json_tags_editor.update_display()

        except Exception as e:
            print(f"Error processing JSON tags: {str(e)}")

    def write_json_tags(self, image_path: Path, tags: dict):
        """Write JSON tags to file"""
        try:
            json_path = image_path.with_suffix('.json')
            with json_path.open('w', encoding='utf-8') as f:
                json.dump(tags, f, indent=2, ensure_ascii=False)
        except OSError as e:
            print(f"Error writing JSON tags: {str(e)}")


    @Slot()
    def set_image_list_filter_text(self, selected_tag: str):
        """
        Construct and set the image list filter text from the selected tag in
        the all tags list.
        """
        escaped_selected_tag = (selected_tag.replace('\\', '\\\\')
                                .replace('"', r'\"').replace("'", r"\'"))
        self.image_list.filter_line_edit.setText(
            f'tag:"{escaped_selected_tag}"')

    @Slot(str)
    def add_tag_to_selected_images(self, tag: str):
        selected_image_indices = self.image_list.get_selected_image_indices()
        self.image_list_model.add_tags([tag], selected_image_indices)
        self.image_tags_editor.select_last_tag()
        self.json_tags_editor.select_last_tag()

    def connect_all_tags_editor_signals(self):
        self.all_tags_editor.clear_filter_button.clicked.connect(
            self.image_list.filter_line_edit.clear)
        self.tag_counter_model.tags_renaming_requested.connect(
            self.image_list_model.rename_tags)
        self.tag_counter_model.tags_renaming_requested.connect(
            self.image_list.filter_line_edit.clear)
        self.all_tags_editor.all_tags_list.image_list_filter_requested.connect(
            self.set_image_list_filter_text)
        self.all_tags_editor.all_tags_list.tag_addition_requested.connect(
            self.add_tag_to_selected_images)
        self.all_tags_editor.all_tags_list.tags_deletion_requested.connect(
            self.image_list_model.delete_tags)
        self.all_tags_editor.all_tags_list.tags_deletion_requested.connect(
            self.image_list.filter_line_edit.clear)
        self.all_tags_editor.visibilityChanged.connect(
            lambda: self.toggle_all_tags_editor_action.setChecked(
                self.all_tags_editor.isVisible()))

    def connect_auto_captioner_signals(self):
        self.auto_captioner.caption_generated.connect(
            lambda image_index, _, tags:
            self.image_list_model.update_image_tags(image_index, tags))
        self.auto_captioner.caption_generated.connect(
            lambda image_index, *_:
            self.image_tags_editor.reload_image_tags_if_changed(image_index,
                                                                image_index))
        self.auto_captioner.caption_generated.connect(
            lambda image_index, *_:
            self.image_tags_editor.reload_image_tags_if_changed(image_index,
                                                                image_index))
        self.auto_captioner.visibilityChanged.connect(
            lambda: self.toggle_auto_captioner_action.setChecked(
                self.auto_captioner.isVisible()))

    @Slot()
    def update_text_tags(self):
        """Update only text-based tags"""
        image_index = self.image_tags_editor.image_index
        if image_index is None:
            return

        image: Image = self.image_list_model.data(image_index, Qt.ItemDataRole.UserRole)
        if not image:
            return

        old_tags = image.tags
        new_tags = self.image_tag_list_model.stringList()

        if old_tags == new_tags:
            return

        # Update undo stack
        old_tags_count = len(old_tags)
        new_tags_count = len(new_tags)

        if new_tags_count > old_tags_count:
            self.image_list_model.add_to_undo_stack(
                action_name='Add Text Tag', should_ask_for_confirmation=False)
        elif new_tags_count == old_tags_count:
            if set(new_tags) == set(old_tags):
                self.image_list_model.add_to_undo_stack(
                    action_name='Reorder Text Tags',
                    should_ask_for_confirmation=False)
            else:
                self.image_list_model.add_to_undo_stack(
                    action_name='Rename Text Tag',
                    should_ask_for_confirmation=False)
        elif old_tags_count - new_tags_count == 1:
            self.image_list_model.add_to_undo_stack(
                action_name='Delete Text Tag', should_ask_for_confirmation=False)
        else:
            self.image_list_model.add_to_undo_stack(
                action_name='Delete Text Tags', should_ask_for_confirmation=False)

        # Save to txt file
        try:
            txt_path = image.path.with_suffix('.txt')
            txt_path.write_text('\n'.join(new_tags), encoding='utf-8')
        except OSError as e:
            print(f"Error saving text tags: {str(e)}")

        self.image_list_model.update_image_tags(image_index, new_tags)

    @Slot()
    def update_json_tags(self):
        """Update only JSON-based tags, saving to .json files"""
        image_index = self.json_tags_editor.image_index
        if image_index is None:
            return

        try:
            # Get the current image
            image: Image = self.image_list_model.data(image_index, Qt.ItemDataRole.UserRole)
            if not image:
                return

            # Get the current JSON tags from the model
            display_tags = self.json_tag_list_model.stringList()

            # Convert display tags to JSON structure
            json_tags = {
                "characters": [],
                "settings": [],
                "actions": []
            }

            # Parse the tags back into JSON structure
            for tag in display_tags:
                try:
                    category, value = tag.split(':', 1)
                    if category == 'character':
                        json_tags['characters'].append(value)
                    elif category == 'setting':
                        json_tags['settings'].append(value)
                    elif category == 'action':
                        json_tags['actions'].append(value)
                except ValueError:
                    continue

            # Write JSON tags to disk
            json_path = image.path.with_suffix('.json')
            with json_path.open('w', encoding='utf-8') as f:
                json.dump(json_tags, f, indent=2, ensure_ascii=False)

        except Exception as e:
            print(f"Error updating JSON tags: {str(e)}")

    def restore(self):
        # Restore the window geometry and state.
        if self.settings.contains('geometry'):
            self.restoreGeometry(self.settings.value('geometry', type=bytes))
        else:
            self.showMaximized()
        self.restoreState(self.settings.value('window_state', type=bytes))
        # Get the last index of the last selected image.
        if self.settings.contains('image_index'):
            image_index = self.settings.value('image_index', type=int)
        else:
            image_index = 0
        # Load the last loaded directory.
        if self.settings.contains('directory_path'):
            directory_path = Path(self.settings.value('directory_path',
                                                      type=str))
            if directory_path.is_dir():
                self.load_directory(
                    Path(self.settings.value('directory_path', type=str)),
                    select_index=image_index)

    # Add these methods to the MainWindow class
    def get_sibling_directories(self, current_dir: Path) -> list[Path]:
        """Get a sorted list of sibling directories (directories at the same level)."""
        print(f"Getting siblings for: {current_dir}")  # Debug print
        if not current_dir or not current_dir.parent.exists():
            return []

        siblings = [d for d in current_dir.parent.iterdir()
                    if d.is_dir() and not d.name.startswith('.')]
        return sorted(siblings)

    @Slot()
    def navigate_to_next_directory(self):
        """Navigate to the next sibling directory."""
        print("Navigate to next directory triggered")  # Debug print
        if not self.settings.contains('directory_path'):
            return

        current_dir = Path(self.settings.value('directory_path'))
        siblings = self.get_sibling_directories(current_dir)

        if not siblings:
            return

        try:
            current_index = siblings.index(current_dir)
            next_index = (current_index + 1) % len(siblings)
            next_dir = siblings[next_index]
            if next_dir.exists():
                self.load_directory(next_dir)
        except ValueError:
            return

    @Slot()
    def navigate_to_previous_directory(self):
        """Navigate to the previous sibling directory."""
        print("Navigate to previous directory triggered")  # Debug print
        if not self.settings.contains('directory_path'):
            return

        current_dir = Path(self.settings.value('directory_path'))
        siblings = self.get_sibling_directories(current_dir)

        if not siblings:
            return

        try:
            current_index = siblings.index(current_dir)
            prev_index = (current_index - 1) % len(siblings)
            prev_dir = siblings[prev_index]
            if prev_dir.exists():
                self.load_directory(prev_dir)
        except ValueError:
            return

    def get_next_directory(self, current_dir: Path) -> Optional[Path]:
        """Get the next directory alphabetically."""
        siblings = self.get_sibling_directories(current_dir)
        if not siblings:
            return None

        try:
            current_index = siblings.index(current_dir)
            # Get next directory, wrap around to first if at end
            next_index = (current_index + 1) % len(siblings)
            return siblings[next_index]
        except ValueError:
            return None

    def get_previous_directory(self, current_dir: Path) -> Optional[Path]:
        """Get the previous directory alphabetically."""
        siblings = self.get_sibling_directories(current_dir)
        if not siblings:
            return None

        try:
            current_index = siblings.index(current_dir)
            # Get previous directory, wrap around to last if at start
            prev_index = (current_index - 1) % len(siblings)
            return siblings[prev_index]
        except ValueError:
            return None


