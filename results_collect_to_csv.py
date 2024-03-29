#!/usr/bin/env -S python3

import os
import json
import csv
import sys
from pathlib import Path
from typing import Optional

import pandas as pd

from lib.config import *

#################
#  CSV columns  #
#################

statio_main_cols = ['heap_blks_hit', 'heap_blks_read', 'idx_blks_hit', 'idx_blks_read']
statio_toast_cols = ['tidx_blks_hit', 'tidx_blks_read', 'toast_blks_hit', 'toast_blks_read']
# Docs for these columns: https://www.postgresql.org/docs/current/monitoring-stats.html#PG-STAT-DATABASE-VIEW
dbstat_cols = {c: 'db_' + c for c in ['active_time', 'blk_read_time', 'blks_hit', 'blks_read']}
bbase_latency_cols = [
    'Average Latency (microseconds)',
    'Maximum Latency (microseconds)',
    '99th Percentile Latency (microseconds)',
    '95th Percentile Latency (microseconds)',
    '90th Percentile Latency (microseconds)',
    '75th Percentile Latency (microseconds)',
    'Median Latency (microseconds)',
    '25th Percentile Latency (microseconds)',
    'Minimum Latency (microseconds)',
]

csv_cols = [
    # configuration from directory information:
    'experiment', 'dir', 'branch', 'block size',
    # configuration from configuration json file
    'block_group_size', 'workload', 'scalefactor', 'selectivity', 'clustering', 'indexes', 'shared_buffers',
    'work_mem', 'synchronize_seqscans', 'pbm_evict_num_samples', 'pbm_bg_naest_max_age', 'pbm_evict_num_victims',
    'pbm_evict_use_freq', 'pbm_evict_use_idx_scan', 'pbm_idx_scan_num_counts', 'pbm_lru_if_not_requested',
    'parallelism', 'time',
    'count_multiplier', 'prewarm', 'seed', 'query_order_randomized',
    # from OS IO statis
    *SYSBLOCKSTAT_COLS,
    # from benchbase summary:
    'Throughput (requests/second)', 'Goodput (requests/second)', 'Benchmark Runtime (nanoseconds)',
    # latency from benchbase summary:
    *bbase_latency_cols,
    # stats from metrics
    'average_stream_s', 'max_stream_s',
    *statio_main_cols,
    *dbstat_cols.values(),
    *('lineitem_' + col for col in statio_main_cols),
    'hit_rate', 'lineitem_hit_rate',
    'data_read_gb', 'data_processed_gb'
]


##########
#  CODE  #
##########


def read_config(config_dir: str, file: str) -> Optional[dict]:
    """Read and parse a file in the results directory, or return `None` if it isn't valid."""
    path = RESULTS_ROOT / config_dir / CONFIG_FILE_NAME
    try:
        with open(path, 'r') as f:
            contents = f.read()

        if not contents:
            return None
        return json.JSONDecoder().decode(contents)

    except (FileNotFoundError, NotADirectoryError):
        return None


def decode_iostats(iostats_file: Path, decoder: json.JSONDecoder) -> dict:
    try:
        with open(iostats_file, 'r') as stats_file:
            decoded = decoder.decode(stats_file.read())

        if 'after' in decoded:
            before = decoded.get('before') or decoded.get('before:')  # make up for silly typo in test scripts...
            after = decoded['after']

            iostats = {k: (int(after[k]) - int(before[k])) for k in before.keys()}

        else:
            # only reads and writes
            iostats = decoded
    except FileNotFoundError:
        iostats = {}

    return iostats


def io_metrics_map(metrics: dict, blk_sz: int) -> dict:
    """Parse the `metrics.json` json file produced by benchbase and extract io metrics."""
    pg_statio_user_tables = metrics['pg_statio_user_tables']
    pg_stat_database = metrics['pg_stat_database']

    dbstat_df = pd.DataFrame(pg_stat_database)
    for c in dbstat_cols.keys():
        dbstat_df[c] = pd.to_numeric(dbstat_df[c])
    dbstat_df = dbstat_df.rename(columns=dbstat_cols)

    # Docs for these cols: https://www.postgresql.org/docs/current/monitoring-stats.html#PG-STAT-DATABASE-VIEW
    metrics_totals = {**dbstat_df[dbstat_cols.values()].sum()}

    for col in statio_main_cols:
        metrics_totals[col] = sum(int(r[col] or 0) for r in pg_statio_user_tables)

    # We're ignoring stats for toast tables assuming they are 0. Check that assumption holds.
    for col in statio_toast_cols:
        s = sum(int(r[col] or 0) for r in pg_statio_user_tables)
        if s > 0:
            print(f'WARNING: found non-zero toast values in column {col}!')

    # Compute stats for just lineitem
    for col in statio_main_cols:
        metrics_totals['lineitem_' + col] = sum(int(r[col] or 0) for r in pg_statio_user_tables if r['relname'] == 'lineitem')

    # Compute hit-rate. (arguably not necessary, can post-process in excel too)
    total_hits = metrics_totals['heap_blks_hit'] + metrics_totals['idx_blks_hit']
    total_reads = metrics_totals['heap_blks_read'] + metrics_totals['idx_blks_read']
    lineitem_total_hits = metrics_totals['lineitem_heap_blks_hit'] + metrics_totals['lineitem_idx_blks_hit']
    lineitem_total_reads = metrics_totals['lineitem_heap_blks_read'] + metrics_totals['lineitem_idx_blks_read']

    metrics_totals['hit_rate'] = total_hits / (total_hits + total_reads)

    if lineitem_total_hits > 0:
        metrics_totals['lineitem_hit_rate'] = lineitem_total_hits / (lineitem_total_hits + lineitem_total_reads)
    else:
        # make sure it has a value so this column has float datatype in pandas
        metrics_totals['lineitem_hit_rate'] = 0.
    # Compute amount of data read/processed
    # blk_sz is in KiB, not bytes, so conversion rate is 2^20 to get to GiB
    metrics_totals['data_read_gb'] = total_reads * blk_sz / (2**20)
    metrics_totals['data_processed_gb'] = (total_reads + total_hits) * blk_sz / (2**20)

    return metrics_totals


def collect_results_to_csv(res_dir: Path, csv_out: Path, sort_rows=True):
    decoder = json.JSONDecoder()
    json_decode = decoder.decode

    out = open(csv_out, 'w')
    writer = csv.DictWriter(out, csv_cols, extrasaction='ignore')
    writer.writeheader()

    rows = []

    # Folders to ignore results from, usually because something went wrong during the test (e.g. network issues...) but the test still completed
    # These experiments have been re-run separately
    ignore_dirs = {
        'TPCH_2023-06-19_10-16-21',  # strangely completed in half the expected time, but without errors... no cgroup maybe?
        'TPCH_2023-06-19_11-02-50',  # ^ similar
        'TPCH_2023-06-13_15-45',  # weirdly low hit-rate compared to other results with the same code... no idea why
        'TPCH_2023-08-16_10-46-45',  # unexpectedly low runtime for the results, rerunning it seems to match the other results (replaced by TPCH_2023-08-17_14-14-26)
    }

    # Process everythign in the results directory
    conf_dir: str
    for conf_dir in os.listdir(res_dir):
        if conf_dir in ignore_dirs:
            print(f'Results directory {conf_dir} marked as to-be-ignored, skipping...')
            continue

        # read config file if it is there
        config = read_config(conf_dir, CONFIG_FILE_NAME)

        if config is None:
            print(f'{conf_dir}: No config, skipping...')
            continue

        # each directory is a different run of benchbase
        subdirs = [subdir for subdir in os.listdir(res_dir / conf_dir) if subdir not in NON_DIR_RESULTS]
        pgconfigs = [subdir.split('_blksz') for subdir in subdirs]
        try:
            pgconfigs = [(s[0], int(s[1])) for s in pgconfigs]
        except (ValueError, IndexError) as e:
            print(f'ERROR: some subdirectory did not match the naming scheme, don\'t know how to parse {conf_dir}!')
            print(f'    {e!r}')
        if len(pgconfigs) > 1:
            print(f'WARNING: multiple subdirectories in {conf_dir}!')

        try:
            for brnch, blk_sz in pgconfigs:
                subdir = res_dir / conf_dir / f'{brnch}_blksz{blk_sz}'

                # Process benchbase output:
                with open(subdir / 'metrics.json', 'r') as metrics_file:
                    metrics = json_decode(metrics_file.read())
                with open(subdir / 'summary.json', 'r') as summary_file:
                    summary = json_decode(summary_file.read())
                try:
                    with open(subdir / 'stream_times.json', 'r') as st_file:
                        stream_times = json_decode(st_file.read())
                except FileNotFoundError:
                    stream_times = []

                iostats = decode_iostats(subdir / IOSTATS_FILE, decoder)
                io_metrics = io_metrics_map(metrics, blk_sz)

                # generate row in the processed results:
                row = {
                    'dir': conf_dir,
                    'branch': brnch,
                    'block size': blk_sz,
                    # compute average stream time (stream times are microseconds)
                    'average_stream_s': sum(stream_times) / len(stream_times) / (10**6) if stream_times else None,
                    'max_stream_s': max(stream_times) / (10**6) if stream_times else None,
                    **config,
                    **iostats,
                    **summary,
                    **summary['Latency Distribution'],
                    **io_metrics,
                }

                rows.append(row)

                if not sort_rows:
                    writer.writerow(row)

                if stream_times and min(stream_times) < 0:
                    print(f'WARNING: negative stream times for {conf_dir}! e={config["experiment"]}')

        except FileNotFoundError as e:
            print(f'ERROR: could not find the benchbase files for {conf_dir}!')
            print(f'    {e!r}')

    if sort_rows:
        print('SORTING')
        rows.sort(key = lambda r: r['dir'])
        print('WRITING')
        writer.writerows(rows)

    out.close()


if __name__ == '__main__':
    res_dir = RESULTS_ROOT
    csv_out = COLLECTED_RESULTS_CSV
    if len(sys.argv) > 2:
        res_dir = Path(sys.argv[1])
        csv_out = Path(sys.argv[2])
    collect_results_to_csv(res_dir, csv_out)
