#pragma once
#include "lob/types.hpp"
#include <charconv>
#include <istream>
#include <stdexcept>
#include <string_view>

namespace lob {
inline constexpr std::string_view csv_header =
    "sequence,timestamp_ns,type,order_id,side,price_ticks,quantity,new_order_id";
template <class T> T integer(std::string_view text) {
    T value{};
    auto [end, ec] = std::from_chars(text.data(), text.data() + text.size(), value);
    if (text.empty() || ec != std::errc{} || end != text.data() + text.size())
        throw std::runtime_error("invalid integer");
    return value;
}
inline Event parse_line(std::string_view line) {
    if (line.size() > 4096)
        throw std::runtime_error("line exceeds 4096 bytes");
    if (!line.empty() && line.back() == '\r')
        line.remove_suffix(1);
    std::array<std::string_view, 8> f{};
    for (std::size_t i = 0; i < 8; ++i) {
        auto pos = line.find(',');
        if ((i < 7 && pos == std::string_view::npos) || (i == 7 && pos != std::string_view::npos))
            throw std::runtime_error("expected eight fields");
        f[i] = line.substr(0, pos);
        if (i < 7)
            line.remove_prefix(pos + 1);
    }
    Event e;
    e.sequence = integer<U64>(f[0]);
    e.timestamp_ns = integer<U64>(f[1]);
    e.order_id = integer<U64>(f[3]);
    if (f[2] == "ADD")
        e.type = Kind::add;
    else if (f[2] == "CANCEL")
        e.type = Kind::cancel;
    else if (f[2] == "DELETE")
        e.type = Kind::erase;
    else if (f[2] == "EXECUTE")
        e.type = Kind::execute;
    else if (f[2] == "REPLACE")
        e.type = Kind::replace;
    else
        throw std::runtime_error("unknown event type");
    if (!f[4].empty()) {
        if (f[4] == "B")
            e.side = Side::bid;
        else if (f[4] == "A")
            e.side = Side::ask;
        else
            throw std::runtime_error("invalid side");
    }
    if (!f[5].empty())
        e.price_ticks = integer<Price>(f[5]);
    if (!f[6].empty())
        e.quantity = integer<U64>(f[6]);
    if (!f[7].empty())
        e.new_order_id = integer<U64>(f[7]);
    return e;
}
// Bounded reading avoids allocating arbitrary memory for an invalid input line.
inline bool read_line(std::istream &in, std::string &line) {
    line.clear();
    char c;
    while (in.get(c)) {
        if (c == '\n')
            return true;
        if (line.size() == 4096)
            throw std::runtime_error("line exceeds 4096 bytes");
        line.push_back(c);
    }
    if (in.bad())
        throw std::runtime_error("input read failure");
    return !line.empty();
}
template <class F> void read_events(std::istream &in, F consume) {
    std::string line;
    if (!read_line(in, line))
        throw std::runtime_error("empty input");
    if (!line.empty() && line.back() == '\r')
        line.pop_back();
    if (line != csv_header)
        throw std::runtime_error("line 1: invalid header");
    U64 n = 1;
    std::string failure;
    try {
        while (true) {
            ++n;
            if (!read_line(in, line))
                break;
            consume(parse_line(line));
        }
    } catch (const std::exception &e) {
        failure = "line " + std::to_string(n) + ": " + e.what();
    }
    if (!failure.empty())
        throw std::runtime_error(failure);
}
} // namespace lob
