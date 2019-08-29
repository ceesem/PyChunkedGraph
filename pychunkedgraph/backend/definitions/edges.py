"""
Classes and types for edges
"""

from typing import Optional

import numpy as np

IN_CHUNK = "in"
BT_CHUNK = "between"
CX_CHUNK = "cross"
TYPES = [IN_CHUNK, BT_CHUNK, CX_CHUNK]

DEFAULT_AFFINITY = np.finfo(np.float32).tiny
DEFAULT_AREA = np.finfo(np.float32).tiny


class Edges:
    def __init__(
        self,
        node_ids1: np.ndarray,
        node_ids2: np.ndarray,
        *,
        affinities: Optional[np.ndarray] = None,
        areas: Optional[np.ndarray] = None,
    ):
        assert node_ids1.size == node_ids2.size
        self.node_ids1 = node_ids1
        self.node_ids2 = node_ids2
        self._as_pairs = None

        self.affinities = np.ones(len(self.node_ids1)) * DEFAULT_AFFINITY
        if affinities is not None:
            assert node_ids1.size == affinities.size
            self.affinities = affinities

        self.areas = np.ones(len(self.node_ids1)) * DEFAULT_AREA
        if areas is not None:
            assert node_ids1.size == areas.size
            self.areas = affinities            

    def get_pairs(self):
        """
        return numpy array of edge pairs [[sv1, sv2] ... ]
        """
        if not self._as_pairs is None:
            return self._as_pairs
        self._as_pairs = np.vstack([self.node_ids1, self.node_ids2]).T
        return self._as_pairs
