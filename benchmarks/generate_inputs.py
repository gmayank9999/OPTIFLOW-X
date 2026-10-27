"""One-off generator for the random-data benchmark inputs.

Run once when a program's input shape changes. Uses a fixed seed so the
generated files are reproducible; the files themselves are committed and
are not regenerated automatically.
"""

import pathlib
import random

ROOT = pathlib.Path(__file__).parent


def write(program: str, name: str, content: str) -> None:
    path = ROOT / program / "inputs" / name
    path.write_text(content)


def gen_bubble_sort() -> None:
    rng = random.Random(1001)
    write("bubble_sort", "in1.txt", "1\n5\n")
    small = [rng.randint(-1000, 1000) for _ in range(33)]
    write("bubble_sort", "in2.txt", f"33\n{' '.join(map(str, small))}\n")
    bench = [rng.randint(-1_000_000, 1_000_000) for _ in range(20000)]
    write("bubble_sort", "in3.txt", f"20000\n{' '.join(map(str, bench))}\n")


def gen_floyd_warshall() -> None:
    rng = random.Random(2002)

    def matrix(n: int) -> str:
        rows = []
        for i in range(n):
            row = []
            for j in range(n):
                if i == j:
                    row.append(0)
                elif rng.random() < 0.3:
                    row.append(100000)
                else:
                    row.append(rng.randint(1, 50))
            rows.append(" ".join(map(str, row)))
        return f"{n}\n" + "\n".join(rows) + "\n"

    write("floyd_warshall", "in1.txt", matrix(1))
    write("floyd_warshall", "in2.txt", matrix(33))
    write("floyd_warshall", "in3.txt", matrix(900))


def gen_lcs() -> None:
    rng = random.Random(3003)
    alphabet = "ACGT"

    def rand_str(n: int) -> str:
        return "".join(rng.choice(alphabet) for _ in range(n))

    write("lcs", "in1.txt", "A A\n")
    write("lcs", "in2.txt", f"{rand_str(33)} {rand_str(29)}\n")
    write("lcs", "in3.txt", f"{rand_str(8000)} {rand_str(8000)}\n")


def gen_substring_naive() -> None:
    rng = random.Random(4004)
    alphabet = "ABCD"

    def rand_str(n: int) -> str:
        return "".join(rng.choice(alphabet) for _ in range(n))

    write("substring_naive", "in1.txt", "A A\n")
    write("substring_naive", "in2.txt", f"{rand_str(33)} {rand_str(5)}\n")
    write("substring_naive", "in3.txt", f"{rand_str(3000000)} {rand_str(10)}\n")


def _random_array_program(name: str, seed: int, bench_n: int, lo: int = -1_000_000, hi: int = 1_000_000) -> None:
    rng = random.Random(seed)
    write(name, "in1.txt", "1\n5\n")
    small = [rng.randint(lo, hi) for _ in range(33)]
    write(name, "in2.txt", f"33\n{' '.join(map(str, small))}\n")
    bench = [rng.randint(lo, hi) for _ in range(bench_n)]
    write(name, "in3.txt", f"{bench_n}\n{' '.join(map(str, bench))}\n")


def gen_insertion_sort() -> None:
    _random_array_program("insertion_sort", 5005, bench_n=72000)


def gen_mergesort_mallocs() -> None:
    rng = random.Random(6006)
    write("mergesort_mallocs", "in1.txt", "0\n\n")
    small = [rng.randint(-1000, 1000) for _ in range(33)]
    write("mergesort_mallocs", "in2.txt", f"33\n{' '.join(map(str, small))}\n")
    bench = [rng.randint(-1_000_000, 1_000_000) for _ in range(2000000)]
    write("mergesort_mallocs", "in3.txt", f"2000000\n{' '.join(map(str, bench))}\n")


def gen_count_inversions() -> None:
    _random_array_program("count_inversions", 7007, bench_n=27000)


def gen_selection_sort() -> None:
    _random_array_program("selection_sort", 8008, bench_n=30000)


def gen_quicksort_bad_pivot() -> None:
    # Deliberately sorted / reverse-sorted so the first-element pivot hits
    # its O(n^2) worst case instead of the typical O(n log n) case.
    write("quicksort_bad_pivot", "in1.txt", "1\n5\n")
    write("quicksort_bad_pivot", "in2.txt", "33\n" + " ".join(str(i) for i in range(33)) + "\n")
    n = 60000
    write("quicksort_bad_pivot", "in3.txt", f"{n}\n" + " ".join(str(i) for i in range(n, 0, -1)) + "\n")


def gen_linear_search_many() -> None:
    rng = random.Random(9009)

    def gen(name: str, n: int, q: int) -> str:
        arr = [rng.randint(0, n * 2) for _ in range(n)]
        queries = [arr[rng.randrange(n)] if rng.random() < 0.5 else rng.randint(0, n * 2) for _ in range(q)]
        return f"{n} {q}\n{' '.join(map(str, arr))}\n{' '.join(map(str, queries))}\n"

    write("linear_search_many", "in1.txt", gen("linear_search_many", 1, 1))
    write("linear_search_many", "in2.txt", gen("linear_search_many", 33, 10))
    write("linear_search_many", "in3.txt", gen("linear_search_many", 20000, 80000))


def gen_binary_search_resort() -> None:
    rng = random.Random(10010)

    def gen(n: int, q: int) -> str:
        arr = [rng.randint(0, n * 2) for _ in range(n)]
        queries = [arr[rng.randrange(n)] if n and rng.random() < 0.5 else rng.randint(0, n * 2) for _ in range(q)]
        return f"{n} {q}\n{' '.join(map(str, arr))}\n{' '.join(map(str, queries))}\n"

    write("binary_search_resort", "in1.txt", gen(1, 1))
    write("binary_search_resort", "in2.txt", gen(33, 10))
    write("binary_search_resort", "in3.txt", gen(1500, 1200))


def _random_adjacency(rng: random.Random, n: int, edge_prob: float, directed: bool = True) -> list[list[int]]:
    adj = [[0] * n for _ in range(n)]
    for i in range(n):
        for j in range(n):
            if i == j:
                continue
            if directed:
                if rng.random() < edge_prob:
                    adj[i][j] = 1
            elif j > i and rng.random() < edge_prob:
                adj[i][j] = 1
                adj[j][i] = 1
    return adj


def _write_adjacency(program: str, name: str, n: int, src_or_extra: str, adj: list[list[int]]) -> None:
    rows = "\n".join(" ".join(map(str, row)) for row in adj)
    header = f"{n} {src_or_extra}".strip()
    write(program, name, f"{header}\n{rows}\n")


def gen_bfs_matrix() -> None:
    rng = random.Random(11011)
    write("bfs_matrix", "in1.txt", "1 0\n0\n")
    _write_adjacency("bfs_matrix", "in2.txt", 33, "0", _random_adjacency(rng, 33, 0.3, directed=False))
    _write_adjacency("bfs_matrix", "in3.txt", 2500, "0", _random_adjacency(rng, 2500, 0.01, directed=False))


def gen_dijkstra_v2() -> None:
    rng = random.Random(12012)

    def weighted(n: int, edge_prob: float) -> list[list[int]]:
        adj = _random_adjacency(rng, n, edge_prob, directed=False)
        for i in range(n):
            for j in range(n):
                if adj[i][j]:
                    adj[i][j] = rng.randint(1, 50)
        return adj

    write("dijkstra_v2", "in1.txt", "1 0\n0\n")
    _write_adjacency("dijkstra_v2", "in2.txt", 33, "0", weighted(33, 0.3))
    _write_adjacency("dijkstra_v2", "in3.txt", 2200, "0", weighted(2200, 0.01))


def gen_dfs_recursive() -> None:
    rng = random.Random(13013)
    write("dfs_recursive", "in1.txt", "1 0\n0\n")
    _write_adjacency("dfs_recursive", "in2.txt", 33, "0", _random_adjacency(rng, 33, 0.3, directed=False))
    _write_adjacency("dfs_recursive", "in3.txt", 2200, "0", _random_adjacency(rng, 2200, 0.05, directed=False))


def gen_bellman_ford() -> None:
    rng = random.Random(14014)

    def weighted(n: int, edge_prob: float) -> list[list[int]]:
        adj = _random_adjacency(rng, n, edge_prob, directed=True)
        for i in range(n):
            for j in range(n):
                if adj[i][j]:
                    adj[i][j] = rng.randint(1, 30)
        return adj

    write("bellman_ford", "in1.txt", "1 0\n0\n")
    _write_adjacency("bellman_ford", "in2.txt", 33, "0", weighted(33, 0.3))
    _write_adjacency("bellman_ford", "in3.txt", 700, "0", weighted(700, 0.05))


def gen_connected_components() -> None:
    rng = random.Random(15015)
    write("connected_components", "in1.txt", "1\n0\n")
    _write_adjacency("connected_components", "in2.txt", 33, "", _random_adjacency(rng, 33, 0.1, directed=False))
    _write_adjacency("connected_components", "in3.txt", 2500, "", _random_adjacency(rng, 2500, 0.002, directed=False))


def gen_pagerank_iters() -> None:
    rng = random.Random(16016)
    write("pagerank_iters", "in1.txt", "1 1\n0\n")
    _write_adjacency("pagerank_iters", "in2.txt", 33, "20", _random_adjacency(rng, 33, 0.3, directed=True))
    _write_adjacency("pagerank_iters", "in3.txt", 550, "900", _random_adjacency(rng, 550, 0.05, directed=True))


def gen_triangle_counting() -> None:
    rng = random.Random(17017)
    write("triangle_counting", "in1.txt", "1\n0\n")
    _write_adjacency("triangle_counting", "in2.txt", 33, "", _random_adjacency(rng, 33, 0.3, directed=False))
    _write_adjacency("triangle_counting", "in3.txt", 1500, "", _random_adjacency(rng, 1500, 0.05, directed=False))


def gen_edit_distance() -> None:
    rng = random.Random(18018)
    alphabet = "ABCDE"

    def rand_str(n: int) -> str:
        return "".join(rng.choice(alphabet) for _ in range(n))

    write("edit_distance", "in1.txt", "A A\n")
    write("edit_distance", "in2.txt", f"{rand_str(33)} {rand_str(29)}\n")
    write("edit_distance", "in3.txt", f"{rand_str(8000)} {rand_str(8000)}\n")


def gen_knapsack01() -> None:
    rng = random.Random(19019)

    def gen(n: int, w_cap: int) -> str:
        lines = [f"{n} {w_cap}"]
        for _ in range(n):
            lines.append(f"{rng.randint(1, 50)} {rng.randint(1, 100)}")
        return "\n".join(lines) + "\n"

    write("knapsack01", "in1.txt", gen(1, 10))
    write("knapsack01", "in2.txt", gen(33, 200))
    write("knapsack01", "in3.txt", gen(2000, 36000))


def gen_lis_on2() -> None:
    _random_array_program("lis_on2", 20020, bench_n=25000, lo=-100000, hi=100000)


def gen_matrix_chain() -> None:
    rng = random.Random(21021)
    n = 1300
    dims = [rng.randint(2, 100) for _ in range(n + 1)]
    write("matrix_chain", "in3.txt", f"{n}\n{' '.join(map(str, dims))}\n")


def gen_palindrome_count() -> None:
    rng = random.Random(22022)

    def rand_str(n: int, alphabet: str) -> str:
        return "".join(rng.choice(alphabet) for _ in range(n))

    write("palindrome_count", "in1.txt", "A\n")
    write("palindrome_count", "in2.txt", rand_str(33, "AB") + "\n")
    # single-character alphabet: every substring is a palindrome, so
    # is_palindrome() always runs to completion instead of exiting on the
    # first mismatch -- this is what actually makes it O(n^3).
    write("palindrome_count", "in3.txt", "A" * 3000 + "\n")


def gen_word_freq_linear() -> None:
    rng = random.Random(23023)
    vocab = [f"word{i}" for i in range(600)]

    def gen(n: int) -> str:
        words = [rng.choice(vocab) for _ in range(n)]
        return f"{n}\n{' '.join(words)}\n"

    write("word_freq_linear", "in1.txt", gen(1))
    write("word_freq_linear", "in2.txt", gen(33))
    write("word_freq_linear", "in3.txt", gen(400000))


def gen_string_reversal_many() -> None:
    rng = random.Random(24024)
    alphabet = "abcdefghijklmnopqrstuvwxyz"

    def rand_word(n: int) -> str:
        return "".join(rng.choice(alphabet) for _ in range(n))

    def gen(n: int, reps: int) -> str:
        words = [rand_word(rng.randint(3, 20)) for _ in range(n)]
        return f"{n} {reps}\n{' '.join(words)}\n"

    write("string_reversal_many", "in1.txt", gen(1, 1))
    write("string_reversal_many", "in2.txt", gen(33, 5))
    write("string_reversal_many", "in3.txt", gen(15000, 3200))


def gen_run_length_encoding() -> None:
    rng = random.Random(25025)
    alphabet = "AB"

    def rand_str(n: int) -> str:
        return "".join(rng.choice(alphabet) for _ in range(n))

    write("run_length_encoding", "in1.txt", "A\n")
    write("run_length_encoding", "in2.txt", rand_str(33) + "\n")
    write("run_length_encoding", "in3.txt", rand_str(60000) + "\n")


if __name__ == "__main__":
    gen_bubble_sort()
    gen_floyd_warshall()
    gen_lcs()
    gen_substring_naive()
    gen_insertion_sort()
    gen_mergesort_mallocs()
    gen_count_inversions()
    gen_selection_sort()
    gen_quicksort_bad_pivot()
    gen_linear_search_many()
    gen_binary_search_resort()
    gen_bfs_matrix()
    gen_dijkstra_v2()
    gen_dfs_recursive()
    gen_bellman_ford()
    gen_connected_components()
    gen_pagerank_iters()
    gen_triangle_counting()
    gen_edit_distance()
    gen_knapsack01()
    gen_lis_on2()
    gen_matrix_chain()
    gen_palindrome_count()
    gen_word_freq_linear()
    gen_string_reversal_many()
    gen_run_length_encoding()
    print("generated inputs for all random-data benchmark programs")
