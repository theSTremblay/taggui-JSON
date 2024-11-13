import os
from pathlib import Path
from dotenv import load_dotenv
from utils.tag_sorter import TagSorter
import torch


def check_gpu_requirements():
    """Check if GPU meets requirements and return memory configuration"""
    if torch.cuda.is_available():
        gpu_name = torch.cuda.get_device_name(0)
        gpu_memory = torch.cuda.get_device_properties(0).total_memory / 1e9  # Convert to GB

        print(f"\nGPU Information:")
        print(f"Name: {gpu_name}")
        print(f"Memory: {gpu_memory:.2f}GB")
        print(f"CUDA Version: {torch.version.cuda}")

        if gpu_memory < 8:
            print("\nWarning: Low GPU memory detected. Using CPU offload configuration.")
            return True, "low_memory"
        return True, "high_memory"
    return False, "cpu"


def setup_llm():
    """Set up the LLM environment with FLAN-T5-base"""
    load_dotenv()

    # Check GPU
    has_gpu = check_gpu_requirements()
    if not has_gpu:
        print("\nWarning: No GPU found. Model will run on CPU which will be slower.")
        user_input = input("Continue anyway? (y/n): ")
        if user_input.lower() != 'y':
            raise RuntimeError("Setup cancelled by user")

    # Get token from environment
    hf_token = os.getenv('HUGGING_FACE_TOKEN')
    if not hf_token:
        raise ValueError(
            "HuggingFace token not found in environment variables.\n"
            "Please create a .env file with your HUGGING_FACE_TOKEN or set it manually.\n"
            "Get your token from: https://huggingface.co/settings/tokens"
        )

    # Define model path for FLAN-T5-base
    root_dir = Path(__file__).parent.absolute()
    model_path = root_dir / "models" / "flan-t5-base"  # Updated path

    try:
        print("\nVerifying model files...")
        temp_sorter = TagSorter()

        if model_path.exists():
            verification_result = temp_sorter.verify_model_files(model_path)
            if not all(verification_result.values()):
                print("Model files incomplete. Starting download...")
                if not TagSorter.download_model(str(model_path), hf_token):
                    raise RuntimeError("Failed to download model files")
        else:
            print(f"Downloading model to: {model_path}")
            if not TagSorter.download_model(str(model_path), hf_token):
                raise RuntimeError("Failed to download model")

        print("\nInitializing TagSorter...")
        tag_sorter = TagSorter(
            local_model_path=str(model_path),
            hf_token=hf_token
        )

        return tag_sorter

    except Exception as e:
        print(f"\nError during setup: {str(e)}")
        raise RuntimeError(f"Failed to initialize TagSorter: {str(e)}")