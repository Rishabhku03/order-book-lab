"""Independent checker: recomputes every level from active orders."""
import csv
from collections import defaultdict

class Reference:
    def __init__(self):
        self.orders = {}; self.counts = [0]*5; self.volume = self.notional = self.peak = 0
        self.sequence = self.timestamp = 0

    def apply(self, e):
        kind = e['type']; oid = int(e['order_id'])
        if kind == 'ADD':
            self.orders[oid] = (e['side'],int(e['price_ticks']),int(e['quantity']))
        elif kind == 'REPLACE':
            side = self.orders.pop(oid)[0]
            self.orders[int(e['new_order_id'])] = (side,int(e['price_ticks']),int(e['quantity']))
        elif kind == 'DELETE': del self.orders[oid]
        else:
            side, price, qty = self.orders[oid]; delta = int(e['quantity'])
            if kind == 'EXECUTE': self.volume += delta; self.notional += price*delta
            if qty == delta: del self.orders[oid]
            else: self.orders[oid] = (side,price,qty-delta)
        self.counts[['ADD','CANCEL','DELETE','EXECUTE','REPLACE'].index(kind)] += 1
        self.peak = max(self.peak,len(self.orders)); self.sequence=int(e['sequence']); self.timestamp=int(e['timestamp_ns'])

    def snapshot(self, depth=None):
        sides = {'B':defaultdict(lambda:[0,0]), 'A':defaultdict(lambda:[0,0])}
        for side,price,qty in self.orders.values():
            sides[side][price][0] += qty; sides[side][price][1] += 1
        bids = sorted(sides['B'].items(),reverse=True); asks = sorted(sides['A'].items())
        levels = lambda xs: [{'price_ticks':str(p),'quantity':str(q),'orders':str(n)} for p,(q,n) in xs[:depth]]
        analytics = dict.fromkeys(['spread','midpoint','imbalance','imbalance5','weighted_midpoint','vwap'])
        analytics['status'] = 'empty' if not bids and not asks else 'one-sided'
        if self.volume: analytics['vwap'] = self.notional/self.volume
        if bids and asks:
            bp,(bq,_) = bids[0]; ap,(aq,_) = asks[0]
            bv=sum(v[0] for _,v in bids[:5]); av=sum(v[0] for _,v in asks[:5])
            analytics.update(status='normal' if bp<ap else 'locked' if bp==ap else 'crossed',
                             spread=ap-bp,midpoint=(bp+ap)/2,imbalance=(bq-aq)/(bq+aq),
                             imbalance5=(bv-av)/(bv+av),weighted_midpoint=(ap*bq+bp*aq)/(bq+aq))
        statistics = {k:str(v) for k,v in dict(active_orders=len(self.orders),total_quantity=sum(o[2] for o in self.orders.values()),
                     peak_live_orders=self.peak,execution_volume=self.volume,execution_notional=self.notional,
                     sequence=self.sequence,timestamp_ns=self.timestamp,bid_levels=len(bids),ask_levels=len(asks)).items()}
        statistics['event_counts'] = self.counts.copy()
        return {'bids':levels(bids),'asks':levels(asks),'statistics':statistics,'analytics':analytics,
                'orders':[dict(id=str(oid),side=s,price_ticks=str(p),quantity=str(q)) for oid,(s,p,q) in sorted(self.orders.items())]}

def rows(path):
    with open(path,newline='') as f: yield from csv.DictReader(f)
