

"""
Collection of IO read functions.

Generic guidelines:
    - Function names starts with "read_..."
    - Arguments are given in order: path, others
"""

import yaml
import json

from typing import List
from functools import wraps


def read_yaml(file):
    """Read YAML file (returning a dictionary/list)
    
    Arguments:
    ----------
        path [str, pathlib.Path] : YAML file to read
        encoding [str] : Encoding of the file
        
        See arguments in built-in open: https://docs.python.org/3/library/functions.html#open

    Returns:
        YAML file in Python representation
    """
    with open(file, 'r') as f:
        return yaml.safe_load(f)