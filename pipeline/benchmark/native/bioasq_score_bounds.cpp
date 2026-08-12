#include <array>
#include <cstdint>
#include <fstream>
#include <iostream>
#include <limits>
#include <stdexcept>
#include <string>
#include <vector>

namespace {

using UInt128 = unsigned __int128;

constexpr std::array<char, 8> kEdgeMagic{'L', 'C', 'E', 'D', 'G', 'E', '1', '\0'};
constexpr std::array<char, 8> kBoundsMagic{'L', 'C', 'B', 'N', 'D', 'S', '1', '\0'};
constexpr std::uint8_t kScaleExponent = 21;
constexpr UInt128 kScale = static_cast<UInt128>(1000000000000000000ULL) * 1000;

template <typename T>
T read_value(std::istream& input) {
    T value{};
    input.read(reinterpret_cast<char*>(&value), sizeof(T));
    if (!input) {
        throw std::runtime_error("truncated edge graph");
    }
    return value;
}

template <typename T>
void write_value(std::ostream& output, const T value) {
    output.write(reinterpret_cast<const char*>(&value), sizeof(T));
    if (!output) {
        throw std::runtime_error("failed to write bounds artifact");
    }
}

void write_uint128(std::ostream& output, UInt128 value) {
    std::array<unsigned char, 16> bytes{};
    for (std::size_t index = 0; index < bytes.size(); ++index) {
        bytes[index] = static_cast<unsigned char>(value & 0xff);
        value >>= 8;
    }
    output.write(reinterpret_cast<const char*>(bytes.data()), bytes.size());
    if (!output) {
        throw std::runtime_error("failed to write UInt128 bound");
    }
}

struct Edge {
    std::uint16_t left = 0;
    std::uint16_t right = 0;
    std::uint32_t count = 0;
};

Edge read_edge(std::istream& input) {
    return Edge{
        read_value<std::uint16_t>(input),
        read_value<std::uint16_t>(input),
        read_value<std::uint32_t>(input),
    };
}

struct TargetBridge {
    std::uint16_t bridge = 0;
    std::uint32_t ab_count = 0;
    std::uint32_t bc_count = 0;
};

struct Rational {
    std::uint64_t numerator = 0;
    std::uint64_t denominator = 1;
};

Rational minimum_path_weight(
    const std::uint32_t ab_count,
    const std::uint32_t bc_count,
    const std::uint32_t a_support,
    const std::uint32_t b_support,
    const std::uint32_t c_support
) {
    const std::uint64_t ab_denominator =
        static_cast<std::uint64_t>(a_support) + b_support - ab_count;
    const std::uint64_t bc_denominator =
        static_cast<std::uint64_t>(b_support) + c_support - bc_count;
    const std::uint64_t left_product =
        static_cast<std::uint64_t>(ab_count) * bc_denominator;
    const std::uint64_t right_product =
        static_cast<std::uint64_t>(bc_count) * ab_denominator;
    if (left_product <= right_product) {
        return Rational{ab_count, ab_denominator};
    }
    return Rational{bc_count, bc_denominator};
}

void run(
    const std::string& edge_path,
    const std::uint16_t seed,
    const std::uint16_t target,
    const std::uint16_t threshold,
    const std::string& output_path
) {
    std::ifstream input(edge_path, std::ios::binary);
    if (!input) {
        throw std::runtime_error("cannot open edge graph: " + edge_path);
    }
    std::array<char, 8> magic{};
    input.read(magic.data(), magic.size());
    if (!input || magic != kEdgeMagic) {
        throw std::runtime_error("edge graph magic mismatch");
    }
    const auto node_count = read_value<std::uint32_t>(input);
    const auto cutoff = read_value<std::uint16_t>(input);
    const auto edge_count = read_value<std::uint64_t>(input);
    if (
        node_count == 0
        || node_count > std::numeric_limits<std::uint16_t>::max()
        || seed >= node_count
        || target >= node_count
        || (threshold != 5 && threshold != 10)
    ) {
        throw std::runtime_error("bounds request is outside the frozen graph contract");
    }
    std::vector<std::uint32_t> support(node_count, 0);
    input.read(
        reinterpret_cast<char*>(support.data()),
        static_cast<std::streamsize>(support.size() * sizeof(std::uint32_t))
    );
    if (!input) {
        throw std::runtime_error("truncated graph support array");
    }
    if (support[seed] < threshold || support[target] < threshold) {
        throw std::runtime_error("case endpoint is ineligible at requested support");
    }
    const auto edge_offset = input.tellg();
    std::vector<std::uint32_t> seed_counts(node_count, 0);
    for (std::uint64_t index = 0; index < edge_count; ++index) {
        const auto edge = read_edge(input);
        if (edge.left == seed) {
            seed_counts[edge.right] = edge.count;
        } else if (edge.right == seed) {
            seed_counts[edge.left] = edge.count;
        }
    }

    input.clear();
    input.seekg(edge_offset);
    if (!input) {
        throw std::runtime_error("failed to rewind edge graph");
    }
    std::vector<UInt128> lower(node_count, 0);
    std::vector<UInt128> upper(node_count, 0);
    std::vector<std::uint32_t> bridge_count(node_count, 0);
    std::vector<TargetBridge> target_bridges;
    const auto add_path = [&](
                              const std::uint16_t bridge,
                              const std::uint16_t candidate,
                              const std::uint32_t bc_count
                          ) {
        if (
            candidate == seed
            || support[bridge] < threshold
            || support[candidate] < threshold
        ) {
            return;
        }
        const auto ab_count = seed_counts[bridge];
        const auto weight = minimum_path_weight(
            ab_count,
            bc_count,
            support[seed],
            support[bridge],
            support[candidate]
        );
        const UInt128 scaled = static_cast<UInt128>(weight.numerator) * kScale;
        const UInt128 floor_value = scaled / weight.denominator;
        const UInt128 ceil_value =
            floor_value + (scaled % weight.denominator == 0 ? 0 : 1);
        lower[candidate] += floor_value;
        upper[candidate] += ceil_value;
        if (bridge_count[candidate] == std::numeric_limits<std::uint32_t>::max()) {
            throw std::runtime_error("candidate bridge count overflow");
        }
        ++bridge_count[candidate];
        if (candidate == target) {
            target_bridges.push_back(TargetBridge{bridge, ab_count, bc_count});
        }
    };
    for (std::uint64_t index = 0; index < edge_count; ++index) {
        const auto edge = read_edge(input);
        if (seed_counts[edge.left] > 0) {
            add_path(edge.left, edge.right, edge.count);
        }
        if (seed_counts[edge.right] > 0) {
            add_path(edge.right, edge.left, edge.count);
        }
    }

    std::ofstream output(output_path, std::ios::binary | std::ios::trunc);
    if (!output) {
        throw std::runtime_error("cannot open bounds output: " + output_path);
    }
    output.write(kBoundsMagic.data(), kBoundsMagic.size());
    write_value(output, node_count);
    write_value(output, cutoff);
    write_value(output, threshold);
    write_value(output, seed);
    write_value(output, target);
    write_value(output, kScaleExponent);
    write_value(output, static_cast<std::uint8_t>(0));
    write_value(output, static_cast<std::uint64_t>(target_bridges.size()));
    for (std::uint32_t node = 0; node < node_count; ++node) {
        write_uint128(output, lower[node]);
        write_uint128(output, upper[node]);
        write_value(output, seed_counts[node]);
        write_value(output, bridge_count[node]);
    }
    for (const auto& bridge : target_bridges) {
        write_value(output, bridge.bridge);
        write_value(output, bridge.ab_count);
        write_value(output, bridge.bc_count);
    }
    if (!output) {
        throw std::runtime_error("failed to finish bounds output");
    }
    std::cout << "nodes=" << node_count << '\n';
    std::cout << "edges=" << edge_count << '\n';
    std::cout << "target_bridges=" << target_bridges.size() << '\n';
}

std::uint16_t parse_uint16(const char* value, const std::string& field) {
    const auto parsed = std::stoul(value);
    if (parsed > std::numeric_limits<std::uint16_t>::max()) {
        throw std::runtime_error(field + " exceeds uint16");
    }
    return static_cast<std::uint16_t>(parsed);
}

}  // namespace

int main(int argc, char** argv) {
    try {
        if (argc != 6) {
            std::cerr << "usage: bioasq_score_bounds EDGES SEED TARGET THRESHOLD OUTPUT\n";
            return 2;
        }
        run(
            argv[1],
            parse_uint16(argv[2], "seed"),
            parse_uint16(argv[3], "target"),
            parse_uint16(argv[4], "threshold"),
            argv[5]
        );
        return 0;
    } catch (const std::exception& error) {
        std::cerr << "bioasq_score_bounds: " << error.what() << '\n';
        return 1;
    }
}
