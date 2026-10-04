"""Versioned, deterministic synthetic order streams. No market-data claims."""
import argparse
import csv
import hashlib
import json
from collections import Counter
from pathlib import Path

HEADER = ['sequence', 'timestamp_ns', 'type', 'order_id', 'side', 'price_ticks', 'quantity', 'new_order_id']
PROFILES = {'balanced': [30, 25, 15, 20, 10], 'cancellation': [30, 40, 20, 5, 5], 'execution': [30, 10, 10, 40, 10]}
SIZES = {'small': (1000, 100), 'medium': (10000, 500), 'large': (100000, 2000)}
KINDS = ['ADD', 'CANCEL', 'DELETE', 'EXECUTE', 'REPLACE']
VERSION = 'splitmix64-v1'
MASK = (1 << 64) - 1

class RNG:
    def __init__(self, seed): self.state = seed & MASK
    def next(self):
        self.state = (self.state + 0x9E3779B97F4A7C15) & MASK
        z = self.state
        z = ((z ^ (z >> 30)) * 0xBF58476D1CE4E5B9) & MASK
        z = ((z ^ (z >> 27)) * 0x94D049BB133111EB) & MASK
        return z ^ (z >> 31)
    def pick(self, n): return self.next() % n

def sha(path):
    with open(path, 'rb') as f: return hashlib.file_digest(f, 'sha256').hexdigest()

def generate(path, profile='balanced', seed=42, events=2000, capacity=200, levels=20):
    path = Path(path)
    if path.exists(): raise FileExistsError(path)
    if capacity < 2 or capacity > 10000000 or levels < 1 or levels >= 100000 or events < 0: raise ValueError('invalid workload dimensions')
    path.parent.mkdir(parents=True, exist_ok=True)
    rng = RNG(seed)
    # Dense live IDs allow deterministic O(1) sampling and deletion.
    live, positions, state = [], {}, {}
    def insert(oid, order):
        positions[oid] = len(live); live.append(oid); state[oid] = order
    def remove(oid):
        at = positions.pop(oid); last = live.pop()
        if at < len(live): live[at] = last; positions[last] = at
        del state[oid]
    sequence = timestamp = next_id = 0
    counts, populations = Counter(), Counter()
    setup = capacity // 2
    weights = PROFILES[profile]
    with path.open('w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f, lineterminator='\n'); writer.writerow(HEADER)
        for i in range(setup + events):
            sequence += 1; timestamp += rng.pick(10000)
            draw = rng.pick(100); total = 0; kind = 'ADD'
            for k, weight in zip(KINDS, weights):
                total += weight
                if draw < total: kind = k; break
            if i < setup or len(live) < capacity // 2: kind = 'ADD'
            elif len(live) == capacity and kind == 'ADD': kind = 'DELETE'
            side = price = quantity = new_id = ''
            if kind == 'ADD':
                next_id += 1; oid = next_id; side = 'B' if rng.pick(2) == 0 else 'A'
                price = 100000 - 1 - rng.pick(levels) if side == 'B' else 100000 + 1 + rng.pick(levels)
                quantity = 1 + rng.pick(1000); insert(oid, [side, price, quantity])
            else:
                oid = live[rng.pick(len(live))]; old = state[oid]
                if kind == 'DELETE': remove(oid)
                elif kind == 'REPLACE':
                    next_id += 1; new_id = next_id
                    price = 100000 - 1 - rng.pick(levels) if old[0] == 'B' else 100000 + 1 + rng.pick(levels)
                    quantity = 1 + rng.pick(1000); replacement = [old[0], price, quantity]
                    remove(oid); insert(new_id, replacement)
                else:
                    quantity = old[2] if rng.pick(2) == 0 else 1 + rng.pick(old[2])
                    old[2] -= quantity
                    if not old[2]: remove(oid)
            writer.writerow([sequence, timestamp, kind, oid, side, price, quantity, new_id])
            if i >= setup: counts[kind] += 1; populations[len(live)] += 1
    manifest = {'schema_version': 1, 'synthetic': True, 'instrument': 'SYNTH', 'tick_size': 0.01,
                'generator_version': VERSION, 'seed': seed, 'profile': profile,
                'max_live_orders': capacity, 'price_levels_per_side': levels,
                'setup_events': setup, 'measured_events': events, 'total_events': setup + events,
                'requested_weights': dict(zip(KINDS, weights)), 'realized_counts': dict(counts),
                'realized_percentages': {kind:100*counts[kind]/events if events else 0 for kind in KINDS},
                'population': {'min': min(populations, default=0), 'max': max(populations, default=0),
                               'mean': sum(k*v for k,v in populations.items()) / events if events else 0,
                               'histogram': {str(k):v for k,v in sorted(populations.items())}},
                'sha256': sha(path)}
    path.with_suffix('.manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    return manifest

def write_fixture(path, rows):
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('w', newline='') as f:
        w = csv.writer(f, lineterminator='\n'); w.writerow(HEADER); w.writerows(rows)
    m = {'schema_version': 1, 'synthetic': True, 'instrument': 'SYNTH', 'tick_size': 0.01,
         'generator_version': 'hand-authored-v1', 'seed': 0, 'profile': 'fixture',
         'max_live_orders': max(len(rows), 2), 'setup_events': 0, 'measured_events': len(rows),
         'total_events': len(rows), 'sha256': sha(path)}
    path.with_suffix('.manifest.json').write_text(json.dumps(m, indent=2)+'\n')
    return m

if __name__ == '__main__':
    p = argparse.ArgumentParser(); p.add_argument('path'); p.add_argument('--events', type=int, default=2000)
    p.add_argument('--seed', type=int, default=42); p.add_argument('--profile', choices=PROFILES, default='balanced')
    p.add_argument('--size', choices=SIZES, default='small'); a=p.parse_args()
    generate(a.path,a.profile,a.seed,a.events,*SIZES[a.size])
