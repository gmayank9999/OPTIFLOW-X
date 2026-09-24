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
    write("lcs", "in3.txt", f"{rand_str(6000)} {rand_str(6000)}\n")


def gen_substring_naive() -> None:
    rng = random.Random(4004)
    alphabet = "ABCD"

    def rand_str(n: int) -> str:
        return "".join(rng.choice(alphabet) for _ in range(n))

    write("substring_naive", "in1.txt", "A A\n")
    write("substring_naive", "in2.txt", f"{rand_str(33)} {rand_str(5)}\n")
    write("substring_naive", "in3.txt", f"{rand_str(3000000)} {rand_str(10)}\n")


if __name__ == "__main__":
    gen_bubble_sort()
    gen_floyd_warshall()
    gen_lcs()
    gen_substring_naive()
    print("generated inputs for bubble_sort, floyd_warshall, lcs, substring_naive")
