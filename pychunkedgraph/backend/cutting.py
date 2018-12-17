import numpy as np
import networkx as nx
import itertools
import logging
from networkx.algorithms.flow import shortest_augmenting_path, edmonds_karp, preflow_push
from networkx.algorithms.connectivity import minimum_st_edge_cut
import igraph
import graph_tool.all, graph_tool.topology, graph_tool.flow
import time


from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple, Union

float_max = np.finfo(np.float32).max


def merge_cross_chunk_edges(edges: Iterable[Sequence[np.uint64]],
                            affs: Sequence[np.uint64],
                            logger: Optional[logging.Logger] = None):
    """ Merges cross chunk edges
    :param edges: n x 2 array of uint64s
    :param affs: float array of length n
    :return:
    """

    # mask for edges that have to be merged
    cross_chunk_edge_mask = np.isinf(affs)

    # graph with edges that have to be merged
    cross_chunk_graph = nx.Graph()
    cross_chunk_graph.add_edges_from(edges[cross_chunk_edge_mask])

    # connected components in this graph will be combined in one component
    ccs = nx.connected_components(cross_chunk_graph)

    remapping = {}
    mapping = np.array([], dtype=np.uint64).reshape(-1, 2)

    for cc in ccs:
        nodes = np.array(list(cc))
        rep_node = np.min(nodes)

        remapping[rep_node] = nodes

        rep_nodes = np.ones(len(nodes), dtype=np.uint64).reshape(-1, 1) * rep_node
        m = np.concatenate([nodes.reshape(-1, 1), rep_nodes], axis=1)

        mapping = np.concatenate([mapping, m], axis=0)

    u_nodes = np.unique(edges)
    u_unmapped_nodes = u_nodes[~np.in1d(u_nodes, mapping)]

    unmapped_mapping = np.concatenate([u_unmapped_nodes.reshape(-1, 1),
                                       u_unmapped_nodes.reshape(-1, 1)], axis=1)
    mapping = np.concatenate([mapping, unmapped_mapping], axis=0)

    sort_idx = np.argsort(mapping[:, 0])
    idx = np.searchsorted(mapping[:, 0], edges, sorter=sort_idx)
    remapped_edges = np.asarray(mapping[:, 1])[sort_idx][idx]

    remapped_edges = remapped_edges[~cross_chunk_edge_mask]
    remapped_affs = affs[~cross_chunk_edge_mask]

    return remapped_edges, remapped_affs, mapping, remapping


def mincut_nx(edges: Iterable[Sequence[np.uint64]], affs: Sequence[np.uint64],
              sources: Sequence[np.uint64], sinks: Sequence[np.uint64],
              logger: Optional[logging.Logger] = None) -> np.ndarray:
    """ Computes the min cut on a local graph
    :param edges: n x 2 array of uint64s
    :param affs: float array of length n
    :param sources: uint64
    :param sinks: uint64
    :return: m x 2 array of uint64s
        edges that should be removed
    """

    time_start = time.time()

    original_edges = edges.copy()

    edges, affs, mapping, remapping = merge_cross_chunk_edges(edges.copy(),
                                                              affs.copy())

    if len(edges) == 0:
        return []

    assert np.unique(mapping[:, 0], return_counts=True)[1].max() == 1

    mapping_dict = dict(mapping)

    remapped_sinks = []
    remapped_sources = []

    for sink in sinks:
        remapped_sinks.append(mapping_dict[sink])

    for source in sources:
        remapped_sources.append(mapping_dict[source])

    sinks = remapped_sinks
    sources = remapped_sources

    sink_connections = np.array(list(itertools.product(sinks, sinks)))
    source_connections = np.array(list(itertools.product(sources, sources)))

    weighted_graph = nx.Graph()
    weighted_graph.add_edges_from(edges)
    weighted_graph.add_edges_from(sink_connections)
    weighted_graph.add_edges_from(source_connections)

    for i_edge, edge in enumerate(edges):
        weighted_graph[edge[0]][edge[1]]['capacity'] = affs[i_edge]
        weighted_graph[edge[1]][edge[0]]['capacity'] = affs[i_edge]

    # Add infinity edges for multicut
    for sink_i in sinks:
        for sink_j in sinks:
            weighted_graph[sink_i][sink_j]['capacity'] = float_max

    for source_i in sources:
        for source_j in sources:
            weighted_graph[source_i][source_j]['capacity'] = float_max


    dt = time.time() - time_start
    if logger is not None:
        logger.debug("Graph creation: %.2fms" % (dt * 1000))
    time_start = time.time()

    ccs = list(nx.connected_components(weighted_graph))
    for cc in ccs:
        cc_list = list(cc)

        # If connected component contains no sources and/or no sinks,
        # remove its nodes from the mincut computation
        if not np.any(np.in1d(sources, cc_list)) or \
                not np.any(np.in1d(sinks, cc_list)):
            weighted_graph.remove_nodes_from(cc)

    r_flow = edmonds_karp(weighted_graph, sinks[0], sources[0])
    cutset = minimum_st_edge_cut(weighted_graph, sources[0], sinks[0],
                                 residual=r_flow)

    # cutset = nx.minimum_edge_cut(weighted_graph, sources[0], sinks[0], flow_func=edmonds_karp)

    dt = time.time() - time_start
    if logger is not None:
        logger.debug("Mincut comp: %.2fms" % (dt * 1000))

    if cutset is None:
        return []

    time_start = time.time()

    edge_cut = list(list(cutset))

    weighted_graph.remove_edges_from(edge_cut)
    ccs = list(nx.connected_components(weighted_graph))

    # assert len(ccs) == 2

    for cc in ccs:
        cc_list = list(cc)
        if logger is not None:
            logger.debug("CC size = %d" % len(cc_list))

        if np.any(np.in1d(sources, cc_list)):
            assert np.all(np.in1d(sources, cc_list))
            assert ~np.any(np.in1d(sinks, cc_list))

        if np.any(np.in1d(sinks, cc_list)):
            assert np.all(np.in1d(sinks, cc_list))
            assert ~np.any(np.in1d(sources, cc_list))

    dt = time.time() - time_start
    if logger is not None:
        logger.debug("Splitting local graph: %.2fms" % (dt * 1000))

    remapped_cutset = []
    for cut in cutset:
        if cut[0] in remapping:
            pre_cut = remapping[cut[0]]
        else:
            pre_cut = [cut[0]]

        if cut[1] in remapping:
            post_cut = remapping[cut[1]]
        else:
            post_cut = [cut[1]]

        remapped_cutset.extend(list(itertools.product(pre_cut, post_cut)))
        remapped_cutset.extend(list(itertools.product(post_cut, pre_cut)))

    remapped_cutset = np.array(remapped_cutset, dtype=np.uint64)

    remapped_cutset_flattened_view = remapped_cutset.view(dtype='u8,u8')
    edges_flattened_view = original_edges.view(dtype='u8,u8')

    cutset_mask = np.in1d(remapped_cutset_flattened_view, edges_flattened_view)

    return remapped_cutset[cutset_mask]


def mincut_igraph(edges: Iterable[Sequence[np.uint64]],
                  affs: Sequence[np.uint64],
                  sources: Sequence[np.uint64],
                  sinks: Sequence[np.uint64],
                  logger: Optional[logging.Logger] = None) -> np.ndarray:
    """ Computes the min cut on a local graph
    :param edges: n x 2 array of uint64s
    :param affs: float array of length n
    :param sources: uint64
    :param sinks: uint64
    :return: m x 2 array of uint64s
        edges that should be removed
    """

    time_start = time.time()

    original_edges = edges.copy()

    # Stitch supervoxels across chunk boundaries and represent those that are
    # connected with a cross chunk edge with a single id. This may cause id
    # changes among sinks and sources that need to be taken care of.

    edges, affs, mapping, remapping = merge_cross_chunk_edges(edges.copy(),
                                                              affs.copy())

    if len(edges) == 0:
        return []

    assert np.unique(mapping[:, 0], return_counts=True)[1].max() == 1

    mapping_dict = dict(mapping)

    remapped_sinks = []
    remapped_sources = []

    for sink in sinks:
        remapped_sinks.append(mapping_dict[sink])

    for source in sources:
        remapped_sources.append(mapping_dict[source])

    sinks = remapped_sinks
    sources = remapped_sources

    # Assemble edges: Edges after remapping combined with edges between sinks
    # and sources
    sink_edges = list(itertools.product(sinks, sinks))
    source_edges = list(itertools.product(sources, sources))
    comb_edges = np.array(edges.tolist() + sink_edges + source_edges)
    comb_affs = affs.tolist() + [float_max,] * (len(sink_edges) + len(source_edges))

    # igraph is nasty when it comes to vertex naming. To make things easier
    # for everyone involved, we map the ids to [0, ..., len(unique_ids) - 1]
    # range

    unique_ids, comb_edges = np.unique(comb_edges[:, :2].astype(np.int),
                                       return_inverse=True)
    comb_edges = comb_edges.reshape(-1, 2)
    sink_graph_ids = np.where(np.in1d(unique_ids, sinks))[0]
    source_graph_ids = np.where(np.in1d(unique_ids, sources))[0]

    # Generate weighted graph with igraph

    weighted_graph = igraph.Graph(comb_edges.tolist(), directed=False)
    weighted_graph.es["weight"] = comb_affs

    dt = time.time() - time_start
    if logger is not None:
        logger.debug("Graph creation: %.2fms" % (dt * 1000))
    time_start = time.time()


    # Get rid of connected components that are not involved in the local
    # mincut
    ccs = list(weighted_graph.components())
    for cc in ccs:
        cc_list = list(cc)

        # If connected component contains no sources and/or no sinks,
        # remove its nodes from the mincut computation
        if not np.any(np.in1d(source_graph_ids, cc_list)) or \
                not np.any(np.in1d(sink_graph_ids, cc_list)):
            weighted_graph.delete_vertices(cc)

    # Compute mincut
    logger.debug("MAXFLOW")
    flow = weighted_graph.maxflow(sink_graph_ids[0],
                                      source_graph_ids[0],
                                      capacity="weight")
    weighted_graph.es["flow"] = flow
    mincut = weighted_graph.mincut(sink_graph_ids[0],
                                  source_graph_ids[0],
                                  capacity="flow")

    cut_edge_set = mincut.cut
    ccs = list(mincut)

    dt = time.time() - time_start
    if logger is not None:
        logger.debug("Mincut comp: %.2fms" % (dt * 1000))

    if len(cut_edge_set) == 0:
        return []

    time_start = time.time()

    # Make sure we did not do something wrong: Check if sinks and sources are
    # among each other and not together across sets

    for cc in ccs:
        # Make sure to read real ids and not igraph ids

        cc_list = unique_ids[np.array(list(cc), dtype=np.int)]

        if logger is not None:
            logger.debug("CC size = %d" % len(cc_list))

        if np.any(np.in1d(sources, cc_list)):
            assert np.all(np.in1d(sources, cc_list))
            assert ~np.any(np.in1d(sinks, cc_list))

        if np.any(np.in1d(sinks, cc_list)):
            assert np.all(np.in1d(sinks, cc_list))
            assert ~np.any(np.in1d(sources, cc_list))

    dt = time.time() - time_start
    if logger is not None:
        logger.debug("Verifying local graph: %.2fms" % (dt * 1000))

    # Extract original ids

    remapped_cutset = []
    for edge in weighted_graph.es[cut_edge_set]:
        s = unique_ids[edge.source]
        t = unique_ids[edge.target]

        if s in remapping:
            s = remapping[s]

        if t in remapping:
            t = remapping[t]

        remapped_cutset.extend([[s, t], [t, s]])

    remapped_cutset = np.array(remapped_cutset, dtype=np.uint64)

    remapped_cutset_flattened_view = remapped_cutset.view(dtype='u8,u8')
    edges_flattened_view = original_edges.view(dtype='u8,u8')

    cutset_mask = np.in1d(remapped_cutset_flattened_view, edges_flattened_view)

    return remapped_cutset[cutset_mask]


def mincut_graph_tool(edges: Iterable[Sequence[np.uint64]],
                  affs: Sequence[np.uint64],
                  sources: Sequence[np.uint64],
                  sinks: Sequence[np.uint64],
                  logger: Optional[logging.Logger] = None) -> np.ndarray:
    """ Computes the min cut on a local graph
    :param edges: n x 2 array of uint64s
    :param affs: float array of length n
    :param sources: uint64
    :param sinks: uint64
    :return: m x 2 array of uint64s
        edges that should be removed
    """

    time_start = time.time()

    original_edges = edges.copy()

    # Stitch supervoxels across chunk boundaries and represent those that are
    # connected with a cross chunk edge with a single id. This may cause id
    # changes among sinks and sources that need to be taken care of.

    edges, affs, mapping, remapping = merge_cross_chunk_edges(edges.copy(),
                                                              affs.copy())

    if len(edges) == 0:
        return []

    assert np.unique(mapping[:, 0], return_counts=True)[1].max() == 1

    mapping_dict = dict(mapping)

    remapped_sinks = []
    remapped_sources = []

    for sink in sinks:
        remapped_sinks.append(mapping_dict[sink])

    for source in sources:
        remapped_sources.append(mapping_dict[source])

    sinks = remapped_sinks
    sources = remapped_sources

    # Assemble edges: Edges after remapping combined with edges between sinks
    # and sources
    sink_edges = list(itertools.product(sinks, sinks))
    source_edges = list(itertools.product(sources, sources))
    comb_edges = np.array(edges.tolist() + sink_edges + source_edges, dtype=np.uint64)
    comb_affs = affs.tolist() + [float_max,] * (len(sink_edges) + len(source_edges))

    # To make things easier
    # for everyone involved, we map the ids to [0, ..., len(unique_ids) - 1]
    # range

    unique_ids, comb_edges = np.unique(comb_edges[:, :2].astype(np.int),
                                       return_inverse=True)
    unique_ids = unique_ids.astype(np.uint64)
    comb_edges = comb_edges.reshape(-1, 2)
    sink_graph_ids = np.where(np.in1d(unique_ids, sinks))[0]
    source_graph_ids = np.where(np.in1d(unique_ids, sources))[0]

    logger.debug(f"{sinks}, {sink_graph_ids}")
    logger.debug(f"{sources}, {source_graph_ids}")


    # Generate weighted graph with graph_tool

    weighted_graph = graph_tool.all.Graph(directed=True)
    weighted_graph.add_edge_list(edge_list=comb_edges, hashed=False)
    cap = weighted_graph.new_edge_property("float", vals=comb_affs)

    dt = time.time() - time_start
    if logger is not None:
        logger.debug("Graph creation: %.2fms" % (dt * 1000))
    time_start = time.time()


    # # Get rid of connected components that are not involved in the local
    # # mincut
    # cc_prop, ns = graph_tool.topology.label_components(weighted_graph)
    #
    # if len(ns):
    #     cc_labels = cc_prop.get_array()
    #
    #     for i_cc in range(len(ns)):
    #         cc_list = np.where(cc_labels == i_cc)[0]
    #
    #         # If connected component contains no sources and/or no sinks,
    #         # remove its nodes from the mincut computation
    #         if not np.any(np.in1d(source_graph_ids, cc_list)) or \
    #                 not np.any(np.in1d(sink_graph_ids, cc_list)):
    #             weighted_graph.delete_vertices(cc)

    # Compute mincut
    logger.debug("MAXFLOW")

    src, tgt = weighted_graph.vertex(source_graph_ids[0]), \
               weighted_graph.vertex(sink_graph_ids[0])

    res = graph_tool.flow.boykov_kolmogorov_max_flow(weighted_graph,
                                                     src, tgt, cap)

    part = graph_tool.all.min_st_cut(weighted_graph, src, cap, res)
    cut_edge_set = [e for e in weighted_graph.edges()
                    if part[e.source()] != part[e.target()]]

    cc_labels = part.get_array()

    dt = time.time() - time_start
    if logger is not None:
        logger.debug("Mincut comp: %.2fms" % (dt * 1000))

    if len(cut_edge_set) == 0:
        return []

    time_start = time.time()

    # Make sure we did not do something wrong: Check if sinks and sources are
    # among each other and not together across sets
    # cc_prop, ns = graph_tool.topology.label_components(weighted_graph)
    # cc_labels = cc_prop.get_array()

    for i_cc in range(2):
        # Make sure to read real ids and not graph ids

        cc_list = unique_ids[np.array(np.where(cc_labels == i_cc)[0],
                                      dtype=np.int)]

        if logger is not None:
            logger.debug("CC size = %d" % len(cc_list))

        if np.any(np.in1d(sources, cc_list)):
            assert np.all(np.in1d(sources, cc_list))
            assert ~np.any(np.in1d(sinks, cc_list))

        if np.any(np.in1d(sinks, cc_list)):
            assert np.all(np.in1d(sinks, cc_list))
            assert ~np.any(np.in1d(sources, cc_list))

    dt = time.time() - time_start
    if logger is not None:
        logger.debug("Verifying local graph: %.2fms" % (dt * 1000))

    # Extract original ids

    remapped_cutset = []
    for edge in cut_edge_set:
        s = unique_ids[int(edge.source())]
        t = unique_ids[int(edge.target())]

        if s in remapping:
            s = remapping[s]
        else:
            s = [s]

        if t in remapping:
            t = remapping[t]
        else:
            t = [t]

        remapped_cutset.extend(list(itertools.product(s, t)))
        remapped_cutset.extend(list(itertools.product(s, t)))

    remapped_cutset = np.array(remapped_cutset, dtype=np.uint64)

    remapped_cutset_flattened_view = remapped_cutset.view(dtype='u8,u8')
    edges_flattened_view = original_edges.view(dtype='u8,u8')

    cutset_mask = np.in1d(remapped_cutset_flattened_view, edges_flattened_view)

    return remapped_cutset[cutset_mask]
