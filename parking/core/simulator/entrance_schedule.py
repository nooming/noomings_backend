# -*- coding: utf-8 -*-
"""在已知到达时刻下，按各入口通行能力计算驶入开始/结束时刻。"""
import heapq


def schedule_drive_times(
    arrivals,
    drive_durations,
    entrance_capacity=1,
    entrance_indices=None,
):
    """
    arrivals[i], drive_durations[i] 对应同一车辆。
    entrance_indices[i] 为该车使用的入口编号（0-based）。

    entrance_capacity：每个入口同时允许驶入的最大车辆数（默认 1）。
    各入口独立排队；多入口可并行，同一入口串行。

    返回 (drive_starts, drive_ends)，长度 n。
    """
    n = len(arrivals)
    if not n:
        return [], []
    cap = max(1, int(entrance_capacity or 1))
    if entrance_indices is None:
        entrance_indices = [0] * n
    n_ent = 1
    for i in range(n):
        try:
            n_ent = max(n_ent, int(entrance_indices[i]) + 1)
        except (TypeError, ValueError):
            pass
    heaps = [[] for _ in range(n_ent)]
    order = sorted(range(n), key=lambda i: (arrivals[i], i))
    drive_starts = [0.0] * n
    drive_ends = [0.0] * n

    for i in order:
        arr = float(arrivals[i])
        dur = max(0.0, float(drive_durations[i]))
        try:
            ei = int(entrance_indices[i])
        except (TypeError, ValueError):
            ei = 0
        ei = max(0, min(n_ent - 1, ei))
        heap = heaps[ei]
        while heap and heap[0] <= arr + 1e-9:
            heapq.heappop(heap)
        if len(heap) < cap:
            start = arr
        else:
            start = max(arr, heap[0])
            while heap and heap[0] <= start + 1e-9:
                heapq.heappop(heap)
        end = start + dur
        heapq.heappush(heap, end)
        drive_starts[i] = start
        drive_ends[i] = end
    return drive_starts, drive_ends
