#include "lob/book.hpp"
#include "lob/parser.hpp"
#include <catch2/catch_approx.hpp>
#include <catch2/catch_test_macros.hpp>
#include <sstream>
using namespace lob;
static Event event(const std::string &s) { return parse_line(s); }
namespace lob {
struct BookTestAccess {
    template <class I> static void counter(Book<I> &b, Kind kind, U64 value) {
        b.stats_.event_counts[static_cast<std::size_t>(kind)] = value;
    }
};
} // namespace lob

TEST_CASE("Full lifecycle and analytics agree across indexes") {
    for (int variant = 0; variant < 3; ++variant) {
        auto test = []<class Index>(std::size_t capacity) {
            Book<Index> b(capacity);
            REQUIRE(analyze(b).status == "empty");
            REQUIRE_FALSE(analyze(b).vwap);
            REQUIRE(b.apply(event("1,0,ADD,1,B,100,10,")));
            REQUIRE(analyze(b).status == "one-sided");
            REQUIRE_FALSE(analyze(b).midpoint);
            REQUIRE(b.apply(event("3,0,ADD,2,A,104,30,")));
            REQUIRE(b.apply(event("4,2,ADD,3,B,100,20,")));
            auto a = analyze(b);
            REQUIRE(*a.midpoint == 102);
            REQUIRE(*a.spread == 4);
            REQUIRE(*a.imbalance == 0);
            REQUIRE(*a.imbalance5 == 0);
            REQUIRE(*a.weighted_midpoint == 102);
            REQUIRE(b.apply(event("5,3,CANCEL,3,,,5,")));
            REQUIRE(b.apply(event("6,4,EXECUTE,1,,,4,")));
            REQUIRE(b.statistics().execution_notional == 400);
            REQUIRE(*analyze(b).vwap == 100);
            REQUIRE(b.apply(event("7,5,REPLACE,2,,99,7,4")));
            REQUIRE(analyze(b).status == "crossed");
            REQUIRE(b.apply(event("8,6,REPLACE,4,,100,7,2")));
            REQUIRE(analyze(b).status == "locked");
            REQUIRE(b.apply(event("9,7,DELETE,3,,,,")));
            REQUIRE(b.apply(event("10,8,EXECUTE,1,,,6,")));
            REQUIRE(b.apply(event("11,9,CANCEL,2,,,7,")));
            REQUIRE(b.invariants());
            REQUIRE(b.snapshot(0).bids.empty());
            REQUIRE(b.statistics().active_orders == 0);
            REQUIRE(b.statistics().total_quantity == 0);
            REQUIRE(b.apply(event("12,10,ADD,1,B,100,1,")));
            b.clear();
            REQUIRE(b.statistics() == BookStatistics{});
            REQUIRE(b.invariants());
            REQUIRE(b.apply(event("0,0,ADD,1,A,10,1,")));
        };
        if (variant == 0)
            test.template operator()<TreeIndex>(0);
        else
            test.template operator()<HashIndex>(variant == 2 ? 200 : 0);
    }
}
TEST_CASE("Every semantic error preserves complete state") {
    auto check = []<class Index>(std::size_t capacity) {
        Book<Index> b(capacity);
        REQUIRE(b.apply(event("10,10,ADD,1,B,100,10,")));
        REQUIRE(b.apply(event("11,10,ADD,2,A,101,10,")));
        const std::vector<std::string> invalid = {
            "11,10,DELETE,1,,,,",         "12,9,DELETE,1,,,,",         "12,10,ADD,1,B,10,1,",
            "12,10,ADD,3,,10,1,",         "12,10,ADD,3,B,0,1,",        "12,10,ADD,3,B,1,0,",
            "12,10,ADD,3,B,1,1,4",        "12,10,DELETE,99,,,,",       "12,10,DELETE,1,,,1,",
            "12,10,CANCEL,1,,,11,",       "12,10,EXECUTE,1,,,0,",      "12,10,CANCEL,1,B,,1,",
            "12,10,REPLACE,1,,100,10,2",  "12,10,REPLACE,1,,100,10,1", "12,10,REPLACE,1,,100,0,3",
            "12,10,REPLACE,1,B,100,10,3", "12,10,REPLACE,99,,100,1,3", "12,10,REPLACE,1,,100,10,",
            "12,10,CANCEL,1,,100,1,",     "12,10,EXECUTE,1,,,1,2",     "12,10,REPLACE,1,,0,10,3",
            "12,10,CANCEL,1,,,,",         "12,10,EXECUTE,99,,,1,",     "12,10,DELETE,1,B,,,",
            "12,10,ADD,3,B,,1,",          "12,10,REPLACE,1,,,10,3"};
        const auto stats = b.statistics();
        const auto orders = b.canonical_orders();
        for (const auto &s : invalid) {
            INFO(s);
            REQUIRE_FALSE(b.apply(event(s)));
            REQUIRE(b.statistics() == stats);
            REQUIRE(b.canonical_orders() == orders);
            REQUIRE(b.invariants());
        }
        Event bad{12, 10, static_cast<Kind>(99), 1, {}, {}, {}, {}};
        REQUIRE_FALSE(b.apply(bad));
        bad = event("12,10,ADD,3,B,100,1,");
        bad.side = static_cast<Side>(9);
        REQUIRE_FALSE(b.apply(bad));
        REQUIRE(b.apply(event("12,10,DELETE,1,,,,")));
    };
    check.template operator()<TreeIndex>(0);
    check.template operator()<HashIndex>(0);
    check.template operator()<HashIndex>(100);
}
TEST_CASE("Overflow rejects updates without changing orders or trades") {
    auto check = []<class Index>(std::size_t capacity) {
        Book<Index> b(capacity);
        const auto max = std::numeric_limits<U64>::max();
        REQUIRE(b.apply({0, 0, Kind::add, 1, Side::bid, 1, max, {}}));
        auto s = b.statistics();
        REQUIRE_FALSE(b.apply({1, 0, Kind::add, 2, Side::ask, 2, 1, {}}));
        REQUIRE(b.statistics() == s);
        REQUIRE(b.apply({1, 0, Kind::execute, 1, {}, {}, max, {}}));
        REQUIRE(b.apply({2, 0, Kind::add, 2, Side::ask, 1, 1, {}}));
        s = b.statistics();
        REQUIRE_FALSE(b.apply({3, 0, Kind::execute, 2, {}, {}, 1, {}}));
        REQUIRE(b.statistics() == s);
        b.clear();
        REQUIRE(b.apply({0, 0, Kind::add, 1, Side::bid, std::numeric_limits<Price>::max(), 3, {}}));
        s = b.statistics();
        REQUIRE_FALSE(b.apply({1, 0, Kind::execute, 1, {}, {}, 3, {}}));
        REQUIRE(b.statistics() == s);
        REQUIRE(b.invariants());
    };
    check.template operator()<TreeIndex>(0);
    check.template operator()<HashIndex>(0);
    check.template operator()<HashIndex>(100);
}
TEST_CASE("Level ordering and weighted formulas") {
    Book<TreeIndex> b;
    for (U64 i = 1; i <= 8; ++i) {
        REQUIRE(b.apply({i, i, Kind::add, i, Side::bid, static_cast<Price>(90 + i), i, {}}));
    }
    REQUIRE(b.apply({9, 9, Kind::add, 9, Side::ask, 100, 10, {}}));
    REQUIRE(b.snapshot(5).bids.size() == 5);
    REQUIRE(b.best_bid()->price == 98);
    REQUIRE(*analyze(b).imbalance5 == Catch::Approx(0.5));
    REQUIRE(*analyze(b).weighted_midpoint == Catch::Approx((100.0 * 8 + 98.0 * 10) / 18));
    REQUIRE(b.apply({10, 10, Kind::erase, 8, {}, {}, {}, {}}));
    REQUIRE(b.best_bid()->price == 97);
    REQUIRE(b.apply({11, 11, Kind::replace, 7, {}, 91, 4, 17}));
    REQUIRE(b.invariants());
}
TEST_CASE("Counter overflow, replacement overflow and multi-price VWAP") {
    auto check = []<class Index>(std::size_t capacity) {
        Book<Index> b(capacity);
        REQUIRE(b.apply(event("1,0,ADD,1,B,100,3,")));
        REQUIRE(b.apply(event("2,0,ADD,2,A,110,7,")));
        REQUIRE(b.apply(event("3,1,EXECUTE,1,,,2,")));
        REQUIRE(b.apply(event("4,1,EXECUTE,2,,,3,")));
        REQUIRE(*analyze(b).vwap == Catch::Approx(106));
        BookTestAccess::counter(b, Kind::erase, std::numeric_limits<U64>::max());
        auto before = b.statistics();
        auto orders = b.canonical_orders();
        REQUIRE_FALSE(b.apply(event("5,1,DELETE,1,,,,")));
        REQUIRE(b.statistics() == before);
        REQUIRE(b.canonical_orders() == orders);
        REQUIRE_FALSE(b.apply({5, 1, Kind::replace, 1, {}, 100, std::numeric_limits<U64>::max(), 3}));
        REQUIRE(b.statistics() == before);
        REQUIRE(b.canonical_orders() == orders);
        REQUIRE(b.invariants());
    };
    check.template operator()<TreeIndex>(0);
    check.template operator()<HashIndex>(0);
    check.template operator()<HashIndex>(100);
}
TEST_CASE("Parser rejects malformed input and accepts CRLF") {
    for (auto s : {"", "1,2,ADD,1,B,10,1", "1,2,ADD,1,B,10,1,,", "x,2,ADD,1,B,10,1,", "-1,2,ADD,1,B,10,1,",
                   "1,2,BOGUS,1,B,10,1,", "1,2,ADD,1,X,10,1,", "1,2,ADD,1,B,9223372036854775808,1,",
                   "18446744073709551616,2,ADD,1,B,10,1,", "1,2,ADD,1,B,10,1x,", "1,2,ADD,1,B,10,1, 2"})
        REQUIRE_THROWS(parse_line(s));
    REQUIRE_THROWS(parse_line(std::string(4097, 'a')));
    REQUIRE(parse_line("1,2,ADD,1,B,10,1,\r").sequence == 1);
    for (auto s :
         {"", "bad\n", "sequence,timestamp_ns,type,order_id,side,price_ticks,quantity,new_order_id\n\n"}) {
        std::istringstream in(s);
        REQUIRE_THROWS(read_events(in, [](const auto &) {}));
    }
    std::istringstream good(std::string(csv_header) + "\r\n1,2,ADD,1,B,10,1,\r\n");
    int n = 0;
    read_events(good, [&](const auto &) { ++n; });
    REQUIRE(n == 1);
    std::istringstream last(std::string(csv_header) + "\n1,2,ADD,1,B,10,1,");
    read_events(last, [](const auto &) {});
    std::istringstream longline(std::string(csv_header) + "\n" + std::string(5000, 'x'));
    REQUIRE_THROWS(read_events(longline, [](const auto &) {}));
}
