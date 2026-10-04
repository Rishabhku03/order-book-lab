#include "lob/parser.hpp"
extern "C" int LLVMFuzzerTestOneInput(const unsigned char *data, std::size_t size) {
    try {
        (void)lob::parse_line(std::string_view(reinterpret_cast<const char *>(data), size));
    } catch (const std::runtime_error &) {
    }
    return 0;
}
