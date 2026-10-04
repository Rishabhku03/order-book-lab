#include "lob/book.hpp"
#include "lob/parser.hpp"
#include <benchmark/benchmark.h>
using namespace lob;
static void parse(benchmark::State &state) {
    for (auto _ : state) {
        auto e = parse_line("1,100,ADD,42,B,10000,100,");
        benchmark::DoNotOptimize(e);
    }
    state.SetItemsProcessed(state.iterations());
}
template <class Index> static void lifecycle(benchmark::State &state) {
    Book<Index> b(static_cast<std::size_t>(state.range(0)));
    U64 seq = 0;
    for (auto _ : state) {
        auto a = b.apply({++seq, 0, Kind::add, 1, Side::bid, 10000, 100, {}});
        auto c = b.apply({++seq, 0, Kind::erase, 1, {}, {}, {}, {}});
        benchmark::DoNotOptimize(a);
        benchmark::DoNotOptimize(c);
        benchmark::ClobberMemory();
    }
    state.SetItemsProcessed(state.iterations() * 2);
}
BENCHMARK(parse);
BENCHMARK_TEMPLATE(lifecycle, TreeIndex)->Arg(0);
BENCHMARK_TEMPLATE(lifecycle, HashIndex)->Arg(0)->Arg(1000);
