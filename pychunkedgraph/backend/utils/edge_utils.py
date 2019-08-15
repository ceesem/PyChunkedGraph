"""
helper functions for edge stuff
"""

from typing import Tuple

import numpy as np

from pychunkedgraph.utils.general import reverse_dictionary
from ..definitions.edges import Edges, IN_CHUNK, BT_CHUNK, CX_CHUNK


def concatenate_chunk_edges(chunk_edge_dicts: list) -> dict:
    """combine edge_dicts of multiple chunks into one edge_dict"""
    edges_dict = {}
    for edge_type in [IN_CHUNK, BT_CHUNK, CX_CHUNK]:
        sv_ids1 = []
        sv_ids2 = []
        affinities = []
        areas = []
        for edge_d in chunk_edge_dicts:
            edges = edge_d[edge_type]
            sv_ids1.append(edges.node_ids1)
            sv_ids2.append(edges.node_ids2)
            affinities.append(edges.affinities)
            areas.append(edges.areas)

        sv_ids1 = np.concatenate(sv_ids1)
        sv_ids2 = np.concatenate(sv_ids2)
        affinities = np.concatenate(affinities)
        areas = np.concatenate(areas)
        edges_dict[edge_type] = Edges(sv_ids1, sv_ids2, affinities, areas)
    return edges_dict


def filter_edges(node_ids: np.ndarray, edges_dict: dict) -> Edges:
    """find edges for the given node_ids from the dict"""
    ids1 = []
    ids2 = []
    affinities = []
    areas = []
    for edge_type in [IN_CHUNK, BT_CHUNK, CX_CHUNK]:
        edges = edges_dict[edge_type]
        xsorted = np.argsort(edges.node_ids1)
        indices = np.searchsorted(edges.node_ids1[xsorted], node_ids)
        indices = indices[indices < xsorted.size]

        ids1.append(edges.node_ids1[indices])
        ids2.append(edges.node_ids2[indices])
        affinities.append(edges.affinities[indices])
        areas.append(edges.areas[indices])
    ids1 = np.concatenate(ids1)
    ids2 = np.concatenate(ids2)
    affinities = np.concatenate(affinities)
    areas = np.concatenate(areas)
    return Edges(ids1, ids2, affinities, areas)


def flatten_parents_children(children_d: dict) -> [np.ndarray, np.ndarray]:
    """
    given a dictionary - d["parent_id"] = [children]
    return [[parent_id]*len(children), children]
    """
    parent_ids = []
    child_ids = []
    for parent_id, children in children_d.items():
        parent_ids.append([parent_id] * children.size)
        child_ids.append(children)
    parent_ids = np.concatenate(parent_ids)
    child_ids = np.concatenate(child_ids)
    return parent_ids, child_ids


def get_active_edges(edges: Edges, parent_children_d: dict) -> Edges:
    """
    get edges [(v1, v2) ...] where parent(v1) == parent(v2)
    assume connected if v1 and v2 belong to same connected component
    """
    child_parent_d = reverse_dictionary(parent_children_d)

    sv_ids1 = edges.node_ids1
    sv_ids2 = edges.node_ids2
    affinities = edges.affinities
    areas = edges.areas
    parent_ids1 = np.array([child_parent_d.get(sv_id, sv_id) for sv_id in sv_ids1])
    parent_ids2 = np.array([child_parent_d.get(sv_id, sv_id) for sv_id in sv_ids2])

    sv_ids1 = sv_ids1[parent_ids1 == parent_ids2]
    sv_ids2 = sv_ids2[parent_ids1 == parent_ids2]
    affinities = affinities[parent_ids1 == parent_ids2]
    areas = areas[parent_ids1 == parent_ids2]

    return Edges(sv_ids1, sv_ids2, affinities, areas)