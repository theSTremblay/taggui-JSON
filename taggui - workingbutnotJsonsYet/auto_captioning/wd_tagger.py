# Based on
# https://huggingface.co/spaces/SmilingWolf/wd-tagger/blob/main/app.py.
import csv
import re
from pathlib import Path

import huggingface_hub
import numpy as np
from PIL import Image as PilImage
from onnxruntime import InferenceSession

KAOMOJIS = ['0_0', '(o)_(o)', '+_+', '+_-', '._.', '<o>_<o>', '<|>_<|>', '=_=',
            '>_<', '3_3', '6_9', '>_o', '@_@', '^_^', 'o_o', 'u_u', 'x_x',
            '|_|', '||_||']


def get_tags_to_exclude(tags_to_exclude_string: str) -> list[str]:
    if not tags_to_exclude_string.strip():
        return []
    tags = re.split(r'(?<!\\),', tags_to_exclude_string)
    tags = [tag.strip().replace(r'\,', ',') for tag in tags]
    return tags


class WdTaggerModel:
    def __init__(self, model_id: str):
        model_path = Path(model_id) / 'model.onnx'
        if not model_path.is_file():
            model_path = huggingface_hub.hf_hub_download(model_id,
                                                         filename='model.onnx')
        tags_path = Path(model_id) / 'selected_tags.csv'
        if not tags_path.is_file():
            tags_path = huggingface_hub.hf_hub_download(
                model_id, filename='selected_tags.csv')
        self.inference_session = InferenceSession(model_path)
        self.tags = []
        self.rating_tags_indices = []
        self.general_tags_indices = []
        self.character_tags_indices = []
        with open(tags_path, 'r') as tags_file:
            reader = csv.DictReader(tags_file)
            for index, line in enumerate(reader):
                tag = line['name']
                if tag not in KAOMOJIS:
                    tag = tag.replace('_', ' ')
                self.tags.append(tag)
                category = line['category']
                if category == '9':
                    self.rating_tags_indices.append(index)
                elif category == '0':
                    self.general_tags_indices.append(index)
                elif category == '4':
                    self.character_tags_indices.append(index)

    def get_inputs(self, image: PilImage) -> np.ndarray:
        # Add a white background to the image in case it has transparent areas.
        canvas = PilImage.new('RGBA', image.size, (255, 255, 255))
        canvas.alpha_composite(image)
        image = canvas.convert('RGB')
        # Pad the image to make it square.
        max_dimension = max(image.size)
        canvas = PilImage.new('RGB', (max_dimension, max_dimension),
                              (255, 255, 255))
        horizontal_padding = (max_dimension - image.width) // 2
        vertical_padding = (max_dimension - image.height) // 2
        canvas.paste(image, (horizontal_padding, vertical_padding))
        # Resize the image to the model's input dimensions.
        _, input_dimension, *_ = self.inference_session.get_inputs()[0].shape
        if max_dimension != input_dimension:
            input_dimensions = (input_dimension, input_dimension)
            image = canvas.resize(input_dimensions,
                                  resample=PilImage.Resampling.BICUBIC)
        # Convert the image to a numpy array.
        image_array = np.array(image, dtype=np.float32)
        # Reverse the order of the color channels.
        image_array = image_array[:, :, ::-1]
        # Add a batch dimension.
        image_array = np.expand_dims(image_array, axis=0)
        return image_array

    def generate_tags(self, image_array: np.ndarray,
                      wd_tagger_settings: dict) -> tuple[tuple, tuple]:
        input_name = self.inference_session.get_inputs()[0].name
        output_name = self.inference_session.get_outputs()[0].name
        probabilities = self.inference_session.run(
            [output_name], {input_name: image_array})[0][0].astype(np.float32)
        # Exclude the rating tags.
        tags = [tag for index, tag in enumerate(self.tags)
                if index not in self.rating_tags_indices]
        probabilities = np.array([
            probability for index, probability in enumerate(probabilities)
            if index not in self.rating_tags_indices
        ])
        min_probability = wd_tagger_settings['min_probability']
        tags_to_exclude_string = wd_tagger_settings['tags_to_exclude']
        tags_to_exclude = get_tags_to_exclude(tags_to_exclude_string)
        tags_and_probabilities = []
        for tag, probability in zip(tags, probabilities):
            if probability < min_probability or tag in tags_to_exclude:
                continue
            tags_and_probabilities.append((tag, probability))
        # Sort the tags by probability.
        tags_and_probabilities.sort(key=lambda x: x[1], reverse=True)
        max_tags = wd_tagger_settings['max_tags']
        tags_and_probabilities = tags_and_probabilities[:max_tags]
        if tags_and_probabilities:
            tags, probabilities = zip(*tags_and_probabilities)
        else:
            tags, probabilities = (), ()
        return tags, probabilities
