import os
from typing import List

root_dir = os.path.join(os.path.dirname(__file__), "..", "..")  # root of this project


def prune_dir(keeps: List[str], base_dir="cdk") -> List[str]:
    """used for the DockerImageCode `exclude` parameter so that simple stack updates dont require a new Docker image"""
    excludes = []
    for lib_dir in os.listdir(os.path.join(root_dir, base_dir)):
        if lib_dir not in keeps:
            excludes.append(os.path.join(base_dir, lib_dir))
    return excludes
