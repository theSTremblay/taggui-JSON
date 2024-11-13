import os
from pathlib import Path
from dotenv import load_dotenv
from utils.tag_sorter import TagSorter


def setup_llm():
    """
    Set up the LLM environment and download model if needed
    """
    # Load environment variables from .env file
    load_dotenv()

    # Get token from environment
    hf_token = os.getenv('HUGGING_FACE_TOKEN')

    if not hf_token:
        raise ValueError(
            "HuggingFace token not found in environment variables.\n"
            "Please create a .env file with your HUGGING_FACE_TOKEN or set it manually.\n"
            "Get your token from: https://huggingface.co/settings/tokens"
        )

    # Define model path relative to project root
    root_dir = Path(__file__).parent
    model_path = root_dir / "models" / "mistral-7b"

    # Download model if not exists
    if not model_path.exists():
        print("Downloading Mistral model (this may take a while)...")
        if not TagSorter.download_model(str(model_path), token=hf_token):
            raise RuntimeError("Failed to download model")

    # Initialize TagSorter
    try:
        tag_sorter = TagSorter(
            local_model_path=str(model_path),
            hf_token=hf_token
        )
        print("LLM initialized successfully")
        return tag_sorter
    except Exception as e:
        raise RuntimeError(f"Failed to initialize TagSorter: {e}")