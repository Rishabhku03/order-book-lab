#pragma once
#include "lob/book.hpp"
#include <nlohmann/json.hpp>
namespace lob {
using Json = nlohmann::json;
inline Json optional(std::optional<double> v) { return v ? Json(*v) : Json(nullptr); }
inline Json event_json(const Event &e) {
    Json j = {{"sequence", std::to_string(e.sequence)},
              {"timestamp_ns", std::to_string(e.timestamp_ns)},
              {"type", name(e.type)},
              {"order_id", std::to_string(e.order_id)}};
    j["side"] = e.side ? Json(*e.side == Side::bid ? "B" : "A") : Json(nullptr);
    j["price_ticks"] = e.price_ticks ? Json(std::to_string(*e.price_ticks)) : Json(nullptr);
    j["quantity"] = e.quantity ? Json(std::to_string(*e.quantity)) : Json(nullptr);
    j["new_order_id"] = e.new_order_id ? Json(std::to_string(*e.new_order_id)) : Json(nullptr);
    return j;
}
template <class B> Json state_json(const B &b, std::size_t depth = 10, bool orders = false) {
    Json j;
    auto s = b.statistics();
    auto a = analyze(b);
    auto snap = b.snapshot(depth);
    j["bids"] = Json::array();
    j["asks"] = Json::array();
    auto append = [](auto &out, const auto &levels) {
        for (const auto &q : levels)
            out.push_back({{"price_ticks", std::to_string(q.price)},
                           {"quantity", std::to_string(q.quantity)},
                           {"orders", std::to_string(q.orders)}});
    };
    append(j["bids"], snap.bids);
    append(j["asks"], snap.asks);
    j["statistics"] = {{"active_orders", std::to_string(s.active_orders)},
                       {"total_quantity", std::to_string(s.total_quantity)},
                       {"peak_live_orders", std::to_string(s.peak_live_orders)},
                       {"execution_volume", std::to_string(s.execution_volume)},
                       {"execution_notional", std::to_string(s.execution_notional)},
                       {"sequence", std::to_string(s.sequence)},
                       {"timestamp_ns", std::to_string(s.timestamp_ns)},
                       {"bid_levels", std::to_string(s.bid_levels)},
                       {"ask_levels", std::to_string(s.ask_levels)},
                       {"event_counts", s.event_counts}};
    j["analytics"] = {{"status", a.status},
                      {"spread", optional(a.spread)},
                      {"midpoint", optional(a.midpoint)},
                      {"imbalance", optional(a.imbalance)},
                      {"imbalance5", optional(a.imbalance5)},
                      {"weighted_midpoint", optional(a.weighted_midpoint)},
                      {"vwap", optional(a.vwap)}};
    if (orders) {
        j["orders"] = Json::array();
        for (const auto &[id, o] : b.canonical_orders())
            j["orders"].push_back({{"id", std::to_string(id)},
                                   {"side", o.side == Side::bid ? "B" : "A"},
                                   {"price_ticks", std::to_string(o.price)},
                                   {"quantity", std::to_string(o.quantity)}});
    }
    return j;
}
} // namespace lob
