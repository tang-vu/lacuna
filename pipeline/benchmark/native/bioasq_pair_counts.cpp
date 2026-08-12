#include <algorithm>
#include <array>
#include <cstdint>
#include <cstring>
#include <fstream>
#include <iostream>
#include <limits>
#include <stdexcept>
#include <string>
#include <vector>

namespace {

constexpr std::array<char, 8> kCorpusMagic{'L', 'C', 'N', 'A', 'B', 'Q', '2', '\0'};
constexpr std::array<char, 8> kEdgeMagic{'L', 'C', 'E', 'D', 'G', 'E', '1', '\0'};
constexpr std::uint16_t kFirstCutoff = 2011;
constexpr std::uint16_t kSecondCutoff = 2012;
constexpr std::uint32_t kSparseMinimumSupport = 5;

template <typename T>
T read_value(std::istream& input) {
    T value{};
    input.read(reinterpret_cast<char*>(&value), sizeof(T));
    if (!input) {
        throw std::runtime_error("truncated compact corpus");
    }
    return value;
}

template <typename T>
void write_value(std::ostream& output, const T value) {
    output.write(reinterpret_cast<const char*>(&value), sizeof(T));
    if (!output) {
        throw std::runtime_error("failed to write edge artifact");
    }
}

std::uint64_t pair_index(
    const std::uint32_t left,
    const std::uint32_t right,
    const std::uint32_t node_count
) {
    return static_cast<std::uint64_t>(left) * node_count
        - (static_cast<std::uint64_t>(left) * (left + 1)) / 2
        + (right - left - 1);
}

struct EdgeWriter {
    std::fstream stream;
    std::uint64_t edge_count = 0;
    std::streampos edge_count_position{};

    EdgeWriter(
        const std::string& path,
        const std::uint32_t node_count,
        const std::uint16_t cutoff,
        const std::vector<std::uint32_t>& support
    ) : stream(path, std::ios::binary | std::ios::out | std::ios::trunc) {
        if (!stream) {
            throw std::runtime_error("cannot open edge output: " + path);
        }
        stream.write(kEdgeMagic.data(), kEdgeMagic.size());
        write_value(stream, node_count);
        write_value(stream, cutoff);
        edge_count_position = stream.tellp();
        write_value(stream, edge_count);
        stream.write(
            reinterpret_cast<const char*>(support.data()),
            static_cast<std::streamsize>(support.size() * sizeof(std::uint32_t))
        );
        if (!stream) {
            throw std::runtime_error("failed to write edge header: " + path);
        }
    }

    void write_edge(
        const std::uint16_t left,
        const std::uint16_t right,
        const std::uint32_t count
    ) {
        write_value(stream, left);
        write_value(stream, right);
        write_value(stream, count);
        ++edge_count;
    }

    void finish() {
        stream.seekp(edge_count_position);
        write_value(stream, edge_count);
        stream.close();
    }
};

void run(
    const std::string& input_path,
    const std::string& first_path,
    const std::string& second_path
) {
    std::ifstream input(input_path, std::ios::binary);
    if (!input) {
        throw std::runtime_error("cannot open compact corpus: " + input_path);
    }
    std::array<char, 8> magic{};
    input.read(magic.data(), magic.size());
    if (!input || magic != kCorpusMagic) {
        throw std::runtime_error("compact corpus magic mismatch");
    }
    const auto node_count = read_value<std::uint32_t>(input);
    const auto bucket_count = read_value<std::uint8_t>(input);
    const auto first_cutoff = read_value<std::uint16_t>(input);
    const auto second_cutoff = read_value<std::uint16_t>(input);
    if (
        node_count == 0
        || node_count > std::numeric_limits<std::uint16_t>::max()
        || bucket_count != 2
        || first_cutoff != kFirstCutoff
        || second_cutoff != kSecondCutoff
    ) {
        throw std::runtime_error("compact corpus header mismatch");
    }

    const auto pair_count =
        (static_cast<std::uint64_t>(node_count) * (node_count - 1)) / 2;
    if (pair_count > std::numeric_limits<std::size_t>::max()) {
        throw std::runtime_error("pair matrix is too large for this process");
    }
    std::vector<std::uint32_t> first_pairs(static_cast<std::size_t>(pair_count), 0);
    std::vector<std::uint32_t> second_pairs(static_cast<std::size_t>(pair_count), 0);
    std::vector<std::uint32_t> first_support(node_count, 0);
    std::vector<std::uint32_t> second_support(node_count, 0);
    std::vector<std::uint16_t> labels;
    std::uint64_t document_count = 0;

    while (true) {
        std::uint8_t bucket = 0;
        input.read(reinterpret_cast<char*>(&bucket), sizeof(bucket));
        if (input.eof()) {
            break;
        }
        if (!input || bucket > 1) {
            throw std::runtime_error("invalid compact document bucket");
        }
        const auto label_count = read_value<std::uint16_t>(input);
        labels.resize(label_count);
        input.read(
            reinterpret_cast<char*>(labels.data()),
            static_cast<std::streamsize>(labels.size() * sizeof(std::uint16_t))
        );
        if (!input) {
            throw std::runtime_error("truncated compact document labels");
        }
        if (!std::is_sorted(labels.begin(), labels.end())) {
            throw std::runtime_error("compact document labels are not sorted");
        }
        if (std::adjacent_find(labels.begin(), labels.end()) != labels.end()) {
            throw std::runtime_error("compact document contains duplicate labels");
        }
        auto& support = bucket == 0 ? first_support : second_support;
        auto& pairs = bucket == 0 ? first_pairs : second_pairs;
        for (const auto label : labels) {
            if (label >= node_count) {
                throw std::runtime_error("compact document label is outside node range");
            }
            if (support[label] == std::numeric_limits<std::uint32_t>::max()) {
                throw std::runtime_error("descriptor support overflow");
            }
            ++support[label];
        }
        for (std::size_t i = 0; i < labels.size(); ++i) {
            for (std::size_t j = i + 1; j < labels.size(); ++j) {
                auto& count = pairs[pair_index(labels[i], labels[j], node_count)];
                if (count == std::numeric_limits<std::uint32_t>::max()) {
                    throw std::runtime_error("descriptor pair count overflow");
                }
                ++count;
            }
        }
        ++document_count;
    }

    std::vector<std::uint32_t> cumulative_support(node_count, 0);
    for (std::uint32_t node = 0; node < node_count; ++node) {
        cumulative_support[node] = first_support[node] + second_support[node];
        if (cumulative_support[node] < first_support[node]) {
            throw std::runtime_error("cumulative descriptor support overflow");
        }
    }
    EdgeWriter first_writer(first_path, node_count, kFirstCutoff, first_support);
    EdgeWriter second_writer(second_path, node_count, kSecondCutoff, cumulative_support);
    std::uint64_t index = 0;
    for (std::uint32_t left = 0; left < node_count; ++left) {
        for (std::uint32_t right = left + 1; right < node_count; ++right, ++index) {
            const auto first_count = first_pairs[index];
            const auto second_count = first_count + second_pairs[index];
            if (second_count < first_count) {
                throw std::runtime_error("cumulative descriptor pair count overflow");
            }
            if (
                first_count > 0
                && first_support[left] >= kSparseMinimumSupport
                && first_support[right] >= kSparseMinimumSupport
            ) {
                first_writer.write_edge(
                    static_cast<std::uint16_t>(left),
                    static_cast<std::uint16_t>(right),
                    first_count
                );
            }
            if (
                second_count > 0
                && cumulative_support[left] >= kSparseMinimumSupport
                && cumulative_support[right] >= kSparseMinimumSupport
            ) {
                second_writer.write_edge(
                    static_cast<std::uint16_t>(left),
                    static_cast<std::uint16_t>(right),
                    second_count
                );
            }
        }
    }
    first_writer.finish();
    second_writer.finish();
    std::cout << "documents=" << document_count << '\n';
    std::cout << "nodes=" << node_count << '\n';
    std::cout << "pairs=" << pair_count << '\n';
    std::cout << "edges_2011=" << first_writer.edge_count << '\n';
    std::cout << "edges_2012=" << second_writer.edge_count << '\n';
}

}  // namespace

int main(int argc, char** argv) {
    try {
        if (argc != 4) {
            std::cerr << "usage: bioasq_pair_counts CORPUS EDGES_2011 EDGES_2012\n";
            return 2;
        }
        run(argv[1], argv[2], argv[3]);
        return 0;
    } catch (const std::exception& error) {
        std::cerr << "bioasq_pair_counts: " << error.what() << '\n';
        return 1;
    }
}
