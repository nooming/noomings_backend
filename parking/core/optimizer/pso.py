# -*- coding: utf-8 -*-
import math


def _imul(a, b):
    return (int(a) * int(b)) & 0xFFFFFFFF


def decode_particle(position, n_veh, n_slot):
    entries = [
        {
            "v": v,
            "i": i,
            "want": min(n_slot - 1, max(0, math.floor(v * n_slot))),
        }
        for i, v in enumerate(position)
    ]
    entries.sort(key=lambda e: e["v"])
    used = set()
    assign = [0] * n_veh
    for entry in entries:
        i = entry["i"]
        want = entry["want"]
        slot = want
        for delta in range(n_slot + 1):
            if want + delta not in used and want + delta < n_slot:
                slot = want + delta
                break
            if want - delta not in used and want - delta >= 0:
                slot = want - delta
                break
        assign[i] = slot
        used.add(slot)
    return assign


def make_rng(seed=None):
    if seed is None:
        import random
        return random.random
    t = int(seed) & 0xFFFFFFFF
    if t == 0:
        t = 1

    def random():
        nonlocal t
        t = (t + 0x6d2b79f5) & 0xFFFFFFFF
        z = t
        z = _imul(z ^ (z >> 15), z | 1) & 0xFFFFFFFF
        z = (z ^ ((z + _imul(z ^ (z >> 7), z | 61)) & 0xFFFFFFFF)) & 0xFFFFFFFF
        return ((z ^ (z >> 14)) & 0xFFFFFFFF) / 4294967296.0

    return random


def gaussian(rng):
    u1 = max(1e-12, rng())
    u2 = rng()
    return math.sqrt(-2 * math.log(u1)) * math.cos(2 * math.pi * u2)


def encode_assign_to_position(assign, n_slot):
    return [(slot_idx + 0.5) / n_slot for slot_idx in assign]
