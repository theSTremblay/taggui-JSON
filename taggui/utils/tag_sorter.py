from pathlib import Path
from transformers import AutoModelForCausalLM, AutoTokenizer
import torch
import json
from typing import List, Dict
import os
from PySide6.QtCore import QObject, Signal

from huggingface_hub import HfFolder, login
from huggingface_hub.utils import LocalTokenNotFoundError
from huggingface_hub import snapshot_download
from transformers import AutoModelForSeq2SeqLM, AutoTokenizer  # Change from AutoModelForCausalLM





class TagSorter(QObject):
    # Make it a QObject to use Qt signals
    sorting_completed = Signal(dict)
    sorting_failed = Signal(str)  # For error messages

    def __init__(self, local_model_path: str = None, hf_token: str = None):
        super().__init__()

        # Convert string path to Path object
        if local_model_path:
            local_model_path = Path(local_model_path)

        self.device = self._setup_device()
        print(f"Using device: {self.device}")

        # Try to authenticate with HuggingFace
        self._authenticate(hf_token)

        # Use FLAN-T5-small instead
        self.model_id = "google/flan-t5-large"  # Much smaller and more focused model

        try:
            if local_model_path and local_model_path.exists():
                verification_result = self.verify_model_files(local_model_path)
                if all(verification_result.values()):
                    self.model_id = str(local_model_path)
                    print("All model files verified successfully")
                else:
                    missing = [f for f, exists in verification_result.items() if not exists]
                    print(f"Missing required files: {missing}")
                    print(f"Falling back to HuggingFace: {self.model_id}")

            print(f"Loading model from: {self.model_id}")

            # Load tokenizer
            self.tokenizer = AutoTokenizer.from_pretrained(
                self.model_id,
                token=hf_token
            )

            # Configure model loading
            load_config = {
                "torch_dtype": torch.float16,
                "device_map": "auto",
                "token": hf_token
            }

            # Add quantization for GPU if available
            if torch.cuda.is_available():
                load_config["load_in_8bit"] = True
                print("Using 8-bit quantization for GPU")

            # Load the model
            self.model = AutoModelForSeq2SeqLM.from_pretrained(
                self.model_id,
                **load_config
            )

            print("Model loaded successfully")

        except Exception as e:
            print(f"Error loading model: {e}")
            raise

    def verify_model_files(self, model_path: Path) -> Dict[str, bool]:
        """Verify all required model files exist"""
        if not isinstance(model_path, Path):
            model_path = Path(model_path)

        required_files = {
            "config.json": False,
            "model.safetensors": False,
            "tokenizer.model": False,
            "tokenizer_config.json": False,
            "generation_config.json": False
        }

        print(f"\nVerifying model files in: {model_path}")
        for file in required_files.keys():
            file_path = model_path / file
            required_files[file] = file_path.exists()
            print(f"Checking {file}: {'✓ Found' if required_files[file] else '✗ Missing'}")

        return required_files

    @staticmethod
    def _authenticate(token: str = None):
        """Authenticate with HuggingFace"""
        try:
            # Try to use provided token
            if token:
                login(token=token)
                return True

            # Try to use token from environment variable
            if 'HUGGING_FACE_TOKEN' in os.environ:
                login(token=os.environ['HUGGING_FACE_TOKEN'])
                return True

            # Try to use token from hub cache
            try:
                token = HfFolder.get_token()
                if token:
                    login(token=token)
                    return True
            except LocalTokenNotFoundError:
                pass

            print("Warning: No HuggingFace token found. Some features may be limited.")
            return False

        except Exception as e:
            print(f"Authentication error: {e}")
            return False

    @staticmethod
    def download_model(save_path: str, token: str) -> bool:
        """Download FLAN-T5-base model"""
        try:
            save_path = Path(save_path)
            print(f"Starting model download to {save_path}")

            save_path.parent.mkdir(parents=True, exist_ok=True)

            snapshot_download(
                repo_id="google/flan-t5-base",  # Updated to base model
                local_dir=str(save_path),
                token=token,
                ignore_patterns=["*.md", "*.txt"],
                local_dir_use_symlinks=False
            )

            print("Model downloaded successfully!")
            return True

        except Exception as e:
            print(f"Error downloading model: {str(e)}")
            import traceback
            traceback.print_exc()
            return False

    def sort_tags(self, tags: List[str]) -> Dict[str, List[str]]:
        result = {
            "characters": [],
            "settings": [],
            "actions": []
        }

        print("\nStarting tag classification:")
        for tag in tags:
            try:
                prompt = self._create_prompt(tag)
                inputs = self.tokenizer(prompt, return_tensors="pt").to(self.device)

                outputs = self.model.generate(
                    **inputs,
                    max_new_tokens=10,
                    num_beams=2,  # Increased for better results
                    temperature=0.3,  # Slightly increased for more confident answers
                    do_sample=False,
                    early_stopping=True
                )

                response = self.tokenizer.decode(outputs[0], skip_special_tokens=True)
                print(f"\nClassifying tag: '{tag}'")
                print(f"Model response: '{response}'")

                # Clean and normalize response
                response = response.upper().strip()

                if "CHARACTER" in response:
                    result["characters"].append(tag)
                    print(f"Classified as CHARACTER: {tag}")
                elif "SETTING" in response:
                    result["settings"].append(tag)
                    print(f"Classified as SETTING: {tag}")
                elif "ACTION" in response:
                    result["actions"].append(tag)
                    print(f"Classified as ACTION: {tag}")
                else:
                    # Enhanced fallback logic
                    if self._looks_like_verb(tag):
                        result["actions"].append(tag)
                        print(f"Fallback - verb pattern detected: {tag}")
                    elif any(living_thing in tag.lower() for living_thing in
                             ['man', 'woman', 'boy', 'girl', 'person', 'dog', 'cat']):
                        result["characters"].append(tag)
                        print(f"Fallback - living entity pattern detected: {tag}")
                    else:
                        result["settings"].append(tag)
                        print(f"Fallback - defaulting to setting: {tag}")

            except Exception as e:
                print(f"Error processing tag '{tag}': {str(e)}")
                continue

        return result

    def _create_prompt(self, tag: str) -> str:
            """Enhanced prompt for FLAN-T5-base"""
            return f"""Task: Classify the word into one category.

    Word to classify: {tag}

    Categories and rules:
    1. CHARACTER: living beings (examples: human, dog, alien, warrior)
    2. SETTING: places or objects (examples: mountain, motorcycle, house, castle)
    3. ACTION: verbs or activities (examples: running, jumping, fighting, explore)

    Choose exactly one category: CHARACTER, SETTING, or ACTION.
    Output only the category name."""

    def _parse_response(self, response: str) -> Dict[str, List[str]]:
        """Parse the LLM response into a proper dictionary with improved error handling"""
        try:
            # Print the raw response for debugging
            print("Raw LLM Response:")
            print(response)

            # Find the JSON block
            start_idx = response.find("{")
            if start_idx == -1:
                print("No JSON object found in response")
                return {"characters": [], "settings": [], "actions": []}

            end_idx = response.rfind("}") + 1
            if end_idx == 0:
                print("No closing brace found in response")
                return {"characters": [], "settings": [], "actions": []}

            json_str = response[start_idx:end_idx]

            # Clean the JSON string
            json_str = json_str.strip()
            json_str = json_str.replace('\n', '')
            json_str = json_str.replace('\\', '')

            # Print cleaned JSON for debugging
            print("\nCleaned JSON string:")
            print(json_str)

            # Parse JSON and ensure proper structure
            try:
                result = json.loads(json_str)
            except json.JSONDecodeError as e:
                print(f"\nJSON Decode Error: {str(e)}")
                print(f"Error at position {e.pos}: {json_str[max(0, e.pos - 20):min(len(json_str), e.pos + 20)]}")
                return {"characters": [], "settings": [], "actions": []}

            # Validate and normalize the result
            normalized_result = {
                "characters": list(set(result.get("characters", []))),
                "settings": list(set(result.get("settings", []))),
                "actions": list(set(result.get("actions", [])))
            }

            return normalized_result

        except Exception as e:
            print(f"Error parsing LLM response: {str(e)}")
            print("Full response:")
            print(response)
            return {"characters": [], "settings": [], "actions": []}

    def _setup_device(self) -> str:
        """Setup and return the appropriate device"""
        if torch.cuda.is_available():
            # Print GPU information
            gpu_name = torch.cuda.get_device_name(0)
            gpu_memory = torch.cuda.get_device_properties(0).total_memory / 1e9  # Convert to GB
            print(f"Found GPU: {gpu_name} with {gpu_memory:.2f}GB memory")

            # Check CUDA version
            cuda_version = torch.version.cuda
            print(f"CUDA Version: {cuda_version}")

            return "cuda"
        else:
            print("No CUDA GPU available. Using CPU.")
            return "cpu"

    def get_gpu_memory_info(self):
        """Get current GPU memory usage"""
        if torch.cuda.is_available():
            current_device = torch.cuda.current_device()
            total_memory = torch.cuda.get_device_properties(current_device).total_memory
            allocated_memory = torch.cuda.memory_allocated(current_device)
            reserved_memory = torch.cuda.memory_reserved(current_device)

            return {
                "total": total_memory / 1e9,  # Convert to GB
                "allocated": allocated_memory / 1e9,
                "reserved": reserved_memory / 1e9
            }
        return None

    def _parse_single_response(self, response: str) -> str:
        """Parse a single classification response"""
        response = response.lower().strip()
        if "character" in response:
            return "character"
        elif "setting" in response:
            return "setting"
        elif "action" in response:
            return "action"
        return "setting"  # default if unclear

    def _looks_like_verb(self, tag: str) -> bool:
        """Simple heuristic to check if a tag looks like a verb"""
        # Common verb endings
        verb_endings = ['ing', 'ed', 'ate', 'ize', 'ise', 'ify']
        tag = tag.lower()
        return any(tag.endswith(ending) for ending in verb_endings)

    def _normalize_response(self, response: str) -> str:
        """Clean up model response to extract category"""
        response = response.upper()
        for category in ["CHARACTER", "SETTING", "ACTION"]:
            if category in response:
                return category
        return "SETTING"  # default


