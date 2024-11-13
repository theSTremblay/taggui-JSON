import torch
import sys
import os


def check_cuda_setup():
    print("\n=== CUDA Setup Diagnostics ===")
    print(f"PyTorch Version: {torch.__version__}")
    print(f"CUDA is available: {torch.cuda.is_available()}")

    if torch.cuda.is_available():
        print(f"CUDA Device Count: {torch.cuda.device_count()}")
        print(f"Current CUDA Device: {torch.cuda.current_device()}")
        print(f"CUDA Device Name: {torch.cuda.get_device_name(0)}")
        print(f"CUDA Version: {torch.version.cuda}")
    else:
        print("\nCUDA is not available. Checking system:")
        # Check if CUDA paths exist
        cuda_paths = [
            "C:\\Program Files\\NVIDIA GPU Computing Toolkit\\CUDA\\v11.8",
            "C:\\Program Files\\NVIDIA GPU Computing Toolkit\\CUDA\\v12.1"
        ]
        for path in cuda_paths:
            print(f"Checking CUDA path: {path}")
            print(f"Exists: {os.path.exists(path)}")

        # Check if CUDA is in PATH
        path_env = os.environ.get('PATH', '')
        cuda_in_path = any('cuda' in p.lower() for p in path_env.split(os.pathsep))
        print(f"\nCUDA in PATH: {cuda_in_path}")


if __name__ == "__main__":
    check_cuda_setup()