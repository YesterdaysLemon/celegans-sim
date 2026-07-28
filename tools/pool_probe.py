"""Does pooled() lose jobs when there are more of them than workers?"""
import time
from tools.assays import pooled


def slow(i):
    time.sleep(2.0)
    return i


def main():
    for n in (8, 12, 20, 30):
        t0 = time.perf_counter()
        out = pooled(slow, list(range(n)), timeout=120)
        print("  %2d jobs -> %2d returned in %4.1f s   %s"
              % (n, len(out), time.perf_counter() - t0,
                 "OK" if len(out) == n else "*** LOST %d ***" % (n - len(out))))


if __name__ == "__main__":
    main()
