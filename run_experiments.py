#!/usr/bin/env python3
from dataclasses import replace
from typing import Iterable
from datetime import datetime as dt
from itertools import product

from lib.experiments import *


###################
#   HELPER CODE   #
###################

# GLOBALS
NUM_EXPERIMENTS_RUN: int = 0


def run_tests(exp_name: str, tests: Iterable[ExperimentConfig], /, dry_run=False):
    """
    Run a set of experiments.
    """
    global NUM_EXPERIMENTS_RUN
    tests = list(tests)
    count = len(tests)
    c_len = len(str(count))
    global_start = dt.now()
    for i, exp in enumerate(tests):
        start = dt.now()
        ts_str = start.strftime('%H:%M:%S')

        print_str = f'===     STARTING EXPERIMENT  [{NUM_EXPERIMENTS_RUN}] {exp_name} #{i+1:{c_len}}/{count}  at  {ts_str}     ==='

        print('='*len(print_str))
        print(print_str)
        print('='*len(print_str))

        if dry_run:
            print(f'EXPERIMENT: {exp.dbconf = }  {exp.pgconf = }')
        else:
            run_experiment(exp_name, exp)

        end = dt.now()
        ts_str = end.strftime('%H:%M:%S')
        elapsed = (end - start)
        e_min = elapsed.seconds // 60
        e_s = elapsed.total_seconds() % 60
        print_str = f'===     END EXPERIMENT  [{NUM_EXPERIMENTS_RUN}] {exp_name} #{i+1:{c_len}}/{count}  at  {ts_str}  ({e_min}m {e_s:.1f}s)     ==='

        print('='*len(print_str))
        print(print_str)
        print('='*len(print_str))
        print()

    global_end = dt.now()
    start_t_str = global_start.strftime('%A, %b %d %H:%M:%S')
    end_t_str = global_end.strftime('%A, %b %d %H:%M:%S')
    elapsed = global_end - global_start
    h = elapsed.seconds // (60*60)
    m = (elapsed.seconds % (60*60)) // 60
    s = elapsed.seconds % 60
    elapsed_str = f'{h}h {m}m {s}s'
    print_str = f'===     [{exp_name}] STARTED {start_t_str}, FINISHED {end_t_str}, TIME ELAPSED = {elapsed_str}     ==='
    
    print('-'*len(print_str))
    print(print_str)
    print('-'*len(print_str))
    print()

    NUM_EXPERIMENTS_RUN += 1


def branch_samples(brnch: PgBranch, ns: List[int]):
    # Some branches don't support the pbm_num_samples arg at all
    if not brnch.accepts_nsamples:
        return [None]
    # For ones that do, only include case with 1 sample for PBM2\
    # Multiple purely-random tests would be redundant
    elif brnch is BRANCH_PBM2:
        return ns
    else:
        return [n for n in ns if n > 1]


##############################
#   EXPERIMENT DEFINITIONS   #
##############################


def _TEST_test_script() -> Iterable[ExperimentConfig]:
    dbsetup = DbSetup(indexes='lineitem_brinonly', clustering='dates')
    bbconf = BBaseConfig(nworkers=2, workload=WORKLOAD_MICRO_COUNTS.with_multiplier(2))

    dbdata = DbData(WORKLOAD_MICRO_COUNTS.workload, sf=1)

    for shmem, brnch in product(['128MB', '1GB'], [BRANCH_POSTGRES_BASE, BRANCH_PBM2]):
        dbbin = DbBin(brnch)
        dbconf = DbConfig(dbbin, dbdata)

        for nsamples in branch_samples(brnch, [1, 10]):
            pgconf = RuntimePgConfig(shared_buffers=shmem, pbm_evict_num_samples=nsamples)

            yield ExperimentConfig(pgconf, dbconf, dbsetup, bbconf)


def test_micro_shared_memory(seed: int, parallelism=8) -> Iterable[ExperimentConfig]:
    dbsetup = DbSetup(indexes='lineitem_brinonly', clustering='dates')
    base_bbconf = BBaseConfig(nworkers=parallelism, workload=WORKLOAD_MICRO_COUNTS.with_multiplier(8), seed=seed)
    dbdata = DbData(WORKLOAD_MICRO_COUNTS.workload, sf=10)

    shmem_ops = ['256MB', '512MB', '1GB', '2GB', '4GB', '8GB', '16GB']

    # for shmem, prewarm, branch in product(shmem_ops, [True, False], POSTGRES_ALL_BRANCHES):
    for shmem, prewarm, branch in product(shmem_ops, [True], POSTGRES_ALL_BRANCHES):
        dbbin = DbBin(branch)
        dbconf = DbConfig(dbbin, dbdata)
        bbconf = replace(base_bbconf, prewarm=prewarm)

        for nsamples in branch_samples(branch, [1, 2, 5, 10, 20]):
            pgconf = RuntimePgConfig(shared_buffers=shmem, pbm_evict_num_samples=nsamples)

            yield ExperimentConfig(pgconf, dbconf, dbsetup, bbconf)


def test_micro_parallelism_constant_nqueries() -> Iterable[ExperimentConfig]:
    dbsetup = DbSetup(indexes='lineitem_brinonly', clustering='dates')
    dbdata = DbData(WORKLOAD_MICRO_COUNTS.workload, sf=10)

    shmem = '2GB'
    total_queries = 2**6
    parallel_ops = [1, 2, 4, 8, 16, 32]
    syncscan_ops = ['on', 'off']
    nsamples = [1, 2, 5, 10, 20]

    for nworkers, branch in product(parallel_ops, POSTGRES_ALL_BRANCHES):
        cm = total_queries // nworkers

        dbbin = DbBin(branch)
        dbconf = DbConfig(dbbin, dbdata)
        bbconf = BBaseConfig(nworkers=nworkers, workload=WORKLOAD_MICRO_COUNTS.with_multiplier(cm))

        for nsamples, syncscans in product(branch_samples(branch, nsamples), syncscan_ops):
            pgconf = RuntimePgConfig(shared_buffers=shmem,
                                     pbm_evict_num_samples=nsamples,
                                     synchronize_seqscans=syncscans)

            yield ExperimentConfig(pgconf, dbconf, dbsetup, bbconf)


def test_micro_parallelism(seed: Optional[int], selectivity: Optional[float], *,
                           cm=8, parallel_ops: List[int] = None, nsamples: List[int] = None) \
        -> Iterable[ExperimentConfig]:
    dbsetup = DbSetup(indexes='lineitem_brinonly', clustering='dates')
    dbdata = DbData(WORKLOAD_MICRO_COUNTS.workload, sf=10)

    shmem = '2GB'
    if parallel_ops is None:
        parallel_ops = [1, 2, 4, 6, 8, 12, 16, 24, 32]
    if nsamples is None:
        nsamples = [1, 2, 5, 10, 20]
    if seed is None:
        seed = 12345  # default seed

    for nworkers, branch in product(parallel_ops, POSTGRES_ALL_BRANCHES):
        dbbin = DbBin(branch)
        dbconf = DbConfig(dbbin, dbdata)
        bbconf = BBaseConfig(nworkers=nworkers, seed=seed,
                             workload=WORKLOAD_MICRO_COUNTS.with_multiplier(cm).with_selectivity(selectivity))

        for ns in branch_samples(branch, nsamples):
            pgconf = RuntimePgConfig(shared_buffers=shmem,
                                     pbm_evict_num_samples=ns,
                                     synchronize_seqscans='on')

            yield ExperimentConfig(pgconf, dbconf, dbsetup, bbconf)


def test_micro_parallelism_with_selectivity(selectivity: float) -> Iterable[ExperimentConfig]:
    return test_micro_parallelism(None, selectivity)


def test_micro_parallelism_same_stream_count(seed: int, parallel_ops=None) -> Iterable[ExperimentConfig]:
    return test_micro_parallelism(seed, None, cm=6, parallel_ops=parallel_ops, nsamples=[1, 5, 10])


def rerun_failed(done_count: int, e_str: str, exp: Iterable[ExperimentConfig], dry=True):
    not_tried = list(exp)[done_count:]
    if dry:
        print("First retry:")
        print(not_tried[0].dbconf)
        print(not_tried[0].pgconf)
    else:
        run_tests(e_str, not_tried)


if __name__ == '__main__':
    # Run actual experiments
    # run_tests('test_scripts_buffer_sizes_2', _TEST_test_script())

    # Real tests
    # run_tests('buffer_sizes_3', test_micro_shared_memory())
    # run_tests('parallelism_3', test_micro_parallelism())
    # run_tests('parallelism_same_nqueries_1', test_micro_parallelism_same_stream_size())

    # run_tests('parallelism_sel20_2', test_micro_parallelism_same_stream_size(0.2))
    # run_tests('parallelism_sel40_2', test_micro_parallelism_same_stream_size(0.4))
    # run_tests('parallelism_sel60_2', test_micro_parallelism_same_stream_size(0.6))
    # run_tests('parallelism_sel80_2', test_micro_parallelism_same_stream_size(0.8))
    #
    # for s in [16312, 22289, 16987, 6262, 32495, 5786]:
    #     run_tests('test_weird_spike_3', test_WHY_SPIKE(s))

    # for s in [29020, 29848, 15858]:
    #     run_tests('buffer_sizes_4', test_micro_shared_memory(s))

    # for s in [29020, 29848, 15858]:
    #     run_tests('buffer_sizes_p16_1', test_micro_shared_memory(s, parallelism=16))

    # re-run part which failed...
    # rerun_failed(43, 'buffer_sizes_p16_1', test_micro_shared_memory(15858, parallelism=16))

    for s in [21473, 25796, 11251, 28834, 16400]:
        run_tests('parallelism_sel30_1', test_micro_parallelism(s, 0.3, cm=6, nsamples=[1, 5, 10]))

    ...