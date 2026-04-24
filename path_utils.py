import os
import sys

def get_root_dir():
    """
    Returns the root directory of the application.
    - In development (running .py): returns the directory of the script.
    - In production (running .exe): returns the directory containing the .exe.
    """
    if getattr(sys, 'frozen', False):
        # Running in a bundle (PyInstaller)
        return os.path.dirname(sys.executable)
    else:
        # Running in normal Python environment
        return os.path.dirname(os.path.abspath(__file__))

def get_asset_path(relative_path):
    """
    Returns the absolute path to an asset file/folder.
    Tries both the root and the '_internal' folder (PyInstaller 6.x default).
    """
    root = get_root_dir()
    # Try root first (siblings of .exe)
    path = os.path.join(root, relative_path)
    if os.path.exists(path):
        return path
    
    # Try _internal folder next
    internal_path = os.path.join(root, "_internal", relative_path)
    if os.path.exists(internal_path):
        return internal_path
        
    return path
