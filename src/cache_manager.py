"""
cache_manager.py

Save and load cached pipeline data.
"""

from pathlib import Path
import pickle


def save_cache(data, filename):
    """
    Save an object to a pickle file.
    """

    path = Path(filename)
    path.parent.mkdir(parents=True, exist_ok=True)

    with open(path, "wb") as file:
        pickle.dump(data, file)


def load_cache(filename):
    """
    Load an object from a pickle file.
    """

    with open(filename, "rb") as file:
        return pickle.load(file)
