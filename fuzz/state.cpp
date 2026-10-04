#include "lob/book.hpp"
#include <cstdlib>
#include <vector>
extern "C" int LLVMFuzzerTestOneInput(const unsigned char *data, std::size_t size) {
    lob::Book<lob::TreeIndex> tree;
    lob::Book<lob::HashIndex> hash(64);
    lob::Book<lob::HashIndex> unreserved;
    std::vector<std::pair<lob::U64, lob::Order>> reference;
    lob::U64 volume = 0, notional = 0;
    for (std::size_t i = 0; i + 5 < size; i += 6) {
        lob::Event e{static_cast<lob::U64>(i),
                     0,
                     static_cast<lob::Kind>(data[i] % 5),
                     static_cast<lob::U64>(data[i + 1] % 64),
                     {},
                     {},
                     {},
                     {}};
        if (e.type == lob::Kind::add)
            e.side = data[i + 2] % 2 ? lob::Side::bid : lob::Side::ask;
        if (e.type == lob::Kind::add || e.type == lob::Kind::replace)
            e.price_ticks = 1 + data[i + 3];
        if (e.type != lob::Kind::erase)
            e.quantity = data[i + 4];
        if (e.type == lob::Kind::replace)
            e.new_order_id = data[i + 5] % 64;
        auto before = tree.canonical_orders();
        auto stats = tree.statistics();
        auto found = std::find_if(reference.begin(), reference.end(),
                                  [&](const auto &o) { return o.first == e.order_id; });
        bool valid = false;
        if (e.type == lob::Kind::add) {
            valid = found == reference.end() && *e.quantity > 0;
            if (valid)
                reference.push_back({e.order_id, {*e.side, *e.price_ticks, *e.quantity}});
        } else if (found != reference.end()) {
            if (e.type == lob::Kind::erase) {
                valid = true;
                reference.erase(found);
            } else if (e.type == lob::Kind::replace) {
                valid = *e.quantity > 0 &&
                        std::none_of(reference.begin(), reference.end(),
                                     [&](const auto &o) { return o.first == *e.new_order_id; });
                if (valid) {
                    auto side = found->second.side;
                    reference.erase(found);
                    reference.push_back({*e.new_order_id, {side, *e.price_ticks, *e.quantity}});
                }
            } else {
                valid = *e.quantity > 0 && *e.quantity <= found->second.quantity;
                if (valid) {
                    if (e.type == lob::Kind::execute) {
                        volume += *e.quantity;
                        notional += *e.quantity * static_cast<lob::U64>(found->second.price);
                    }
                    found->second.quantity -= *e.quantity;
                    if (!found->second.quantity)
                        reference.erase(found);
                }
            }
        }
        auto a = tree.apply(e), b = hash.apply(e);
        auto c = unreserved.apply(e);
        std::map<lob::U64, lob::Order> expected(reference.begin(), reference.end());
        if (static_cast<bool>(a) != valid || tree.canonical_orders() != expected ||
            tree.statistics().execution_volume != volume || tree.statistics().execution_notional != notional)
            std::abort();
        if (a.error != c.error || tree.canonical_orders() != unreserved.canonical_orders() ||
            tree.statistics() != unreserved.statistics() || !unreserved.invariants())
            std::abort();
        if (a.error != b.error || tree.canonical_orders() != hash.canonical_orders() ||
            tree.statistics() != hash.statistics() || !tree.invariants() || !hash.invariants())
            std::abort();
        if (!a && (tree.canonical_orders() != before || tree.statistics() != stats))
            std::abort();
    }
    return 0;
}
