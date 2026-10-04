#include "lob/output.hpp"
#include "lob/parser.hpp"
#include <chrono>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <picosha2.h>
#include <sstream>
#include <stdexcept>
#ifdef _WIN32
#define NOMINMAX
// clang-format off
#include <windows.h>
#include <psapi.h>
// clang-format on
#else
#include <sched.h>
#include <sys/resource.h>
#include <unistd.h>
#endif

using namespace lob;
namespace fs = std::filesystem;
using Clock = std::chrono::steady_clock;
using Args = std::map<std::string, std::string>;
static double seconds(Clock::time_point start) {
    return std::chrono::duration<double>(Clock::now() - start).count();
}
static std::string required(const Args &a, const std::string &key) {
    auto it = a.find(key);
    if (it == a.end())
        throw std::runtime_error("missing --" + key);
    return it->second;
}
static std::string arg(const Args &a, const std::string &key, std::string fallback) {
    auto it = a.find(key);
    return it == a.end() ? fallback : it->second;
}
static void write_json(const fs::path &path, const Json &j) {
    std::ofstream f(path);
    if (!f)
        throw std::runtime_error("cannot write " + path.filename().string());
    f << j.dump(2) << '\n';
    f.close();
    if (!f)
        throw std::runtime_error("output write failed");
}
static std::string hash_file(const fs::path &path) {
    std::ifstream f(path, std::ios::binary);
    if (!f)
        throw std::runtime_error("cannot read input " + path.string());
    picosha2::hash256_one_by_one h;
    std::array<char, 65536> buffer{};
    while (f) {
        f.read(buffer.data(), static_cast<std::streamsize>(buffer.size()));
        h.process(buffer.begin(), buffer.begin() + f.gcount());
    }
    if (!f.eof())
        throw std::runtime_error("input read error " + path.string());
    h.finish();
    return picosha2::get_hash_hex_string(h);
}
static std::string hash_text(const std::string &text) { return picosha2::hash256_hex_string(text); }
static Json memory() {
#ifdef _WIN32
    PROCESS_MEMORY_COUNTERS pm{};
    pm.cb = sizeof(pm);
    if (!GetProcessMemoryInfo(GetCurrentProcess(), &pm, sizeof(pm)))
        throw std::runtime_error("memory query failed");
    return {{"current_bytes", pm.WorkingSetSize},
            {"peak_bytes", pm.PeakWorkingSetSize},
            {"metric", "Windows working set"}};
#else
    rusage ru{};
    getrusage(RUSAGE_SELF, &ru);
    U64 size = 0, resident = 0;
    std::ifstream stat("/proc/self/statm");
    stat >> size >> resident;
    return {{"current_bytes", resident * static_cast<U64>(sysconf(_SC_PAGESIZE))},
            {"peak_bytes", static_cast<U64>(ru.ru_maxrss) * 1024},
            {"metric", "Linux RSS"}};
#endif
}
static void affinity(unsigned cpu) {
#ifdef _WIN32
    if (cpu >= sizeof(DWORD_PTR) * 8 ||
        !SetProcessAffinityMask(GetCurrentProcess(), static_cast<DWORD_PTR>(1) << cpu))
        throw std::runtime_error("could not set CPU affinity");
#else
    if (cpu >= CPU_SETSIZE)
        throw std::runtime_error("invalid CPU");
    cpu_set_t set;
    CPU_ZERO(&set);
    CPU_SET(cpu, &set);
    if (sched_setaffinity(0, sizeof(set), &set))
        throw std::runtime_error("could not set CPU affinity");
#endif
}
template <class B> static void apply_checked(B &b, const Event &e) {
    auto r = b.apply(e);
    if (!r)
        throw std::runtime_error("sequence " + std::to_string(e.sequence) + ": " + r.error);
}
static Json manifest(const Args &a) {
    std::ifstream f(required(a, "manifest"));
    if (!f)
        throw std::runtime_error("cannot read manifest " + required(a, "manifest"));
    Json m;
    f >> m;
    for (const auto &key : {"max_live_orders", "total_events", "setup_events"}) {
        if (!m.at(key).is_number_unsigned())
            throw std::runtime_error(std::string("manifest requires unsigned ") + key);
    }
    if (m.at("setup_events").get<U64>() > m.at("total_events").get<U64>())
        throw std::runtime_error("setup exceeds total events");
    if (!m.at("schema_version").is_number_unsigned() || m.at("schema_version").get<U64>() != 1 ||
        !m.at("synthetic").get<bool>() || m.at("instrument").get<std::string>().empty() ||
        !m.at("tick_size").is_number() || m.at("tick_size").get<double>() <= 0)
        throw std::runtime_error("invalid manifest");
    if (m.at("max_live_orders").get<U64>() == 0 || m.at("max_live_orders").get<U64>() > 10000000)
        throw std::runtime_error("capacity outside safety limit");
    if (hash_file(required(a, "input")) != m.at("sha256").get<std::string>())
        throw std::runtime_error("input SHA-256 mismatch");
    return m;
}
template <class B>
static Json run_replay(const std::string &command, const Args &args, const Json &m, std::size_t capacity) {
    B b(capacity);
    Json trace = Json::array(), checkpoints = Json::array();
    U64 count = 0;
    std::optional<std::pair<U64, U64>> inspected_ordering;
    const bool full = args.contains("full-state");
    const U64 trace_limit = integer<U64>(arg(args, "trace-limit", "10000"));
    const U64 stop = integer<U64>(arg(args, "sequence", std::to_string(std::numeric_limits<U64>::max())));
    const bool tracing = args.contains("trace");
    const U64 trace_from = integer<U64>(arg(args, "trace-from-ns", "0"));
    const U64 trace_to =
        integer<U64>(arg(args, "trace-to-ns", std::to_string(std::numeric_limits<U64>::max())));
    if (trace_from > trace_to)
        throw std::runtime_error("trace time range is reversed");
    if (trace_limit > 100000)
        throw std::runtime_error("trace limit exceeds 100000");
    std::ifstream f(required(args, "input"), std::ios::binary);
    if (!f)
        throw std::runtime_error("cannot read input");
    read_events(f, [&](const Event &e) {
        if (command == "inspect") {
            if (inspected_ordering && e.sequence <= inspected_ordering->first)
                throw std::runtime_error("sequence " + std::to_string(e.sequence) +
                                         ": sequence must increase");
            if (inspected_ordering && e.timestamp_ns < inspected_ordering->second)
                throw std::runtime_error("sequence " + std::to_string(e.sequence) + ": timestamp decreased");
            inspected_ordering = {e.sequence, e.timestamp_ns};
            if (e.sequence > stop)
                return;
        }
        apply_checked(b, e);
        ++count;
        if (command == "replay" && count % 1000000 == 0)
            std::cerr << "Replayed " << count << " events\n";
        if (command == "audit") {
            auto frame = state_json(b, std::numeric_limits<std::size_t>::max(), true);
            frame["event"] = event_json(e);
            std::cout << frame.dump() << '\n';
        }
        if (tracing && e.timestamp_ns >= trace_from && e.timestamp_ns <= trace_to) {
            if (trace.size() >= trace_limit)
                throw std::runtime_error("trace limit exceeded; use a smaller workload");
            auto frame = state_json(b, full ? std::numeric_limits<std::size_t>::max() : 10, full);
            frame["event"] = event_json(e);
            trace.push_back(std::move(frame));
        }
        if (args.contains("checkpoints") && count % 250000 == 0)
            checkpoints.push_back(
                {{"event_count", count},
                 {"sha256", hash_text(state_json(b, std::numeric_limits<std::size_t>::max(), true).dump())}});
    });
    if (command != "inspect" && count != m.at("total_events").get<U64>())
        throw std::runtime_error("event count differs from manifest");
    if (command == "inspect" && (!count || b.statistics().sequence != stop))
        throw std::runtime_error("requested sequence not found");
    if (!b.invariants())
        throw std::runtime_error("final invariant failure");
    Json result = {{"schema_version", 1},
                   {"synthetic", true},
                   {"complete", true},
                   {"event_count", count},
                   {"engine_commit", LOB_COMMIT},
                   {"variant", arg(args, "variant", "hash_reserved")},
                   {"input_sha256", m.at("sha256")},
                   {"summary", state_json(b, full ? std::numeric_limits<std::size_t>::max() : 10, full)}};
    if (args.contains("checkpoints")) {
        result["checkpoints"] = checkpoints;
        result["final_state_sha256"] =
            hash_text(state_json(b, std::numeric_limits<std::size_t>::max(), true).dump());
    }
    if (command == "inspect" || command == "validate" || command == "audit")
        return result;
    fs::path out = required(args, "output");
    if (fs::exists(out))
        throw std::runtime_error("output directory exists");
    fs::create_directories(out);
    write_json(out / "summary.json", result);
    Json output_manifest = m;
    output_manifest["engine_commit"] = LOB_COMMIT;
    output_manifest["variant"] = result["variant"];
    if (tracing) {
        output_manifest["trace_from_ns"] = std::to_string(trace_from);
        output_manifest["trace_to_ns"] = std::to_string(trace_to);
    }
    write_json(out / "manifest.json", output_manifest);
    if (tracing)
        write_json(out / "trace.json", {{"schema_version", 1},
                                        {"synthetic", true},
                                        {"engine_commit", LOB_COMMIT},
                                        {"instrument", m.at("instrument")},
                                        {"tick_size", m.at("tick_size")},
                                        {"input_sha256", m.at("sha256")},
                                        {"frames", trace}});
    return result;
}
template <class B> static Json run_bench(const Args &args, const Json &m, std::size_t capacity) {
    if (std::string(LOB_BUILD_TYPE) != "Release")
        throw std::runtime_error("benchmarks require Release build");
    const auto mode = arg(args, "mode", "book");
    const auto input = required(args, "input");
    const U64 setup = m.at("setup_events").get<U64>();
    Json result = {{"schema_version", 1},
                   {"synthetic", true},
                   {"mode", mode},
                   {"variant", arg(args, "variant", "hash_reserved")},
                   {"input_sha256", m.at("sha256")},
                   {"engine_commit", LOB_COMMIT},
                   {"build_type", LOB_BUILD_TYPE},
                   {"compiler", std::string(
#ifdef _MSC_VER
                                    "MSVC " + std::to_string(_MSC_VER)
#else
                                    __VERSION__
#endif
                                        )},
                   {"cpu", arg(args, "cpu", "unbound")}};
    if (args.contains("cpu"))
        affinity(integer<unsigned>(args.at("cpu")));
    auto start = Clock::now();
    B b(capacity);
    result["construction_seconds"] = seconds(start);
    result["memory_empty"] = memory();
    std::vector<Event> events;
    if (mode == "memory") {
        std::ifstream f(input, std::ios::binary);
        U64 n = 0;
        read_events(f, [&](const Event &e) {
            if (n++ < setup)
                apply_checked(b, e);
        });
        result["memory_populated_before_buffer"] = memory();
        result["populated_orders"] = b.statistics().active_orders;
    }
    start = Clock::now();
    if (mode != "end_to_end" && mode != "parse" && mode != "export") {
        events.reserve(m.at("total_events").get<std::size_t>());
        std::ifstream f(input, std::ios::binary);
        read_events(f, [&](const Event &e) { events.push_back(e); });
        if (events.size() != m.at("total_events").get<std::size_t>() || setup > events.size())
            throw std::runtime_error("invalid event count/setup");
    }
    result["preload_seconds"] = seconds(start);
    if (mode == "memory") {
        result["memory_with_buffer"] = memory();
        result["event_buffer_bytes"] = events.capacity() * sizeof(Event);
        for (std::size_t i = static_cast<std::size_t>(setup); i < events.size(); ++i)
            apply_checked(b, events[i]);
        result["memory_final"] = memory();
        result["buckets"] = b.buckets();
    } else if (mode == "parse") {
        std::ifstream f(input, std::ios::binary);
        std::string bytes((std::istreambuf_iterator<char>(f)), {});
        events.reserve(m.at("total_events").get<std::size_t>());
        std::istringstream stream(bytes);
        start = Clock::now();
        read_events(stream, [&](const Event &e) { events.push_back(e); });
        result["elapsed_seconds"] = seconds(start);
        result["measured_events"] = events.size();
        result["bytes"] = bytes.size();
        for (const auto &e : events)
            apply_checked(b, e);
    } else if (mode == "end_to_end" || mode == "export") {
        U64 n = 0;
        std::ofstream export_file;
        if (mode == "export") {
            export_file.open(required(args, "export-file"));
            if (!export_file)
                throw std::runtime_error("cannot open export file");
        }
        start = Clock::now();
        std::ifstream f(input, std::ios::binary);
        if (!f)
            throw std::runtime_error("cannot read input");
        read_events(f, [&](const Event &e) {
            apply_checked(b, e);
            ++n;
            if (mode == "export") {
                auto frame = state_json(b);
                frame["event"] = event_json(e);
                export_file << frame.dump() << '\n';
            }
        });
        auto summary = state_json(b); // Summary work belongs to the end-to-end measurement.
        if (mode == "export") {
            export_file.flush();
            if (!export_file)
                throw std::runtime_error("export write failure");
        }
        result["elapsed_seconds"] = seconds(start);
        result["measured_events"] = n;
        result["file_cache"] = "uncontrolled; input hash verified before timing";
    } else {
        start = Clock::now();
        for (std::size_t i = 0; i < setup; ++i)
            apply_checked(b, events[i]);
        result["setup_seconds"] = seconds(start);
        const auto measured = events.size() - static_cast<std::size_t>(setup);
        if (mode == "latency") {
            std::vector<U64> samples;
            samples.reserve(measured);
            std::vector<U64> baseline;
            baseline.reserve(10000);
            for (int i = 0; i < 10000; ++i) {
                auto t = Clock::now();
                baseline.push_back(static_cast<U64>(
                    std::chrono::duration_cast<std::chrono::nanoseconds>(Clock::now() - t).count()));
            }
            for (std::size_t i = static_cast<std::size_t>(setup); i < events.size(); ++i) {
                auto t = Clock::now();
                auto r = b.apply(events[i]);
                auto end = Clock::now();
                if (!r)
                    throw std::runtime_error(r.error);
                samples.push_back(
                    static_cast<U64>(std::chrono::duration_cast<std::chrono::nanoseconds>(end - t).count()));
            }
            if (args.contains("samples-file")) {
                std::ofstream sample_file(args.at("samples-file"));
                if (!sample_file)
                    throw std::runtime_error("cannot open latency sample file");
                sample_file << "duration_ns\n";
                for (auto duration : samples)
                    sample_file << duration << '\n';
                sample_file.flush();
                if (!sample_file)
                    throw std::runtime_error("latency sample write failure");
            }
            std::sort(samples.begin(), samples.end());
            std::sort(baseline.begin(), baseline.end());
            if (samples.empty())
                throw std::runtime_error("no measured events");
            auto pct = [&](std::size_t numerator) {
                return samples[(samples.size() * numerator + 99) / 100 - 1];
            };
            result["latency_ns"] = {{"p50", pct(50)},
                                    {"p95", pct(95)},
                                    {"p99", pct(99)},
                                    {"max", samples.back()},
                                    {"timer_pair_p50", baseline[4999]},
                                    {"samples", samples.size()},
                                    {"method", "nearest rank; no overhead subtraction"}};
        } else if (mode == "book" || mode == "analytics") {
            double sink = 0;
            start = Clock::now();
            for (std::size_t i = static_cast<std::size_t>(setup); i < events.size(); ++i) {
                apply_checked(b, events[i]);
                if (mode == "analytics") {
                    const auto a = analyze(b);
                    // Consume every reported metric so release optimization retains its work.
                    sink += a.midpoint.value_or(0) + a.spread.value_or(0) + a.imbalance.value_or(0) +
                            a.imbalance5.value_or(0) + a.weighted_midpoint.value_or(0) + a.vwap.value_or(0) +
                            static_cast<double>(a.status.size());
                }
            }
            result["elapsed_seconds"] = seconds(start);
            result["analytics_sink"] = sink;
        } else
            throw std::runtime_error("unknown benchmark mode");
        result["measured_events"] = measured;
    }
    const auto final = state_json(b, std::numeric_limits<std::size_t>::max(), true);
    if (!b.invariants())
        throw std::runtime_error("benchmark invariant failure");
    result["final_state_sha256"] = hash_text(final.dump());
    result["statistics"] = final.at("statistics");
    if (!result.contains("memory_final"))
        result["memory_final"] = memory();
    result["buckets"] = b.buckets();
    if (result.contains("elapsed_seconds")) {
        const auto elapsed = result.at("elapsed_seconds").get<double>();
        const auto n = result.at("measured_events").get<double>();
        if (elapsed <= 0 || n <= 0)
            throw std::runtime_error("empty/zero-duration benchmark");
        result["events_per_second"] = n / elapsed;
        result["average_ns_per_event"] = elapsed * 1e9 / n;
    }
    return result;
}
int main(int argc, char **argv) {
    Args args;
    try {
        if (argc == 2 && std::string(argv[1]) == "--version") {
            std::cout << "lob 1.0.0 " << LOB_COMMIT << ' ' << LOB_BUILD_TYPE << '\n';
            return 0;
        }
        if (argc < 2)
            throw std::runtime_error("usage: lob replay|validate|inspect|bench --input FILE --manifest FILE");
        const std::string command = argv[1];
        if (command != "replay" && command != "validate" && command != "inspect" && command != "bench" &&
            command != "audit")
            throw std::runtime_error("unknown command");
        const std::vector<std::string> allowed{"input",       "manifest",     "output",        "variant",
                                               "sequence",    "mode",         "cpu",           "export-file",
                                               "trace-limit", "samples-file", "trace-from-ns", "trace-to-ns"};
        for (int i = 2; i < argc; ++i) {
            std::string key = argv[i];
            if (!key.starts_with("--"))
                throw std::runtime_error("expected --option");
            key.erase(0, 2);
            if (args.contains(key))
                throw std::runtime_error("duplicate option");
            if (key == "trace" || key == "full-state" || key == "checkpoints")
                args[key] = "true";
            else {
                if (std::find(allowed.begin(), allowed.end(), key) == allowed.end() || i + 1 >= argc)
                    throw std::runtime_error("unknown/missing option: " + key);
                args[key] = argv[++i];
            }
        }
        const auto m = manifest(args);
        const auto variant = arg(args, "variant", "hash_reserved");
        const auto cap = variant == "hash_reserved" ? m.at("max_live_orders").get<std::size_t>() : 0;
        auto run = [&]<class B>() {
            return command == "bench" ? run_bench<B>(args, m, cap) : run_replay<B>(command, args, m, cap);
        };
        Json result;
        if (variant == "tree")
            result = run.template operator()<Book<TreeIndex>>();
        else if (variant == "hash" || variant == "hash_reserved")
            result = run.template operator()<Book<HashIndex>>();
        else
            throw std::runtime_error("unknown variant");
        if (command == "bench" && args.contains("output")) {
            if (fs::exists(args.at("output")))
                throw std::runtime_error("output file exists");
            write_json(args.at("output"), result);
        }
        std::cout << result.dump() << '\n';
        return 0;
    } catch (const std::exception &e) {
        std::cerr
            << Json({{"complete", false}, {"input", arg(args, "input", "")}, {"error", e.what()}}).dump()
            << '\n';
        return 2;
    }
}
