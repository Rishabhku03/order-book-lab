#pragma once
#include <array>
#include <cstdint>
#include <optional>
#include <string>
#include <vector>

namespace lob {
using U64 = std::uint64_t;
using Price = std::int64_t;
enum class Side { bid, ask };
enum class Kind { add, cancel, erase, execute, replace };
struct Event {
    U64 sequence{}, timestamp_ns{};
    Kind type{Kind::add};
    U64 order_id{};
    std::optional<Side> side;
    std::optional<Price> price_ticks;
    std::optional<U64> quantity, new_order_id;
};
struct Order {
    Side side{};
    Price price{};
    U64 quantity{};
    bool operator==(const Order &) const = default;
};
struct Quote {
    Price price{};
    U64 quantity{}, orders{};
    bool operator==(const Quote &) const = default;
};
struct Level {
    U64 quantity{}, orders{};
    bool operator==(const Level &) const = default;
};
struct BookSnapshot {
    std::vector<Quote> bids, asks;
};
struct BookStatistics {
    U64 active_orders{}, total_quantity{}, peak_live_orders{}, execution_volume{}, execution_notional{};
    U64 sequence{}, timestamp_ns{}, bid_levels{}, ask_levels{};
    std::array<U64, 5> event_counts{};
    bool operator==(const BookStatistics &) const = default;
};
struct ApplyResult {
    std::string error;
    explicit operator bool() const { return error.empty(); }
};
struct Analytics {
    std::string status;
    std::optional<double> spread, midpoint, imbalance, imbalance5, weighted_midpoint, vwap;
};
inline const char *name(Kind k) {
    constexpr std::array names{"ADD", "CANCEL", "DELETE", "EXECUTE", "REPLACE"};
    auto i = static_cast<std::size_t>(k);
    return i < names.size() ? names[i] : "INVALID";
}
} // namespace lob
