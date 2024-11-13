import logging
import os
import sys
import traceback
import warnings

import transformers
from PySide6.QtGui import QImageReader
from PySide6.QtWidgets import QApplication, QMessageBox

from utils.settings import get_settings
from widgets.main_window import MainWindow
from dotenv import load_dotenv
from setup_llm import setup_llm  # Add this import



def suppress_warnings():
    """Suppress all warnings when not in a development environment."""
    environment = os.getenv('TAGGUI_ENVIRONMENT')
    if environment == 'development':
        print('Running in development environment.')
        return
    logging.basicConfig(level=logging.ERROR)
    warnings.simplefilter('ignore')
    transformers.logging.set_verbosity_error()
    try:
        import auto_gptq
        auto_gptq_logger = logging.getLogger(auto_gptq.modeling._base.__name__)
        auto_gptq_logger.setLevel(logging.ERROR)
    except ImportError:
        pass


def run_gui():
    # Load environment variables
    load_dotenv()
    # Initialize the LLM
    tag_sorter = None  # Initialize as None in case setup fails
    try:
        tag_sorter = setup_llm()
        print("LLM initialized successfully")
    except Exception as e:
        print(f"Failed to initialize LLM: {e}")
        # Continue without LLM functionality

    app = QApplication([])
    # The application name is shown in the taskbar.
    app.setApplicationName('TagGUI')
    # The application display name is shown in the title bar.
    app.setApplicationDisplayName('TagGUI')
    app.setStyle('Fusion')
    # Disable the allocation limit to allow loading large images.
    QImageReader.setAllocationLimit(0)
    main_window = MainWindow(app, tag_sorter=tag_sorter)
    main_window.show()
    sys.exit(app.exec())


if __name__ == '__main__':
    # Suppress all warnings when not in a development environment.
    suppress_warnings()
    try:
        run_gui()
    except Exception as exception:
        settings = get_settings()
        settings.clear()
        error_message_box = QMessageBox()
        error_message_box.setWindowTitle('Error')
        error_message_box.setIcon(QMessageBox.Icon.Critical)
        error_message_box.setText(str(exception))
        error_message_box.setDetailedText(traceback.format_exc())
        error_message_box.exec()
        raise exception
