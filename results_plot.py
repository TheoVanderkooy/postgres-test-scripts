#!/usr/bin/env -S python3 -i
import pandas as pd
from typing import Union, Iterable, Optional
import matplotlib.pyplot as plt
import matplotlib

from lib.config import *

# Configure matplotlib
matplotlib.use('TkAgg')


# rename certain columns to make them easier to work with
rename_cols = {
    'Average Latency (microseconds)': 'avg_latency',
    'Throughput (requests/second)': 'throughput',
}


def to_mb(ms: str):
    """Convert memory size in postgres config format to # of MB"""
    units = ms[-2:].lower()

    num = float(ms[:-2]) * {
        'mb': 2**0,
        'gb': 2**10,
    }[units]

    return int(num)


def format_str_or_iterable(to_fmt: Union[str, Iterable[str]]) -> str:
    """For a list/sequence of strings, format as comma-separated string"""
    if type(to_fmt) == str:
        return to_fmt

    return ', '.join(str(s) for s in to_fmt)


def plot_exp(df: pd.DataFrame, exp: str, *, ax: Optional[plt.Axes] = None,
             x, xsort=False, xlabels=None, logx=False, xlabel=None,
             y, ylabel=None, ybound=None, avg_y_values=False,
             group: Union[str, Iterable[str]] = ('branch', 'pbm_evict_num_samples'),
             title=None):
    """Plot an experiment."""
    df_exp = df[df['experiment'] == exp]

    if ax is None:
        f, ax = plt.subplots(num=title)

    if type(group) is not str:
        group = list(group)

    for grp, df_plot in df_exp.groupby(group):
        # sort x values if requested
        if type(xsort) == bool and xsort:
            xsort = x
        else:
            xsort = None

        # average the y-values for the same x-value first if requested
        if avg_y_values:
            if xsort is not None and xsort is not x:
                cols = [x, xsort, y]
            else:
                cols = [x, y]

            # print(df_plot[cols])
            df_plot = df_plot[cols].groupby(x).mean().reset_index()
            # print(df_plot)

        if xsort is not None:
            df_plot = df_plot.sort_values(by=xsort)

        # whether to use log-scale for x or not
        if logx:
            plotfn = lambda *a, **kwa: ax.semilogx(*a, base=2, **kwa)
        else:
            plotfn = ax.plot

        # actually plot the current group
        plotfn(df_plot[x], df_plot[y], label=format_str_or_iterable(grp))

    ax.minorticks_off()
    if ybound is not None:
        ax.set_ybound(*ybound)
    if xlabels is not None:
        ax.set_xticks(df_plot[x], labels=df_plot[xlabels])

    ax.set_xlabel(xlabel or str(x))
    ax.set_ylabel(ylabel or y)
    ax.legend(title=format_str_or_iterable(group))
    ax.set_title(str(title))

    return ax


def main():
    # Read in the data, converting certain column names
    df = pd.read_csv(COLLECTED_RESULTS_CSV, keep_default_na=False).rename(columns=rename_cols)

    # Add some columns for convenience

    # Convert shared buffers config to numbers for plotting
    df['shmem_mb'] = df['shared_buffers'].map(to_mb)
    df['data_per_stream'] = df.data_read_gb / df.parallelism

    # Output results
    print('================================================================================')
    print('== Post-process interactive prompt:')
    print('==   `df` contains a dataframe of the results')
    print('==   `plt` is `matplotlib.pyplot`')
    print('================================================================================')

    print(f'Generating plots...')

    # # plot some experiments
    plots = [
        # plot_exp (df, 'test_reset_stats_shmem',
        #                  x='shmem_mb', xsort=True, xlabels='shared_buffers', logx=True, xlabel='shared memory',
        #                  y='hit_rate', ylabel='hit rate', ybound=(0,1),
        #                  title='Hit-rate vs shared buffer size'),
        # plot_exp(df, 'test_shmem_prewarm_2', group=['branch', 'prewarm'],
        #                  x='shmem_mb', xsort=True, xlabels='shared_buffers', logx=True, xlabel='shared memory',
        #                  y='hit_rate', ylabel='hit rate', ybound=(0,1),
        #                  title='Hit-rate vs shared buffer size with and without pre-warming'),
        # plot_exp(df, 'test_sf100', group=['branch', 'prewarm'],
        #                  x='shmem_mb', xsort=True, xlabels='shared_buffers', logx=True, xlabel='shared memory',
        #                  y='hit_rate', ylabel='hit rate', ybound=(0,1),
        #                  title='SF 100 Hit-rate vs shared buffer size'),

        # plot_exp(df, 'test_scripts_buffer_sizes', group=['branch', 'pbm_evict_num_samples'],
        #                  x='shmem_mb', xsort=True, xlabels='shared_buffers', logx=True, xlabel='shared memory',
        #                  y='hit_rate', ylabel='hit rate', ybound=(0,1),
        #                  title='Hit-rate vs shared buffer'),

        # microbenchmarks varying the buffer size, with and without prewarm
        # plot_exp(df[df.prewarm == True], 'buffer_sizes_3', group=['branch', 'pbm_evict_num_samples'],
        #          x='shmem_mb', xsort=True, xlabels='shared_buffers', logx=True, xlabel='shared memory',
        #          y='hit_rate', ylabel='hit rate', ybound=(0,1),
        #          title='Hit-rate vs shared buffer size with pre-warming'),
        # plot_exp(df[df.prewarm == False], 'buffer_sizes_3', group=['branch', 'pbm_evict_num_samples'],
        #          x='shmem_mb', xsort=True, xlabels='shared_buffers', logx=True, xlabel='shared memory',
        #          y='hit_rate', ylabel='hit rate', ybound=(0,1),
        #          title='Hit-rate vs shared buffer size without pre-warming'),

        # microbenchmaks varying parallelism with and without syncscans
        # plot_exp(df[df.synchronize_seqscans == 'on'], 'parallelism_3', group=['branch', 'pbm_evict_num_samples'],
        #          x='parallelism', xsort=True, xlabel='Parallelism',
        #          y='hit_rate', ylabel='hit rate', ybound=(0,1),
        #          title='Hit-rate vs parallelism with syncscans'),
        # # plot_exp(df[df.synchronize_seqscans == 'off'], 'parallelism_3', group=['branch', 'pbm_evict_num_samples'],
        # #          x='parallelism', xsort=True, xlabel='Parallelism',
        # #          y='hit_rate', ylabel='hit rate', ybound=(0,1),
        # #          title='Hit-rate vs parallelism without syncscans'),
        # plot_exp(df, 'parallelism_same_nqueries_1', group=['branch', 'pbm_evict_num_samples'],
        #          x='parallelism', xsort=True, xlabel='Parallelism',
        #          y='hit_rate', ylabel='hit rate', ybound=(0, 1),
        #          title='Hit-rate vs parallelism with syncscans'),
        # plot_exp(df, 'parallelism_same_nqueries_1', group=['branch', 'pbm_evict_num_samples'],
        #          x='parallelism', xsort=True, xlabel='Parallelism',
        #          y='throughput',
        #          title='Throughput vs parallelism'),
        # plot_exp(df, 'parallelism_same_nqueries_1', group=['branch', 'pbm_evict_num_samples'],
        #          x='parallelism', xsort=True, xlabel='Parallelism',
        #          y='data_per_stream', ylabel='Data read (GiB)',
        #          title='Data volume (per stream) vs parallelism'),



        # parallelism_same_nqueries_1,   parallelism_3

    ]

    f, ax = plt.subplots(2, 2)
    for i, exp in enumerate(['parallelism_sel20', 'parallelism_sel40', 'parallelism_sel60', 'parallelism_sel80']):
        plot_exp(df, exp, ax=ax[i//2][i%2], group=['branch', 'pbm_evict_num_samples'],
                 x='parallelism', xsort=True, xlabel='Parallelism',
                 y='hit_rate', ylabel='hit rate', ybound=(0, 1),
                 title=exp + ' hit_rate vs parallelism')

    # TODO ^ plot the same thing with average_stream_s (?) instead of throughput?
    # TODO figure out the weird spike!

    plot_exp(df, 'test_weird_spike_1', group=['branch', 'pbm_evict_num_samples'],
             x='parallelism', xsort=True, xlabel='Parallelism',
             y='hit_rate', ylabel='hit rate', ybound=(0, 1), avg_y_values=True,
             title='averaged hit_rate vs parallelism 1')

    plot_exp(df, 'test_weird_spike_2', group=['branch', 'pbm_evict_num_samples'],
             x='parallelism', xsort=True, xlabel='Parallelism',
             y='hit_rate', ylabel='hit rate', ybound=(0, 1), avg_y_values=True,
             title='averaged hit_rate vs parallelism 2')

    f, ax = plt.subplots(2, 3)
    for i, s in enumerate([16312, 22289, 16987, 6262, 32495]):
        plot_exp(df[df.seed == str(s)], 'test_weird_spike_2', ax=ax[i//3][i%3],
                 group=['branch', 'pbm_evict_num_samples'],
                 x='parallelism', xsort=True, xlabel='Parallelism',
                 y='hit_rate', ylabel='hit rate', ybound=(0, 1), avg_y_values=True,
                 title=f'averaged hit_rate vs parallelism seed={s}')




    print(f'Showing plots...')
    plt.show()

    return df, plots

    # TODO consider `seaborn` package for better visualization...
    # TODO split script into generating results.csv (collect_results?) and processing results.csv (graphing, etc.)


if __name__ == '__main__':
    df, plots = main()
