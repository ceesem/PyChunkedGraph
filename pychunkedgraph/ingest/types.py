import numpy as np

from ..backend import ChunkedGraphMeta
from ..backend.chunks.hierarchy import get_children_coords


class ChunkTask:
    def __init__(self, cg_meta: ChunkedGraphMeta, coords: np.ndarray, layer: int = 2):
        self.cg_meta = cg_meta
        self.coords = coords
        self.layer = layer

    @staticmethod
    def task_id(layer: int, coords: np.ndarray):
        return f"{layer}_{'_'.join(map(str, coords))}"

    @property
    def id(self) -> str:
        return ChunkTask.task_id(self.layer, self.coords)

    def parent_task(self):
        parent_layer = self.layer + 1
        parent_coords = np.array(self.coords, int) // self.cg_meta.graph_config.fanout
        return ChunkTask(self.cg_meta, parent_coords, parent_layer)

    @property
    def children_coords(self):
        return get_children_coords(self.cg_meta, self.layer, self.coords)

