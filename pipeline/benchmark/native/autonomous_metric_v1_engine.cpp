#include <algorithm>
#include <array>
#include <cstdint>
#include <cstring>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <limits>
#include <map>
#include <stdexcept>
#include <string>
#include <vector>

namespace fs = std::filesystem;

constexpr std::uint64_t kTieSalt = 0x7a6b4d2f19c3e805ULL;
constexpr std::size_t kIoRows = 1U << 20;

#pragma pack(push, 1)
struct PositiveRow {
    std::uint64_t key;
    std::uint64_t count;
};

struct WeightRow {
    std::uint64_t adamic_adar_q48;
    std::uint64_t resource_allocation_q48;
};

struct ScoreRow {
    std::uint64_t pair_key;
    std::uint64_t adamic_adar_q48;
    std::uint64_t resource_allocation_q48;
    std::uint64_t prevalence;
    std::uint32_t common_neighbors;
    std::uint32_t jaccard_denominator;
    std::uint64_t preferential_attachment;
};
#pragma pack(pop)

static_assert(sizeof(PositiveRow) == 16);
static_assert(sizeof(WeightRow) == 16);
static_assert(sizeof(ScoreRow) == 48);

struct RankItem {
    std::uint64_t score;
    std::uint64_t tie;
    std::uint64_t pair_key;
};

[[noreturn]] void fail(const std::string& message) {
    throw std::runtime_error(message);
}

void require_little_endian() {
    const std::uint16_t value = 1;
    if (*reinterpret_cast<const std::uint8_t*>(&value) != 1) {
        fail("metric-v1 engine requires a little-endian host");
    }
}

std::uint64_t parse_u64(const std::string& text, const std::string& name) {
    std::size_t consumed = 0;
    unsigned long long value = 0;
    try {
        value = std::stoull(text, &consumed, 10);
    } catch (...) {
        fail(name + " is not an unsigned integer");
    }
    if (consumed != text.size()) {
        fail(name + " is not an unsigned integer");
    }
    return static_cast<std::uint64_t>(value);
}

std::map<std::string, std::string> parse_args(int argc, char** argv, int start) {
    std::map<std::string, std::string> result;
    for (int index = start; index < argc; index += 2) {
        const std::string key(argv[index]);
        if (key.rfind("--", 0) != 0 || index + 1 >= argc) {
            fail("arguments must be --name value pairs");
        }
        if (!result.emplace(key.substr(2), argv[index + 1]).second) {
            fail("duplicate argument: " + key);
        }
    }
    return result;
}

const std::string& required(
    const std::map<std::string, std::string>& args,
    const std::string& name
) {
    const auto found = args.find(name);
    if (found == args.end()) {
        fail("missing --" + name);
    }
    return found->second;
}

std::uint64_t artifact_file_size(const fs::path& path) {
    std::error_code error;
    const auto size = fs::file_size(path, error);
    if (error) {
        fail("cannot stat " + path.string() + ": " + error.message());
    }
    return static_cast<std::uint64_t>(size);
}

template <typename T>
std::vector<T> read_vector(const fs::path& path, const std::string& name) {
    const auto bytes = artifact_file_size(path);
    if (bytes % sizeof(T) != 0) {
        fail(name + " byte count is not row-aligned");
    }
    const auto rows64 = bytes / sizeof(T);
    if (rows64 > static_cast<std::uint64_t>(std::numeric_limits<std::size_t>::max())) {
        fail(name + " is too large for this host");
    }
    std::vector<T> values(static_cast<std::size_t>(rows64));
    std::ifstream input(path, std::ios::binary);
    if (!input) {
        fail("cannot open " + name + ": " + path.string());
    }
    if (bytes != 0) {
        input.read(reinterpret_cast<char*>(values.data()), static_cast<std::streamsize>(bytes));
    }
    if (!input || static_cast<std::uint64_t>(input.gcount()) != bytes) {
        fail("short read from " + name);
    }
    return values;
}

template <typename T>
void write_vector_new(const fs::path& path, const std::vector<T>& values, const std::string& name) {
    if (fs::exists(path)) {
        fail(name + " already exists; refusal to overwrite: " + path.string());
    }
    fs::create_directories(path.parent_path());
    std::ofstream output(path, std::ios::binary | std::ios::out);
    if (!output) {
        fail("cannot create " + name + ": " + path.string());
    }
    if (!values.empty()) {
        const auto bytes = values.size() * sizeof(T);
        output.write(reinterpret_cast<const char*>(values.data()), static_cast<std::streamsize>(bytes));
    }
    output.flush();
    if (!output) {
        fail("failed writing " + name);
    }
}

std::uint64_t splitmix64(std::uint64_t value) {
    value += 0x9e3779b97f4a7c15ULL;
    value = (value ^ (value >> 30U)) * 0xbf58476d1ce4e5b9ULL;
    value = (value ^ (value >> 27U)) * 0x94d049bb133111ebULL;
    return value ^ (value >> 31U);
}

bool is_backbone_edge(
    std::uint64_t count,
    std::uint64_t denominator,
    std::uint64_t left_support,
    std::uint64_t right_support
) {
    if (count == 0 || denominator == 0) {
        return false;
    }
    const unsigned __int128 observed =
        static_cast<unsigned __int128>(count) * denominator;
    const unsigned __int128 expected =
        static_cast<unsigned __int128>(left_support) * right_support;
    return observed > expected;
}

template <typename Callback>
std::uint64_t for_each_positive(
    const fs::path& path,
    std::uint64_t nodes,
    Callback callback
) {
    const auto bytes = artifact_file_size(path);
    if (bytes % sizeof(PositiveRow) != 0) {
        fail("positive-pair file is not 16-byte aligned");
    }
    const std::uint64_t rows = bytes / sizeof(PositiveRow);
    std::ifstream input(path, std::ios::binary);
    if (!input) {
        fail("cannot open positive-pair file");
    }
    std::vector<PositiveRow> buffer(kIoRows);
    std::uint64_t consumed = 0;
    std::uint64_t previous_key = 0;
    bool have_previous = false;
    while (consumed < rows) {
        const auto take = static_cast<std::size_t>(
            std::min<std::uint64_t>(buffer.size(), rows - consumed)
        );
        const auto chunk_bytes = take * sizeof(PositiveRow);
        input.read(reinterpret_cast<char*>(buffer.data()), static_cast<std::streamsize>(chunk_bytes));
        if (!input || static_cast<std::size_t>(input.gcount()) != chunk_bytes) {
            fail("short read from positive-pair file");
        }
        for (std::size_t offset = 0; offset < take; ++offset) {
            const auto& row = buffer[offset];
            if ((have_previous && row.key <= previous_key) || row.count == 0) {
                fail("positive-pair order or count invariant failed");
            }
            const std::uint64_t left = row.key / nodes;
            const std::uint64_t right = row.key % nodes;
            if (left >= right || right >= nodes) {
                fail("positive-pair key is outside the descriptor-pair universe");
            }
            callback(row, static_cast<std::uint32_t>(left), static_cast<std::uint32_t>(right));
            previous_key = row.key;
            have_previous = true;
        }
        consumed += take;
    }
    return rows;
}

void build_backbone(const std::map<std::string, std::string>& args) {
    const fs::path supports_path(required(args, "supports"));
    const fs::path positive_path(required(args, "positive"));
    const fs::path offsets_path(required(args, "offsets"));
    const fs::path neighbors_path(required(args, "neighbors"));
    const std::uint64_t nodes = parse_u64(required(args, "nodes"), "nodes");
    const std::uint64_t denominator = parse_u64(required(args, "denominator"), "denominator");
    if (nodes == 0 || nodes > std::numeric_limits<std::uint32_t>::max()) {
        fail("node count is outside uint32");
    }
    if (fs::exists(offsets_path) || fs::exists(neighbors_path)) {
        fail("backbone output exists; audit it or select a new output directory");
    }
    const auto supports = read_vector<std::uint64_t>(supports_path, "support vector");
    if (supports.size() != nodes) {
        fail("support vector row count differs from node count");
    }
    std::vector<std::uint64_t> degrees(nodes, 0);
    std::uint64_t edges = 0;
    const auto input_rows = for_each_positive(
        positive_path,
        nodes,
        [&](const PositiveRow& row, std::uint32_t left, std::uint32_t right) {
            if (is_backbone_edge(row.count, denominator, supports[left], supports[right])) {
                if (degrees[left] == std::numeric_limits<std::uint32_t>::max() ||
                    degrees[right] == std::numeric_limits<std::uint32_t>::max()) {
                    fail("backbone degree overflowed uint32");
                }
                ++degrees[left];
                ++degrees[right];
                ++edges;
            }
        }
    );
    if (edges > std::numeric_limits<std::size_t>::max() / 2U) {
        fail("backbone neighbor vector is too large for this host");
    }
    std::vector<std::uint64_t> offsets(nodes + 1, 0);
    for (std::size_t index = 0; index < nodes; ++index) {
        offsets[index + 1] = offsets[index] + degrees[index];
    }
    if (offsets.back() != edges * 2U) {
        fail("backbone degree sum drifted");
    }
    std::vector<std::uint32_t> neighbors(static_cast<std::size_t>(offsets.back()));
    std::vector<std::uint64_t> cursors(offsets.begin(), offsets.end() - 1);
    std::uint64_t second_pass_edges = 0;
    for_each_positive(
        positive_path,
        nodes,
        [&](const PositiveRow& row, std::uint32_t left, std::uint32_t right) {
            if (is_backbone_edge(row.count, denominator, supports[left], supports[right])) {
                neighbors[static_cast<std::size_t>(cursors[left]++)] = right;
                neighbors[static_cast<std::size_t>(cursors[right]++)] = left;
                ++second_pass_edges;
            }
        }
    );
    if (second_pass_edges != edges) {
        fail("backbone edge count differs between passes");
    }
    for (std::size_t node = 0; node < nodes; ++node) {
        if (cursors[node] != offsets[node + 1]) {
            fail("backbone CSR fill count drifted");
        }
        const auto first = neighbors.begin() + static_cast<std::ptrdiff_t>(offsets[node]);
        const auto last = neighbors.begin() + static_cast<std::ptrdiff_t>(offsets[node + 1]);
        if (!std::is_sorted(first, last) || std::adjacent_find(first, last) != last) {
            fail("backbone neighbor list is not strictly sorted");
        }
    }
    write_vector_new(offsets_path, offsets, "backbone offsets");
    write_vector_new(neighbors_path, neighbors, "backbone neighbors");
    std::cout << "positive_rows=" << input_rows << "\n";
    std::cout << "backbone_edges=" << edges << "\n";
    std::cout << "neighbor_rows=" << neighbors.size() << "\n";
}

void audit_backbone(const std::map<std::string, std::string>& args) {
    const auto supports = read_vector<std::uint64_t>(required(args, "supports"), "support vector");
    const auto offsets = read_vector<std::uint64_t>(required(args, "offsets"), "backbone offsets");
    const auto neighbors = read_vector<std::uint32_t>(required(args, "neighbors"), "backbone neighbors");
    const fs::path positive_path(required(args, "positive"));
    const std::uint64_t nodes = parse_u64(required(args, "nodes"), "nodes");
    const std::uint64_t denominator = parse_u64(required(args, "denominator"), "denominator");
    if (supports.size() != nodes || offsets.size() != nodes + 1 || offsets.front() != 0 ||
        offsets.back() != neighbors.size()) {
        fail("backbone audit dimensions drifted");
    }
    std::vector<std::uint64_t> cursors(offsets.begin(), offsets.end() - 1);
    std::uint64_t expected_edges = 0;
    const auto input_rows = for_each_positive(
        positive_path,
        nodes,
        [&](const PositiveRow& row, std::uint32_t left, std::uint32_t right) {
            if (!is_backbone_edge(row.count, denominator, supports[left], supports[right])) {
                return;
            }
            if (cursors[left] >= offsets[left + 1] || cursors[right] >= offsets[right + 1] ||
                neighbors[static_cast<std::size_t>(cursors[left])] != right ||
                neighbors[static_cast<std::size_t>(cursors[right])] != left) {
                fail("backbone differs from exact positive-association source reduction");
            }
            ++cursors[left];
            ++cursors[right];
            ++expected_edges;
        }
    );
    for (std::size_t node = 0; node < nodes; ++node) {
        if (cursors[node] != offsets[node + 1]) {
            fail("backbone contains an extra or missing neighbor");
        }
    }
    if (neighbors.size() != expected_edges * 2U) {
        fail("backbone degree sum differs from audited edge count");
    }
    std::cout << "audited_positive_rows=" << input_rows << "\n";
    std::cout << "audited_backbone_edges=" << expected_edges << "\n";
}

struct GraphInputs {
    std::uint64_t nodes;
    std::vector<std::uint64_t> supports;
    std::vector<std::uint64_t> offsets;
    std::vector<std::uint32_t> neighbors;
    std::vector<WeightRow> weights;
};

GraphInputs load_graph(const std::map<std::string, std::string>& args) {
    GraphInputs graph;
    graph.nodes = parse_u64(required(args, "nodes"), "nodes");
    graph.supports = read_vector<std::uint64_t>(required(args, "supports"), "support vector");
    graph.offsets = read_vector<std::uint64_t>(required(args, "offsets"), "backbone offsets");
    graph.neighbors = read_vector<std::uint32_t>(required(args, "neighbors"), "backbone neighbors");
    graph.weights = read_vector<WeightRow>(required(args, "weights"), "degree weights");
    if (graph.supports.size() != graph.nodes || graph.offsets.size() != graph.nodes + 1 ||
        graph.weights.size() != graph.nodes + 1 || graph.offsets.front() != 0 ||
        graph.offsets.back() != graph.neighbors.size()) {
        fail("graph artifact dimensions drifted");
    }
    for (std::size_t node = 0; node < graph.nodes; ++node) {
        const auto begin = graph.offsets[node];
        const auto end = graph.offsets[node + 1];
        if (end < begin || end - begin > graph.nodes - 1) {
            fail("graph offset or degree drifted");
        }
        if (graph.weights[end - begin].adamic_adar_q48 == 0 && end - begin >= 2) {
            fail("degree-weight table is incomplete");
        }
        std::uint32_t previous = 0;
        bool have_previous = false;
        for (auto cursor = begin; cursor < end; ++cursor) {
            const auto neighbor = graph.neighbors[static_cast<std::size_t>(cursor)];
            if (neighbor >= graph.nodes || neighbor == node ||
                (have_previous && neighbor <= previous)) {
                fail("graph neighbor invariant drifted");
            }
            previous = neighbor;
            have_previous = true;
        }
    }
    return graph;
}

ScoreRow score_candidate(const GraphInputs& graph, std::uint64_t pair_key) {
    const std::uint64_t left = pair_key / graph.nodes;
    const std::uint64_t right = pair_key % graph.nodes;
    if (left >= right || right >= graph.nodes) {
        fail("candidate key is outside the descriptor-pair universe");
    }
    auto left_cursor = graph.offsets[left];
    const auto left_end = graph.offsets[left + 1];
    auto right_cursor = graph.offsets[right];
    const auto right_end = graph.offsets[right + 1];
    unsigned __int128 adamic_adar = 0;
    unsigned __int128 resource_allocation = 0;
    std::uint64_t common_neighbors = 0;
    while (left_cursor < left_end && right_cursor < right_end) {
        const auto left_neighbor = graph.neighbors[static_cast<std::size_t>(left_cursor)];
        const auto right_neighbor = graph.neighbors[static_cast<std::size_t>(right_cursor)];
        if (left_neighbor < right_neighbor) {
            ++left_cursor;
        } else if (right_neighbor < left_neighbor) {
            ++right_cursor;
        } else {
            const auto degree = graph.offsets[left_neighbor + 1] - graph.offsets[left_neighbor];
            if (degree < 2 || degree >= graph.weights.size()) {
                fail("common-neighbor degree is outside the weight table");
            }
            adamic_adar += graph.weights[degree].adamic_adar_q48;
            resource_allocation += graph.weights[degree].resource_allocation_q48;
            ++common_neighbors;
            ++left_cursor;
            ++right_cursor;
        }
    }
    if (adamic_adar > std::numeric_limits<std::uint64_t>::max() ||
        resource_allocation > std::numeric_limits<std::uint64_t>::max() ||
        common_neighbors > std::numeric_limits<std::uint32_t>::max()) {
        fail("candidate score overflowed its frozen integer domain");
    }
    const std::uint64_t left_degree = left_end - graph.offsets[left];
    const std::uint64_t right_degree = right_end - graph.offsets[right];
    const std::uint64_t jaccard_denominator =
        std::max<std::uint64_t>(1, left_degree + right_degree - common_neighbors);
    const unsigned __int128 prevalence =
        static_cast<unsigned __int128>(graph.supports[left]) * graph.supports[right];
    const unsigned __int128 preferential =
        static_cast<unsigned __int128>(left_degree) * right_degree;
    if (prevalence > std::numeric_limits<std::uint64_t>::max() ||
        preferential > std::numeric_limits<std::uint64_t>::max() ||
        jaccard_denominator > std::numeric_limits<std::uint32_t>::max()) {
        fail("candidate baseline overflowed its frozen integer domain");
    }
    return ScoreRow{
        pair_key,
        static_cast<std::uint64_t>(adamic_adar),
        static_cast<std::uint64_t>(resource_allocation),
        static_cast<std::uint64_t>(prevalence),
        static_cast<std::uint32_t>(common_neighbors),
        static_cast<std::uint32_t>(jaccard_denominator),
        static_cast<std::uint64_t>(preferential),
    };
}

bool rank_less(const RankItem& left, const RankItem& right) {
    if (left.score != right.score) {
        return left.score > right.score;
    }
    if (left.tie != right.tie) {
        return left.tie < right.tie;
    }
    return left.pair_key < right.pair_key;
}

std::vector<std::uint64_t> load_candidates(
    const fs::path& path,
    std::uint64_t expected_rows
) {
    auto candidates = read_vector<std::uint64_t>(path, "candidate stream");
    if (candidates.size() != expected_rows) {
        fail("candidate row count differs from frozen contract");
    }
    if (!std::is_sorted(candidates.begin(), candidates.end()) ||
        std::adjacent_find(candidates.begin(), candidates.end()) != candidates.end()) {
        fail("candidate stream is not strictly sorted and duplicate-free");
    }
    return candidates;
}

void score_all(const std::map<std::string, std::string>& args) {
    const auto expected_rows = parse_u64(required(args, "candidate-rows"), "candidate-rows");
    const fs::path scores_path(required(args, "scores"));
    const fs::path order_path(required(args, "primary-order"));
    if (fs::exists(scores_path) || fs::exists(order_path)) {
        fail("score output exists; audit it or select a new output directory");
    }
    const auto graph = load_graph(args);
    const auto candidates = load_candidates(required(args, "candidates"), expected_rows);
    fs::create_directories(scores_path.parent_path());
    std::ofstream output(scores_path, std::ios::binary | std::ios::out);
    if (!output) {
        fail("cannot create candidate score artifact");
    }
    std::vector<RankItem> rank_items;
    rank_items.reserve(candidates.size());
    for (std::size_t index = 0; index < candidates.size(); ++index) {
        const auto row = score_candidate(graph, candidates[index]);
        output.write(reinterpret_cast<const char*>(&row), sizeof(row));
        if (!output) {
            fail("failed writing candidate score artifact");
        }
        rank_items.push_back(RankItem{
            row.adamic_adar_q48,
            splitmix64(row.pair_key ^ kTieSalt),
            row.pair_key,
        });
        if ((index + 1) % 1000000U == 0) {
            std::cerr << "scored_rows=" << (index + 1) << "\n";
        }
    }
    output.flush();
    if (!output) {
        fail("failed flushing candidate score artifact");
    }
    output.close();
    std::sort(rank_items.begin(), rank_items.end(), rank_less);
    std::vector<std::uint64_t> order;
    order.reserve(rank_items.size());
    for (const auto& item : rank_items) {
        order.push_back(item.pair_key);
    }
    write_vector_new(order_path, order, "primary total order");
    std::cout << "scored_rows=" << candidates.size() << "\n";
    std::cout << "primary_order_rows=" << order.size() << "\n";
}

bool equal_score_row(const ScoreRow& left, const ScoreRow& right) {
    return left.pair_key == right.pair_key &&
        left.adamic_adar_q48 == right.adamic_adar_q48 &&
        left.resource_allocation_q48 == right.resource_allocation_q48 &&
        left.prevalence == right.prevalence &&
        left.common_neighbors == right.common_neighbors &&
        left.jaccard_denominator == right.jaccard_denominator &&
        left.preferential_attachment == right.preferential_attachment;
}

void audit_all(const std::map<std::string, std::string>& args) {
    const auto expected_rows = parse_u64(required(args, "candidate-rows"), "candidate-rows");
    const auto graph = load_graph(args);
    const auto candidates = load_candidates(required(args, "candidates"), expected_rows);
    const auto scores = read_vector<ScoreRow>(required(args, "scores"), "candidate scores");
    const auto order = read_vector<std::uint64_t>(required(args, "primary-order"), "primary order");
    if (scores.size() != candidates.size() || order.size() != candidates.size()) {
        fail("score or primary-order row count differs from candidate count");
    }
    std::vector<RankItem> expected_order;
    expected_order.reserve(candidates.size());
    for (std::size_t index = 0; index < candidates.size(); ++index) {
        const auto expected = score_candidate(graph, candidates[index]);
        if (!equal_score_row(scores[index], expected)) {
            fail("candidate score audit drift at row " + std::to_string(index));
        }
        expected_order.push_back(RankItem{
            expected.adamic_adar_q48,
            splitmix64(expected.pair_key ^ kTieSalt),
            expected.pair_key,
        });
    }
    std::sort(expected_order.begin(), expected_order.end(), rank_less);
    for (std::size_t index = 0; index < order.size(); ++index) {
        if (order[index] != expected_order[index].pair_key) {
            fail("primary total-order audit drift at row " + std::to_string(index));
        }
    }
    std::cout << "audited_score_rows=" << scores.size() << "\n";
    std::cout << "audited_primary_order_rows=" << order.size() << "\n";
}

void print_usage() {
    std::cerr
        << "usage:\n"
        << "  engine build-backbone --supports PATH --positive PATH --offsets PATH "
           "--neighbors PATH --nodes N --denominator N\n"
        << "  engine audit-backbone --supports PATH --positive PATH --offsets PATH "
           "--neighbors PATH --nodes N --denominator N\n"
        << "  engine score --supports PATH --candidates PATH --offsets PATH --neighbors PATH "
           "--weights PATH --scores PATH --primary-order PATH --nodes N --candidate-rows N\n"
        << "  engine audit --supports PATH --candidates PATH --offsets PATH --neighbors PATH "
           "--weights PATH --scores PATH --primary-order PATH --nodes N --candidate-rows N\n";
}

int main(int argc, char** argv) {
    try {
        require_little_endian();
        if (argc < 2) {
            print_usage();
            return 2;
        }
        const std::string command(argv[1]);
        const auto args = parse_args(argc, argv, 2);
        if (command == "build-backbone") {
            build_backbone(args);
        } else if (command == "audit-backbone") {
            audit_backbone(args);
        } else if (command == "score") {
            score_all(args);
        } else if (command == "audit") {
            audit_all(args);
        } else {
            print_usage();
            return 2;
        }
        return 0;
    } catch (const std::exception& error) {
        std::cerr << "metric-v1 engine: " << error.what() << "\n";
        return 1;
    }
}
