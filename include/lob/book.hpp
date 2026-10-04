#pragma once
#include "lob/types.hpp"
#include <algorithm>
#include <limits>
#include <map>
#include <unordered_map>

namespace lob {
using TreeIndex = std::map<U64, Order>;
using HashIndex = std::unordered_map<U64, Order>;
template <class Index> class Book {
    friend struct BookTestAccess;
    Index orders_;
    std::map<Price, Level, std::greater<Price>> bids_;
    std::map<Price, Level> asks_;
    BookStatistics stats_;
    bool started_ = false;
    static constexpr U64 max = std::numeric_limits<U64>::max();

    void add_level(const Order &o) {
        auto add = [&](auto &levels) {
            auto &l = levels[o.price];
            l.quantity += o.quantity;
            ++l.orders;
        };
        if (o.side == Side::bid)
            add(bids_);
        else
            add(asks_);
    }
    void reduce_level(const Order &o, U64 qty, bool remove) {
        auto reduce = [&](auto &levels) {
            auto it = levels.find(o.price);
            it->second.quantity -= qty;
            if (remove)
                --it->second.orders;
            if (it->second.orders == 0)
                levels.erase(it);
        };
        if (o.side == Side::bid)
            reduce(bids_);
        else
            reduce(asks_);
    }

  public:
    explicit Book(std::size_t capacity = 0) {
        if constexpr (requires { orders_.reserve(capacity); }) {
            orders_.max_load_factor(1.0F);
            if (capacity)
                orders_.reserve(capacity);
        }
    }
    ApplyResult apply(const Event &e) {
        const auto ki = static_cast<std::size_t>(e.type);
        if (ki >= 5)
            return {"invalid event type"};
        if (started_ && e.sequence <= stats_.sequence)
            return {"sequence must increase"};
        if (started_ && e.timestamp_ns < stats_.timestamp_ns)
            return {"timestamp decreased"};
        const bool add = e.type == Kind::add, replace = e.type == Kind::replace;
        const bool reduction = e.type == Kind::cancel || e.type == Kind::execute;
        if (add) {
            if (!e.side || (*e.side != Side::bid && *e.side != Side::ask) || !e.price_ticks ||
                *e.price_ticks <= 0 || !e.quantity || !*e.quantity || e.new_order_id)
                return {"invalid ADD fields"};
        } else if (replace) {
            if (e.side || !e.price_ticks || *e.price_ticks <= 0 || !e.quantity || !*e.quantity ||
                !e.new_order_id || *e.new_order_id == e.order_id)
                return {"invalid REPLACE fields"};
        } else if (reduction) {
            if (e.side || e.price_ticks || e.new_order_id || !e.quantity || !*e.quantity)
                return {"invalid reduction fields"};
        } else if (e.side || e.price_ticks || e.quantity || e.new_order_id)
            return {"invalid DELETE fields"};
        auto it = orders_.find(e.order_id);
        if (add && it != orders_.end())
            return {"duplicate active order ID"};
        if (!add && it == orders_.end())
            return {"unknown order ID"};
        if (replace && orders_.contains(*e.new_order_id))
            return {"replacement ID is active"};
        if (reduction && *e.quantity > it->second.quantity)
            return {"reduction exceeds quantity"};
        if (stats_.event_counts[ki] == max)
            return {"event counter overflow"};
        const U64 removed = add ? 0 : (replace || e.type == Kind::erase ? it->second.quantity : *e.quantity);
        const U64 added = add || replace ? *e.quantity : 0;
        if (added > max - (stats_.total_quantity - removed))
            return {"book quantity overflow"};
        U64 notional = 0;
        if (e.type == Kind::execute) {
            const U64 price = static_cast<U64>(it->second.price);
            if (*e.quantity > max / price)
                return {"trade multiplication overflow"};
            notional = price * *e.quantity;
            if (notional > max - stats_.execution_notional || *e.quantity > max - stats_.execution_volume)
                return {"trade accumulator overflow"};
        }
        // All semantic validation precedes mutation. Allocation failure is fatal to the run.
        if (add) {
            Order order{*e.side, *e.price_ticks, *e.quantity};
            orders_.emplace(e.order_id, order);
            add_level(order);
        } else if (replace) {
            const Order old = it->second;
            Order next{old.side, *e.price_ticks, *e.quantity};
            orders_.erase(it);
            reduce_level(old, old.quantity, true);
            orders_.emplace(*e.new_order_id, next);
            add_level(next);
        } else {
            const Order old = it->second;
            const bool erase = removed == old.quantity;
            reduce_level(old, removed, erase);
            if (erase)
                orders_.erase(it);
            else
                it->second.quantity -= removed;
        }
        stats_.total_quantity = stats_.total_quantity - removed + added;
        stats_.execution_notional += notional;
        if (e.type == Kind::execute)
            stats_.execution_volume += *e.quantity;
        ++stats_.event_counts[ki];
        stats_.sequence = e.sequence;
        stats_.timestamp_ns = e.timestamp_ns;
        stats_.active_orders = static_cast<U64>(orders_.size());
        stats_.peak_live_orders = std::max(stats_.peak_live_orders, stats_.active_orders);
        stats_.bid_levels = static_cast<U64>(bids_.size());
        stats_.ask_levels = static_cast<U64>(asks_.size());
        started_ = true;
        return {};
    }
    std::optional<Quote> best_bid() const {
        if (bids_.empty())
            return {};
        const auto &[p, l] = *bids_.begin();
        return Quote{p, l.quantity, l.orders};
    }
    std::optional<Quote> best_ask() const {
        if (asks_.empty())
            return {};
        const auto &[p, l] = *asks_.begin();
        return Quote{p, l.quantity, l.orders};
    }
    BookSnapshot snapshot(std::size_t depth) const {
        BookSnapshot s;
        auto copy = [depth](const auto &levels, auto &out) {
            for (const auto &[p, l] : levels) {
                if (out.size() == depth)
                    break;
                out.push_back({p, l.quantity, l.orders});
            }
        };
        copy(bids_, s.bids);
        copy(asks_, s.asks);
        return s;
    }
    BookStatistics statistics() const { return stats_; }
    std::map<U64, Order> canonical_orders() const { return {orders_.begin(), orders_.end()}; }
    std::size_t buckets() const {
        if constexpr (requires { orders_.bucket_count(); })
            return orders_.bucket_count();
        else
            return 0;
    }
    void clear() {
        orders_.clear();
        bids_.clear();
        asks_.clear();
        stats_ = {};
        started_ = false;
    }
    bool invariants() const {
        std::map<Price, Level, std::greater<Price>> bids;
        std::map<Price, Level> asks;
        U64 qty = 0;
        for (const auto &[id, o] : orders_) {
            (void)id;
            if (!o.quantity || o.price <= 0 || o.quantity > max - qty)
                return false;
            qty += o.quantity;
            auto add = [&](auto &levels) {
                auto &l = levels[o.price];
                l.quantity += o.quantity;
                ++l.orders;
            };
            if (o.side == Side::bid)
                add(bids);
            else
                add(asks);
        }
        return bids == bids_ && asks == asks_ && qty == stats_.total_quantity &&
               orders_.size() == stats_.active_orders;
    }
};

template <class B> Analytics analyze(const B &b) {
    Analytics a;
    auto bid = b.best_bid(), ask = b.best_ask();
    auto s = b.statistics();
    a.status = !bid && !ask               ? "empty"
               : !bid || !ask             ? "one-sided"
               : bid->price < ask->price  ? "normal"
               : bid->price == ask->price ? "locked"
                                          : "crossed";
    if (s.execution_volume)
        a.vwap = static_cast<double>(s.execution_notional) / static_cast<double>(s.execution_volume);
    if (bid && ask) {
        const double bp = static_cast<double>(bid->price), ap = static_cast<double>(ask->price);
        const double bq = static_cast<double>(bid->quantity), aq = static_cast<double>(ask->quantity);
        a.spread = static_cast<double>(ask->price - bid->price);
        a.midpoint = bp / 2 + ap / 2;
        a.imbalance = (bq - aq) / (bq + aq);
        a.weighted_midpoint = ap * (bq / (bq + aq)) + bp * (aq / (bq + aq));
        auto top = b.snapshot(5);
        double bv = 0, av = 0;
        for (const auto &q : top.bids)
            bv += static_cast<double>(q.quantity);
        for (const auto &q : top.asks)
            av += static_cast<double>(q.quantity);
        a.imbalance5 = (bv - av) / (bv + av);
    }
    return a;
}
} // namespace lob
