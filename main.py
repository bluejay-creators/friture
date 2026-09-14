#!/usr/bin/env python

import os

# The pitch tracker does ~50 small matrix products per second; OpenBLAS's
# default thread pool (one worker per core) spins on every one of them and
# was measured at 11+ cores of CPU for nothing. One thread is faster here.
# Must be set before numpy is imported anywhere.
for _var in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS"):
    os.environ.setdefault(_var, "1")

from friture.analyzer import main

if __name__ == '__main__':
    main()
