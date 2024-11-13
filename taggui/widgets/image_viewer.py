from pathlib import Path

from PySide6.QtCore import QModelIndex, QSize, Qt, Slot
from PySide6.QtGui import QImageReader, QPixmap, QResizeEvent
from PySide6.QtWidgets import (QLabel, QSizePolicy, QVBoxLayout, QWidget,
                              QRubberBand, QMessageBox, QDialog)
from models.proxy_image_list_model import ProxyImageListModel
from utils.image import Image

from PySide6.QtCore import Qt, QRect, QPoint, Signal, Slot
from PySide6.QtGui import QPainter, QPen, QColor
from PySide6.QtWidgets import QRubberBand, QMessageBox
from PIL import Image as PILImage
import os
from .clipping_tag_dialog import ClippingTagDialog  # Add this import
import json


class ImageLabel(QLabel):
    clip_created = Signal(QRect)

    def __init__(self):
        super().__init__()
        self.rubberBand = None
        self.origin = QPoint()
        self.is_clipping_mode = False
        self.current_image_rect = None
        # Keep existing ImageLabel functionality
        self.image_path = None
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setSizePolicy(QSizePolicy.Policy.Expanding,
                           QSizePolicy.Policy.Expanding)
        self.setMinimumSize(QSize(1, 1))

    def resizeEvent(self, event: QResizeEvent):
        """Reload the image whenever the label is resized."""
        if self.image_path:
            self.load_image(self.image_path)

    def load_image(self, image_path: Path):
        """Keep existing load_image functionality"""
        self.image_path = image_path
        image_reader = QImageReader(str(image_path))
        image_reader.setAutoTransform(True)
        pixmap = QPixmap.fromImageReader(image_reader)
        pixmap.setDevicePixelRatio(self.devicePixelRatio())
        pixmap = pixmap.scaled(
            self.size() * pixmap.devicePixelRatio(),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation)
        self.setPixmap(pixmap)

        # Store the actual image rect for proper coordinate transformation
        if pixmap:
            self.current_image_rect = self.get_actual_image_rect()

    def get_actual_image_rect(self) -> QRect:
        """Get the actual rectangle where the image is displayed"""
        if not self.pixmap():
            return QRect()

        # Calculate the actual rectangle where the image is displayed
        pw = self.pixmap().width() / self.devicePixelRatio()
        ph = self.pixmap().height() / self.devicePixelRatio()
        w = self.width()
        h = self.height()

        if pw * h > ph * w:
            # Width limited
            scaled_h = int(ph * w / pw)
            return QRect(0, (h - scaled_h) // 2, w, scaled_h)
        else:
            # Height limited
            scaled_w = int(pw * h / ph)
            return QRect((w - scaled_w) // 2, 0, scaled_w, h)

    # Add new clipping-related methods
    def enterClippingMode(self):
        """Enable clipping mode"""
        self.is_clipping_mode = True
        self.setCursor(Qt.CursorShape.CrossCursor)

    def exitClippingMode(self):
        """Disable clipping mode"""
        self.is_clipping_mode = False
        self.setCursor(Qt.CursorShape.ArrowCursor)
        if self.rubberBand:
            self.rubberBand.hide()
            self.rubberBand = None

    def mousePressEvent(self, event):
        if not self.is_clipping_mode or not self.pixmap():
            return

        self.origin = event.pos()
        if not self.rubberBand:
            self.rubberBand = QRubberBand(QRubberBand.Shape.Rectangle, self)
        self.rubberBand.setGeometry(QRect(self.origin, QPoint()))
        self.rubberBand.show()

    def mouseMoveEvent(self, event):
        if not self.is_clipping_mode or not self.rubberBand:
            return

        self.rubberBand.setGeometry(QRect(self.origin, event.pos()).normalized())

    def mouseReleaseEvent(self, event):
        if not self.is_clipping_mode or not self.rubberBand:
            return

        clip_rect = self.rubberBand.geometry()
        if clip_rect.width() < 10 or clip_rect.height() < 10:
            QMessageBox.warning(self, "Invalid Selection",
                                "Selection area is too small. Please make a larger selection.")
            self.rubberBand.hide()
            return

        # Convert the selection rectangle to image coordinates
        if self.current_image_rect:
            # Get original image dimensions
            image_reader = QImageReader(str(self.image_path))
            original_width = image_reader.size().width()
            original_height = image_reader.size().height()

            # Calculate scaling factors
            display_rect = self.current_image_rect
            scale_x = original_width / display_rect.width()
            scale_y = original_height / display_rect.height()

            # Transform coordinates to image space
            image_x = int((clip_rect.x() - display_rect.x()) * scale_x)
            image_y = int((clip_rect.y() - display_rect.y()) * scale_y)
            image_width = int(clip_rect.width() * scale_x)
            image_height = int(clip_rect.height() * scale_y)

            # Create the final rectangle in image coordinates
            image_clip_rect = QRect(image_x, image_y, image_width, image_height)

            self.clip_created.emit(image_clip_rect)

        self.rubberBand.hide()


class ImageViewer(QWidget):
    def __init__(self, proxy_image_list_model, tag_sorter=None):
        super().__init__()
        self.proxy_image_list_model = proxy_image_list_model
        self.tag_sorter = tag_sorter
        self.image_label = ImageLabel()
        QVBoxLayout(self).addWidget(self.image_label)

        # Connect the clip_created signal
        self.image_label.clip_created.connect(self.handle_clip_created)
        self.current_image_path = None

    @Slot()
    def load_image(self, proxy_image_index):
        """Load an image from the model"""
        image = self.proxy_image_list_model.data(
            proxy_image_index, Qt.ItemDataRole.UserRole)
        self.current_image_path = image.path
        self.image_label.load_image(image.path)

    # Add new clipping-related methods
    def enterClippingMode(self):
        """Enable clipping mode"""
        self.image_label.enterClippingMode()

    def exitClippingMode(self):
        """Disable clipping mode"""
        self.image_label.exitClippingMode()

    def handle_clip_created(self, clip_rect):
        """Handle the creation of a new clip"""
        if not self.current_image_path:
            return

        try:
            # Open the original image with PIL
            with PILImage.open(str(self.current_image_path)) as img:
                # Crop the image using the corrected coordinates
                cropped = img.crop((
                    max(0, clip_rect.x()),
                    max(0, clip_rect.y()),
                    min(img.width, clip_rect.x() + clip_rect.width()),
                    min(img.height, clip_rect.y() + clip_rect.height())
                ))

                # Generate the new filename
                base_path = os.path.splitext(str(self.current_image_path))[0]
                extension = os.path.splitext(str(self.current_image_path))[1]

                # Find the next available clip number
                clip_num = 1
                while True:
                    new_path = f"{base_path}_clip{clip_num}{extension}"
                    if not os.path.exists(new_path):
                        break
                    clip_num += 1

                # Save the cropped image
                cropped.save(new_path)
                new_path = Path(new_path)

                # Show the tagging dialog
                dialog = ClippingTagDialog(new_path, self, tag_sorter=self.tag_sorter)  # Pass tag_sorter to dialog
                dialog.tags_confirmed.connect(self.save_clip_tags)

                if dialog.exec() == QDialog.DialogCode.Rejected:
                    # If dialog was canceled, delete the saved clip
                    try:
                        os.remove(new_path)
                    except OSError:
                        pass
                    return

        except Exception as e:
            QMessageBox.critical(self, "Error",
                                 f"Failed to save clip: {str(e)}")

    def save_clip_tags(self, tags: dict, clip_path: Path):
        """Save the JSON tags for the clip"""
        try:
            # Save JSON tags only
            json_path = clip_path.with_suffix('.json')
            with open(json_path, 'w', encoding='utf-8') as f:
                json.dump(tags, f, indent=2, ensure_ascii=False)

            QMessageBox.information(self, "Success",
                                    f"Clip saved as: {clip_path.name}")

        except Exception as e:
            QMessageBox.critical(self, "Error",
                                 f"Failed to save clip tags: {str(e)}")
            import traceback
            traceback.print_exc()



    def _copy_associated_files(self, original_path, new_base_path):
        """Copy associated txt and json files for the clip"""
        base_path = os.path.splitext(original_path)[0]

        # Copy txt file if it exists
        txt_path = f"{base_path}.txt"
        if os.path.exists(txt_path):
            with open(txt_path, 'r', encoding='utf-8') as f:
                content = f.read()
            with open(f"{new_base_path}.txt", 'w', encoding='utf-8') as f:
                f.write(content)

        # Copy json file if it exists
        json_path = f"{base_path}.json"
        if os.path.exists(json_path):
            with open(json_path, 'r', encoding='utf-8') as f:
                content = f.read()
            with open(f"{new_base_path}.json", 'w', encoding='utf-8') as f:
                f.write(content)
