"""
%prog [options] CONFIG

THOR detects differential peaks in multiple ChIP-seq profiles associated
with two distinct biological conditions.

Copyright (C) 2014-2016  Manuel Allhoff (allhoff@aices.rwth-aachen.de)

This program comes with ABSOLUTELY NO WARRANTY. This is free 
software, and you are welcome to redistribute it under certain 
conditions. Please see LICENSE file for details.
"""

# Python
from __future__ import print_function

import sys
import time
import numpy as np
from math import log
from operator import add


# Internal
from rgt.THOR.postprocessing import merge_delete
from MultiCoverageSet import MultiCoverageSet
from rgt.GenomicRegion import GenomicRegion
from rgt.GenomicRegionSet import GenomicRegionSet
from rgt.THOR.get_fast_gen_pvalue import get_log_pvalue_new

import configuration

np.random.rand(42)


def is_cov_sparse(signal_statics, stepsize):
    """to test if data are sparse, then we could use sparse matrix
    we make our estimate according to max_read counts in one chrom that is less than shape of bin size
    """
    is_sparse = True
    for i in range(signal_statics['dim'][0]):
        for j in range(signal_statics['dim'][1]):
            stats_data = signal_statics['data'][i][j]['stats_data']
            max_stats = stats_data[-1]
            if max_stats[-1] < (max_stats[1]/stepsize) * 0.05:
                is_sparse &= True
            else:
                return False
    return is_sparse


def initialize(options, strand_cov, genome_path, regionset, mask_file, signal_statics, inputs_statics, tracker=None, verbose=False):
    """Initialize the MultiCoverageSet
    Region_giver includes: regions to be analysed + regions to be masked + chrom_sizes file name + chrom_sizes_dict
    Use sampling methods to initialize certain part of data
    Get exp_data, we have one pattern, 0.1
    """
    # options.binsize = 100
    # options.stepsize = 50
    print("Begin reading", file=sys.stderr)
    start = time.time()
    use_sm = is_cov_sparse(signal_statics, options.stepsize)
    cov_set = MultiCoverageSet(name=options.name, regionset=regionset,mask_file=mask_file, binsize=options.binsize, stepsize=options.stepsize, rmdup=options.rmdup, signal_statics=signal_statics, inputs_statics=inputs_statics,
                                      strand_cov=strand_cov, use_sm=use_sm)

    elapsed_time = time.time() - start
    print("End reading using time %.3f s"%(elapsed_time), file=sys.stderr)

    options.no_gc_content = True
    if not options.no_gc_content and genome_path: # maybe we could use samples to get values not all data;; samples from indices, and around 1000 for it
        start = time.time()
        options.gc_hv = None
        options.gc_avg_T = None
        options.gc_hv, options.gc_avg_T = cov_set.normalization_by_gc_content(inputs_statics, genome_path, options.gc_hv, options.gc_avg_T, delta=0.01)
        elapsed_time = time.time() - start
        if verbose:
            print("Compute GC-content using time %.3f s"%(elapsed_time), file=sys.stderr)

    cov_set.init_overall_coverage(strand_cov=strand_cov)

    if inputs_statics: # only inputs_statics exist we do it;
        start = time.time()
        options.factors_inputs = cov_set.normalization_by_input(signal_statics, inputs_statics, options.name, options.factors_inputs)
        if tracker:
            tracker.write(text=map(lambda x: str(x), options.factors_inputs), header="Inputs Scaling factors")
        elapsed_time = time.time() - start
        if verbose:
            print("Normalize input-DNA using time %.3f s"%(elapsed_time), file=sys.stderr)

    start = time.time()
    options.scaling_factors_ip = cov_set.normalization_by_signal(options.name, options.scaling_factors_ip, signal_statics, options.housekeeping_genes,
                                    options.report, options.m_threshold, options.a_threshold)
    if tracker:
        tracker.write(text=map(lambda x: str(x), options.scaling_factors_ip), header="Signal Scaling factors")
    elapsed_time = time.time() - start
    if verbose:
        print('Normalize ChIP-seq profiles using time %.3f s' % (elapsed_time), file=sys.stderr)
    ## we need to change data from float into interger
    cov_set.sm_change_data_2int()
    return cov_set


def dump_posteriors_and_viterbi(name, posteriors, DCS, states):
    print("Computing info...", file=sys.stderr)
    f = open(name + '-posts.bed', 'w')
    g = open(name + '-states-viterbi.bed', 'w')
    
    for i in range(len(DCS.indices_of_interest)):
        cov1, cov2 = DCS._get_sm_covs(i)
        p1, p2, p3 = posteriors[i][0], posteriors[i][1], posteriors[i][2]
        chrom, initial, final = DCS._index2coordinates(DCS.indices_of_interest[i])
        
        print(chrom, initial, final, states[i], cov1, cov2, sep='\t', file=g)
        print(chrom, initial, final, max(p3, max(p1,p2)), p1, p2, p3, cov1, cov2, sep='\t', file=f)

    f.close()
    g.close()


def _compute_pvalue((x, y, side, distr)):
    a, b = np.mean(x,dtype=int), np.mean(y,dtype=int)
    return -get_log_pvalue_new(a, b, side, distr)


def _get_log_ratio(l1, l2):
    l1, l2 = float(np.sum(np.array(l1))), float(np.sum(np.array(l2)))
    try:
        res = l1/l2
    except:
        return sys.maxint
    
    if res > 0:
        try:
            res = log(res)
            if np.isinf(res):
                return sys.maxint
            return res
        except:
            print('error to compute log ratio', l1, l2, file=sys.stderr)
            return sys.maxint
    else:
        return sys.maxint


def _merge_consecutive_bins(tmp_peaks, distr, merge=True):
    """Merge consecutive peaks and compute p-value. Return list
    <(chr, s, e, c1, c2, strand)> and <(pvalue)>"""
    peaks_set = GenomicRegionSet('')
    peaks_set.name = tmp_peaks.name
    i, j, = 0, 0
    while i < len(tmp_peaks):
        j+=1
        chrom, initial, final, state, data = tmp_peaks[i].chrom, tmp_peaks[i].initial, tmp_peaks[i].final, tmp_peaks[i].orientation, tmp_peaks[i].data
        c1, c2, strand_pos, strand_neg = data[0], data[1], data[2], data[3]
        v1 = c1
        v2 = c2

        tmp_pos = [strand_pos]
        tmp_neg = [strand_neg]
        #merge bins, here are some problems maybe happpen about the conditions
        while merge and i+1 < len(tmp_peaks) and final >= tmp_peaks[i+1].initial and state == tmp_peaks[i+1].orientation:
            final = tmp_peaks[i+1].final
            v1 = map(add, v1, tmp_peaks[i+1].data[0])
            v2 = map(add, v2, tmp_peaks[i+1].data[1])
            tmp_pos.append(tmp_peaks[i+1].data[2])
            tmp_neg.append(tmp_peaks[i+1].data[3])
            i += 1
        v1 = list(v1)
        v2 = list(v2)
        side = 'l' if state == '+' else 'r'

        pvalue = _compute_pvalue((v1, v2, side, distr))
        ratio = _get_log_ratio(tmp_pos, tmp_neg)
        # peaks.append((c, s, e, v1, v2, strand, ratio))
        peak_region = GenomicRegion(chrom=chrom, initial=initial, final=final,  orientation=state,
                                    data={'cov1':v1, 'cov2':v2, 'pvalue':pvalue, 'ratio':ratio})
        peaks_set.add(peak_region)
        i += 1

    return peaks_set


def _calpvalues_merge_bins(tmp_peaks, bin_pvalues, distr, pcutoff):
    """ we calculate firstly p-values for each bin and then filter them using pcutoff values,
    at end we merge bins with similar p-values
    pcutoff: two format, one is just one value, secondly, one array, [start, end, steps]
    then above them, we get it, and then merge them..

    :tem_peaks
        tmp_peaks.append((chrom, initial, final, cov1, cov2, strand, cov1_strand, cov2_strand))
        c, s, e, c1, c2, strand, strand_pos, strand_neg = tmp_peaks[i]
    :return
        ratio = _get_log_ratio(tmp_pos, tmp_neg)
        peaks.append((c, s, e, v1, v2, strand, ratio))
        pvalues = map(_compute_pvalue, pvalues)
    """
    pcutoff_peaks = {}
    pcutoff_pvalues = {}


    if len(pcutoff) == 3:
        pvalue_init, pvalue_end, pvalue_step = pcutoff[0], pcutoff[1],pcutoff[2]
        if pvalue_end > sys.maxint:
            pvalue_end = sys.maxint
    elif len(pcutoff) == 2:
        pvalue_init, pvalue_end, pvalue_step = pcutoff[0], pcutoff[1], 1
    elif len(pcutoff) == 1:
        pvalue_init, pvalue_end, pvalue_step = pcutoff[0], pcutoff[0] + 1, 1

    for i in np.arange(pvalue_init, pvalue_end, pvalue_step):
        new = 0
        new_peaks = []
        new_pvalues = []
        pi_peaks = []
        pi_pvalues = []
        for j in range(len(bin_pvalues)):
            # this means actually we filter like cumulatively..
            if bin_pvalues[j] >= i:
                new_pvalues.append(bin_pvalues[j])
                new_peaks.append(tmp_peaks[j])

        if new_pvalues is None:
            print('the setting of end filter p-value is too big')
            pcutoff_peaks['p_value_over_' + str(i)] = pi_peaks
            pcutoff_pvalues['p_value_over_' + str(i)] = pi_pvalues
            return pcutoff_peaks, pcutoff_pvalues

        for k in range(len(new_peaks)):
            chrom, s, e, ct1, ct2, strand, strand_pos, strand_neg = new_peaks[k]
            if new == 0:
                current_chr = chrom
                current_s = s
                current_e = e
                current_strand = strand
                current_ct1 = ct1
                current_ct2 = ct2
                current_strand_pos = [strand_pos]
                current_strand_neg = [strand_neg]
                current_pvalue = [new_pvalues[k]]
                new += 1
            else:
                if (current_chr == chrom) & (current_strand == strand) & (current_e >= s):
                    current_e = e
                    # if (numpy.argmax([pvalue,current_pvalue])==0):
                    current_pvalue.append(new_pvalues[k])
                    current_ct1 = np.add(ct1, current_ct1 )
                    current_ct2 = np.add(ct2, current_ct2 )
                    current_strand_pos += [strand_pos]
                    current_strand_neg += [strand_neg]
                    new += 1
                else:
                    # current_ct1=current_ct1/new
                    # current_ct2=current_ct2/new
                    current_pvalue.sort(reverse=True)
                    # print(current_pvalue)
                    p = - min([np.log10(new) - x - np.log10(j + 1) for j, x in enumerate(current_pvalue)])
                    ratio = _get_log_ratio(current_strand_pos, current_strand_neg)
                    pi_peaks.append((current_chr, current_s, current_e, list(current_ct1), list(current_ct2), current_strand, ratio))
                    pi_pvalues.append(p)

                    current_chr = chrom
                    current_s = s
                    current_e = e
                    current_strand = strand
                    current_ct1 = np.add(ct1, current_ct1)
                    current_ct2 = np.add(ct2, current_ct2)
                    current_strand_pos = [strand_pos]
                    current_strand_neg = [strand_neg]
                    current_pvalue = [new_pvalues[k]]

        current_pvalue.sort(reverse=True)
        p = - min([np.log10(new) - x - np.log10(j + 1) for j, x in enumerate(current_pvalue)])
        ratio = _get_log_ratio(current_strand_pos, current_strand_neg)
        pi_peaks.append((current_chr, current_s, current_e, list(current_ct1), list(current_ct2), current_strand, ratio))
        pi_pvalues.append(p)

        pcutoff_peaks['p_value_'+str(i)] = pi_peaks
        pcutoff_pvalues['p_value_'+str(i)] = pi_pvalues

    return pcutoff_pvalues, pcutoff_peaks


def get_peaks_set(peaks_set, indices):
    """get dataf from peaks_set with indices and recombine them together"""
    tmp_set = GenomicRegionSet('')
    tmp_set.name = peaks_set.name
    indices = np.ravel(indices)
    for idx in indices:
        tmp_set.add(peaks_set[idx])
    return tmp_set


def combine_2region_set(peaks):
    """combine data a list into 2 single region set, but at first it should have such values"""
    peaks_set = reduce(lambda x_region_set, y_region_set: x_region_set.combine(y_region_set, output=False), peaks)
    peaks_set.name = "peaks"
    return peaks_set


def get_peaks(cov_set, states, exts, merge, distr, merge_bin, p=70):
    """Merge Peaks, compute p-value and give out *.bed and *.narrowPeak"""
    start = time.time()
    exts = np.mean(exts)
    tmp_data = []
    peaks_set = GenomicRegionSet('peaks')
    for i in range(len(cov_set.indices_of_interest)):
        if states[i] not in [1,2]:
            continue #ignore background states
        idx = cov_set.indices_of_interest[i]
        state = '+' if states[i] == 1 else '-'
        covs_list, strand_covs_list = cov_set.get_sm_covs(idx, strand_cov=True)  # only return data not indices
        cov1 = (covs_list[0]).astype(int)
        cov2 = (covs_list[1]).astype(int)
        # strand_cov1 in format [file_0: [forwards: ],[reverse: ]],[file_1:: [forward: ],[reverse: ] ]
        forward_strand = np.sum(strand_covs_list[0][:,0] + strand_covs_list[1][:,0])
        reverse_strand = np.sum(strand_covs_list[0][:,1] + strand_covs_list[1][:,1])
        ## get genome information from idx, to get chrom, initial and final
        chrom, initial, final = cov_set.sm_index2coordinates(idx)
        peak_region = GenomicRegion(chrom=chrom, initial=initial, final=final, name='', orientation=state, data=(cov1, cov2,forward_strand, reverse_strand))
        peaks_set.add(peak_region)
        side = 'l' if states[i] == 1 else 'r'
        tmp_data.append((np.sum(cov1), np.sum(cov2), side, distr))
    
    if not tmp_data:
        print('no data', file=sys.stderr)
        return [], [], []
    
    tmp_pvalues = np.array(map(_compute_pvalue, tmp_data))
    p_threshold = np.percentile(tmp_pvalues, p)

    indices = np.where(tmp_pvalues > p_threshold)
    peaks_set = get_peaks_set(peaks_set, indices)

    peaks_set = _merge_consecutive_bins(peaks_set, distr, merge_bin) #merge consecutive peaks and compute p-value
    peaks_set = merge_delete(exts, merge, peaks_set) #postprocessing, returns GenomicRegionSet with merged regions

    elapsed_time = time.time() - start
    if configuration.VERBOSE:
        print("Compute peaks using time %.3f s" % (elapsed_time), file=sys.stderr)
    return peaks_set


