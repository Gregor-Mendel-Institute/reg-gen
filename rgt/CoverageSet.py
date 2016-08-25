"""
CoverageSet
===================
CoverageSet represents the coverage data of a GenomicRegionSet.

"""

from __future__ import print_function
from rgt.GenomicRegionSet import *
import pysam, sys  # @UnresolvedImport
import numpy as np
import numpy.ma
import os
import math
import tempfile
import subprocess
import multiprocessing
from rgt.ODIN.gc_content import get_gc_context
import sys
from sys import platform




class CoverageSet:
    """*Keyword arguments:*

        - name -- names.
        - genomicRegions -- instance of GenomicRegionSet
    """
    
    def __init__(self, name, GenomicRegionSet):
        """Initialize CoverageSet <name>."""
        self.name = name
        self.genomicRegions = GenomicRegionSet
        self.coverage = [] #coverage data for genomicRegions
        self.binsize = 100
        self.mapped_reads = None #number of mapped read
        self.reads = None #number of reads
        self.stepsize = 50
    
    def subtract(self, cs):
        """Substract CoverageSet <cs>.
        
        *Keyword arguments:*
        
        - cs -- instance of CoverageSet
        
        .. note::
            negative values are set to 0.
        """
        
        cs_chroms = cs.genomicRegions.get_chrom()
        assert len(cs_chroms) == len(set(cs_chroms)) #no double entries
        assert len(self.genomicRegions.get_chrom()) == len(set(self.genomicRegions.get_chrom()))
        
        i = 0
        for c in self.genomicRegions.get_chrom(): #c corresponds to self.coverage[i]
            try:
                j = cs_chroms.index(c)
                assert len(self.coverage[i]) == len(cs.coverage[j])
                self.coverage[i] -= cs.coverage[j]
                self.coverage[i] = self.coverage[i].clip(0, max(max(self.coverage[i]), 0)) #neg. values to 0
            except ValueError:
                pass
            i += 1
    
    def add(self, cs):
        """Add CoverageSet <cs>.
        
        *Keyword arguments:*
        
        - cs -- instance of CoverageSet, which is used to add up
        
        """
        cs_chroms = cs.genomicRegions.get_chrom()
        assert len(cs_chroms) == len(set(cs_chroms)) #no double entries
        assert len(self.genomicRegions.get_chrom()) == len(set(self.genomicRegions.get_chrom()))
        
        i = 0
        for c in self.genomicRegions.get_chrom(): #c corresponds to self.coverage[i]
            try:
                j = cs_chroms.index(c)
                assert len(self.coverage[i]) == len(cs.coverage[j])
                self.coverage[i] += cs.coverage[j]
            except ValueError:
                pass
            i += 1
    
    def scale(self, factor):
        """Scale coverage with <factor>.
        
        *Keyword arguments:*
        
        - factor -- float
        
        """
        for i in range(len(self.coverage)):
            self.coverage[i] = np.rint(self.coverage[i] * float(factor)).astype(int)

    def normRPM(self):
        """Normalize to read per million (RPM)."""
        if self.reads == 0:
            print("Error! The reads number is zero in "+self.name)
            print("** Please try to reindex the file by \'samtools index\'.")
            sys.exit(1)

        factor=1000000/float(self.reads)

        self.coverage = np.array(self.coverage)*factor

    def write_bed(self, filename, zero=False):
        """Output coverage in BED format. 
        
        *Keyword arguments:*
        
        - filename -- filepath
        - zero -- boolean
        
        .. note:: If zero=True, coverage of zero is output as well. This may cause large output files!
        
        """
        
        with open(filename, 'w') as f:
            i = 0
            for region in self.genomicRegions:
                c = self.coverage[i]
                i += 1
                for j in range(len(c)):
                    if zero:
                        print(region.chrom, j * self.stepsize + ((self.binsize-self.stepsize)/2) + region.initial, \
                              j * self.stepsize + ((self.binsize+self.stepsize)/2) + region.initial, c[j], sep='\t', file=f)
                    else:
                        if c[j] != 0:
                            print(region.chrom, j * self.stepsize + ((self.binsize-self.stepsize)/2) + region.initial, \
                                  j * self.stepsize + ((self.binsize+self.stepsize)/2) + region.initial, c[j], sep='\t', file=f)
                        
    def write_wig(self, filename, end):
        """Output coverage in wig format. 
        
        *Keyword arguments:*
        
        - filename -- filepath
        - end -- boolean
        
        .. warning:: Parameter end is deprecated! Please do not use it.
        
        """
        f = open(filename, 'w')
        i = 0
        for region in self.genomicRegions:
            print('variableStep chrom=' + str(region.chrom) + ' span=' +str(self.stepsize), file=f)
            c = self.coverage[i]
            i += 1
            for j in range(len(c)):
                if c[j] != 0:
                    print(j * self.stepsize + ((self.binsize-self.stepsize)/2), c[j], file=f)
        f.close()
    
    def write_bigwig(self, filename, chrom_file, end=True, save_wig=False):
        """Output coverage in bigwig format. 
        
        The path to the chromosome size file <chrom_file> is required. This file is tab-separated and assigns
        a chromosome to its size.
        
        *Keyword arguments:*
        
        - filename -- filepath
        - chrom_file -- chromosome size file
        - end -- boolean
        - save_wig -- boolean, if set, wig file is also saved.
        
        .. warning:: Parameter <end> is deprecated! Please do not use it.
        
        .. note:: The <save_wig> option may cause large output files 
        
        """
        
        if save_wig:
            tmp_path = filename + '.wig'
            self.write_wig(tmp_path)
            t = ['wigToBigWig', "-clip", tmp_path, chrom_file, filename] #TODO: something is wrong here, call only wigToBigWig
            c = " ".join(t)
            os.system(c)
        else:
            _, tmp_path = tempfile.mkstemp()
            self.write_wig(tmp_path, end)
            t = ['wigToBigWig', "-clip", tmp_path, chrom_file, filename] #TODO: something is wrong here, call only wigToBigWig
            c = " ".join(t)
            #print(c, file=sys.stderr)
            os.system(c)
            #os.remove(tmp_path)
    
    def _init_read_number(self, bamFile):
        """Compute number of reads and number of mapped reads for CoverageSet"""
        # XXX ToDo add number of mapped reads in all cases
        try:
            if pysam.__version__ == '0.9.0':
                a = pysam.idxstats(bamFile)
                mapped_reads = sum([int(el.split('\t')[2]) for el in a.split('\n')[:len(a.split('\n'))-1]])
                unmapped_read = sum([int(el.split('\t')[3]) for el in a.split('\n')[:len(a.split('\n'))-1]])
                self.reads = mapped_reads + unmapped_read
                self.mapped_reads = mapped_reads
            else:
                self.reads = reduce(lambda x, y: x + y, [ eval('+'.join(l.rstrip('\n').split('\t')[2:]) ) for l in pysam.idxstats(bamFile)])
                self.mapped_reads = None
        except:
            self.reads = None
            self.mapped_reads = None
    
    def coverage_from_genomicset(self, bamFile, readSize=200, strand_specific=False):

        """Compute coverage based on the class variable <genomicRegions>. 
        
        Iterate over each GenomicRegion in class variable genomicRegions (GenomicRegionSet) and set coverage to the number of reads falling into the GenomicRegion.
              
        *Keyword arguments:*
        
        - bamFile -- path to bam file
        - readSize -- used read size
        - strand_specific -- calculate the coverage from the reads with the same orientation with the region
        
        *Output:*
        
        Class variable <coverage>: a list where the elements correspond to the GenomicRegion. The list elements give
        the number of reads falling into the GenomicRegion.
        
        """
        
        bam = pysam.Samfile(bamFile, "rb" )
        self._init_read_number(bamFile)
        
        cov=[0]*len(self.genomicRegions)
        for i,region in enumerate(self.genomicRegions):
            
            try:
                if not strand_specific:
                    for r in bam.fetch(region.chrom,region.initial-readSize,region.final+readSize):
                        cov[i] += 1
                else:
                    for r in bam.fetch(region.chrom,region.initial-readSize,region.final+readSize):
                        # print(region.orientation)
                        # print(r.is_reverse)
                        if region.orientation == "+" and not r.is_reverse: cov[i] += 1
                        elif region.orientation == "-" and r.is_reverse: cov[i] += 1
                
            except:
                print("\tSkip: "+region.toString())

        self.coverage = cov 
        self.coverageOrig = cov

    def _get_bedinfo(self, l):
        if len(l) > 1:
            l.strip()
            l = l.split('\t')
            return l[0], int(l[1]), int(l[2]), True
        else:
            return -1, -1, -1, False

    def coverage_from_bam2(self, bam_file, extension_size = 200, binsize = 100, stepsize = 50, rmdup = True, mask_file = None, 
                          get_strand_info = False, no_gaps=False):
        """Compute coverage based on GenomicRegionSet. 
        
        Iterate over each GenomicRegion in class variable genomicRegions (GenomicRegionSet). The GenomicRegion is divided into consecutive bins with lenth <binsize>.
        A sliding-window approach with a stepsize of <stepsize> generates the coverage signal.
              
        *Keyword arguments:*
        
        - bam_file -- path to bam file
        - extension_size -- used extension size
        - binsize -- size of bins
        - stepsize -- stepsize for the window-based approach to generat the signal
        - rmdup -- remove dupliacted reads (reads with same starting coordinate)
        - mask_file -- ignore region described in <mask_file> (tab-separated: chrom, start, end)
        - get_strand_info -- compute strand information for each bin
        
        
        *Output:*
        
        - Class variable <coverage>: a list of lists: the elements correspond a GenomicRegion. This list gives the coverage of each bin.
        - Class variable <overall_cov>: a list: concatenation of class variable <coverage>.
        - If option <get_strand_info> is set, a numpy array class variable  <cov_strand_all> of tuples. The tuples give the number of forward and backward reads for each bin.
        
        *Example:*
        
        First, we compute a GenomicRegionSet that covers the entire mouse genome mm9. We use the annotation of RGT to compute the variable <regionset>::
            
            >>>from rgt.Util import GenomeData
            >>>from helper import get_chrom_sizes_as_genomicregionset
            
            >>>g = GenomeData('mm9')
            >>>regionset = get_chrom_sizes_as_genomicregionset(g.get_chromosome_sizes())
        
        Next, we load the CoverageSet class from RGT and initialize it with the variable <regionset>. Finally, we compute the coverage based on <bamfile>::
        
            >>>from rgt.CoverageSet import CoverageSet
            >>>cov = CoverageSet('IP coverage', regionset)
            >>>cov.coverage_from_bam(bam_file=bamfile, extension_size=200)
        
        We can now access <cov>::
        
            >>>from __future__ import print_function
            >>>from numpy import sum
            >>>print(cov.overall_cov[cov.overall_cov>0][:10])
            [1 1 1 1 1 2 2 2 2 1]
            
            >>>print(len(cov.overall_cov))
            54515813
        
        .. note::
        
         the length of the <overall_cov> equals 54515813, as we take the entire genome into account, but use a the default stepsize of 50 for segmentation. 
        
        """

        if len(self.genomicRegions) == 0:
            return
        
        self.binsize = binsize
        self.stepsize = stepsize
        self.coverage = []
        bin_half = int(0.5 * binsize)
        bam = pysam.Samfile(bam_file, "rb" )
        
        for read in bam.fetch():
            fragment_size = read.rlen + extension_size
            break

        self._init_read_number(bam_file)
        
        # Mask
        if mask_file and os.path.exists(mask_file):
            mask = GenomicRegionSet(mask_file)
            mask.read_bed(mask_file)
            self.genomicRegions = self.genomicRegions.subtract(mask)

        if get_strand_info:
            self.cov_strand_all = []
        # Calculate the coverage
        for region in self.genomicRegions:
            steps_num = int(math.ceil(len(region) / stepsize))
            cov = [0] * steps_num
            if get_strand_info:
                cov_strand = [[0,0]] * steps_num
                # strand_info = {}
            positions = []

            for read in bam.fetch(region.chrom, max(0, region.initial-fragment_size), region.final+fragment_size):
                # print(read.query_alignment_start < read.query_alignment_end)
                if read.is_reverse and read.reference_end < region.initial:
                    continue
                elif not read.is_reverse and read.reference_start > region.final:
                    continue
                elif not read.is_unmapped:
                    
                    if no_gaps:
                        positions += read.get_blocks()

                    else:
                        if not read.is_reverse:
                            positions += [[read.reference_start, read.reference_end + extension_size]]
                        else:
                            positions += [[read.reference_start - extension_size, read.reference_end]]
            
            positions.sort(lambda x,y: cmp(x[0], y[0]))
            # print(positions)

            # if not read.is_reverse:
            i = 0
            j = 0
            pre_j = 0
            while i < steps_num and j < len(positions):
            # for i in range(steps_num):
                l_bin = 0 - bin_half + i*stepsize + region.initial
                r_bin = 0 + bin_half + i*stepsize + region.initial

                if positions[j][1] <= l_bin: # frag < bin
                    j += 1
                    pre_j = j
                elif positions[j][0] <= l_bin and positions[j][1] > l_bin:
                    cov[i] += 1
                    j += 1
                elif l_bin < positions[j][0] and positions[j][1] < r_bin:
                    cov[i] += 1
                    j += 1
                elif positions[j][1] >= r_bin and positions[j][0] < r_bin:
                    cov[i] += 1
                    j += 1
                elif positions[j][0] >= r_bin:
                    j = pre_j
                    i += 1
                else:
                    print("eeeeeeeeeeelllllllllllsssssssseeeeeeeee")

            self.coverage.append(np.array(cov))


    
    def coverage_from_bam(self, bam_file, extension_size = 200, binsize = 100, stepsize = 50, rmdup = True, mask_file = None, 
                          get_strand_info = False, no_gaps=False):
        """Compute coverage based on GenomicRegionSet. 
        
        Iterate over each GenomicRegion in class variable genomicRegions (GenomicRegionSet). The GenomicRegion is divided into consecutive bins with lenth <binsize>.
        A sliding-window approach with a stepsize of <stepsize> generates the coverage signal.
              
        *Keyword arguments:*
        
        - bam_file -- path to bam file
        - extension_size -- used read size
        - binsize -- size of bins
        - stepsize -- stepsize for the window-based approach to generat the signal
        - rmdup -- remove dupliacted reads (reads with same starting coordinate)
        - mask_file -- ignore region described in <mask_file> (tab-separated: chrom, start, end)
        - get_strand_info -- compute strand information for each bin
        
        
        *Output:*
        
        - Class variable <coverage>: a list of lists: the elements correspond a GenomicRegion. This list gives the coverage of each bin.
        - Class variable <overall_cov>: a list: concatenation of class variable <coverage>.
        - If option <get_strand_info> is set, a numpy array class variable  <cov_strand_all> of tuples. The tuples give the number of forward and backward reads for each bin.
        
        *Example:*
        
        First, we compute a GenomicRegionSet that covers the entire mouse genome mm9. We use the annotation of RGT to compute the variable <regionset>::
            
            >>>from rgt.Util import GenomeData
            >>>from helper import get_chrom_sizes_as_genomicregionset
            
            >>>g = GenomeData('mm9')
            >>>regionset = get_chrom_sizes_as_genomicregionset(g.get_chromosome_sizes())
        
        Next, we load the CoverageSet class from RGT and initialize it with the variable <regionset>. Finally, we compute the coverage based on <bamfile>::
        
            >>>from rgt.CoverageSet import CoverageSet
            >>>cov = CoverageSet('IP coverage', regionset)
            >>>cov.coverage_from_bam(bam_file=bamfile, extension_size=200)
        
        We can now access <cov>::
        
            >>>from __future__ import print_function
            >>>from numpy import sum
            >>>print(cov.overall_cov[cov.overall_cov>0][:10])
            [1 1 1 1 1 2 2 2 2 1]
            
            >>>print(len(cov.overall_cov))
            54515813
        
        .. note::
        
         the length of the <overall_cov> equals 54515813, as we take the entire genome into account, but use a the default stepsize of 50 for segmentation. 
        
        """

        if len(self.genomicRegions) == 0:
            return
        
        self.binsize = binsize
        self.stepsize = stepsize
        self.coverage = []
        
        bam = pysam.Samfile(bam_file, "rb" )
        
        for read in bam.fetch():
            fragment_size = read.rlen + extension_size
            break
        
        self._init_read_number(bam_file)
        
        #check whether one should mask
        next_it = True
        if mask_file is not None and os.path.exists(mask_file):
            mask = True
            f = open(mask_file, 'r')
            c_help, s_help, e_help = self.genomicRegions.sequences[0].chrom, -1, -1
        else:
            mask = False
        
        chrom_regions = [r.chrom for r in self.genomicRegions.sequences] #chroms by regions
        
        if get_strand_info:
            self.cov_strand_all = []
        
        for region in self.genomicRegions:
            cov = [0] * (len(region) / stepsize)
            
            if get_strand_info:
                cov_strand = [[0,0]] * (len(region) / stepsize)
                strand_info = {}
            
            positions = []
            j = 0
            read_length = -1
            try:
                for read in bam.fetch(region.chrom, max(0, region.initial-fragment_size), region.final+fragment_size):
                    if len(read.get_blocks()) > 1: continue
                    j += 1
                    read_length = read.rlen 
                    if not read.is_unmapped:
                        # pos = read.pos - extension_size if read.is_reverse else read.pos
                        # pos_help = read.pos - read.qlen if read.is_reverse else read.pos
                        pos = read.pos - extension_size if read.is_reverse else read.pos
                        pos_help = read.pos - read.qlen if read.is_reverse else read.pos
                        
                        within_gap = False
                        if no_gaps:
                            blocks = read.get_blocks()
                            if len(blocks) > 1:
                                # print(read.is_reverse)
                                # print(read.pos)
                                # print(blocks)
                                for b_ind in range(len(blocks) - 1):
                                    # print([blocks[b_ind][1], read.pos, blocks[b_ind+1][0]])
                                    if blocks[b_ind][1] <= read.pos < blocks[b_ind+1][0]:
                                        within_gap = True

                            
                            
                        #if position in mask region, then ignore
                        if mask:
                            while next_it and c_help not in chrom_regions: #do not consider this deadzone
                                c_help, s_help, e_help, next_it = self._get_bedinfo(f.readline())
                            if c_help != -1 and chrom_regions.index(region.chrom) >= chrom_regions.index(c_help): #deadzones behind, go further
                                while next_it and c_help != region.chrom: #get right chromosome
                                    c_help, s_help, e_help, next_it = self._get_bedinfo(f.readline())
                            while next_it and e_help <= pos_help and c_help == region.chrom: #check right position
                                c_help, s_help, e_help, next_it = self._get_bedinfo(f.readline())
                            if next_it and s_help <= pos_help and c_help == region.chrom:
                                continue #pos in mask region
                        if within_gap: continue
                        else: positions.append(pos)
                        
                        if get_strand_info:
                            if pos not in strand_info:
                                strand_info[pos] = (1,0) if not read.is_reverse else (0,1)
                        
            except ValueError:
                pass
            if rmdup:
                positions = list(set(positions))
                
            positions.sort()
            positions.reverse()
            # print(positions[0:10])
            i = 0
            while positions:
                win_s = max(0, i * stepsize - binsize*0.5) + region.initial
                win_e = i * stepsize + binsize*0.5 + region.initial 
                c = 0
                if get_strand_info:
                    sum_strand_info = [0,0]
                
                taken = []
                while True:
                    s = positions.pop()
                    
                    taken.append(s)
                    if s < win_e: #read within window
                        c += 1
                        if get_strand_info:
                            sum_strand_info[0] += strand_info[s][0]
                            sum_strand_info[1] += strand_info[s][1]
                        
                    if s >= win_e or not positions:
                        taken.reverse()
                        for s in taken:
                            if s + extension_size + read_length >= win_s: #consider read in next iteration
                                positions.append(s)
                            else:
                                break #as taken decreases monotonously
                        taken = []
                        break
                
                if i < len(cov):
                    cov[i] = c
                    if get_strand_info:
                        cov_strand[i] = sum_strand_info
                i += 1

            self.coverage.append(np.array(cov))
            if get_strand_info:
                self.cov_strand_all.append(np.array(cov_strand))
            
        self.coverageorig = self.coverage[:]
        self.overall_cov = reduce(lambda x,y: np.concatenate((x,y)), [self.coverage[i] for i in range(len(self.genomicRegions))])
        if mask: f.close()

    def index2coordinates(self, index, regions):
        """Convert index of class variable <overall_cov> to genomic coordinates.
        
        *Keyword arguments:*
        
        - index -- index of <overall_cov> that is to be converted
        - regions -- instance of GenomicRegionSet the conversion is based on
        
        .. note:: In most of the cases, the parameter <regions> equals the GenomicRegionSet used for the initialization of the CoverageSet.
                
        *Output:*
        
        Triple which gives the chromosome, the start- and the end-coordinate of the bin associated to <index>.
        
        *Example:*
        
        Here, we give out the genomic regions of bins that exhibit a value higher than 10::
        
            >>>from rgt.CoverageSet import CoverageSet
            >>>cov = CoverageSet('IP coverage', regionset)
            >>>cov.coverage_from_bam(bam_file=bamfile, extension_size=200)
            >>>for i, el in enumerate(cov.overall_cov):
            >>>    if el > 10:
            >>>        chrom, s, e = cov.index2coordinates(i, regionset)
            >>>        print(chrom, s, e)
        
        """
        r = regions
        iter = r.__iter__()
        r = iter.next()
        sum = r.final
        last = 0
        i = 0
        while sum <= index * self.stepsize:
            last += len(self.coverage[i])
            try:
                r = iter.next()
            except StopIteration:
                sum += r.final
                i += 1
                break
            sum += r.final
            i += 1
        
        return r.chrom, (index-last) * self.stepsize, \
            min((index-last) * self.stepsize + self.stepsize, r.final)
    
    def coverage_from_bigwig(self, bigwig_file, stepsize=100):

        """Return list of arrays describing the coverage of each genomicRegions from <bigwig_file>.
        
        *Keyword arguments:*
        
        - bigwig_file -- path to bigwig file
        - stepsize -- used stepsize
        
        *Output:*
        
        Class variable <coverage>: a list where the elements correspond to the GenomicRegion. The list elements give
        the number of reads falling into the GenomicRegion.
        
        """
        if platform == "darwin" or "http://" in bigwig_file or "https://" in bigwig_file or "ftp://" in bigwig_file:
            self.coverage = []
            # mp_input = []
            for gr in self.genomicRegions:
                # print(gr)
                steps = int(abs(gr.final-gr.initial)/stepsize)
                cmd = ["bigWigSummary",bigwig_file,gr.chrom,str(gr.initial-stepsize),str(gr.final-stepsize),str(steps)]
                # print(" ".join(cmd))
                try:
                    output = subprocess.check_output(cmd, shell=False, stderr=subprocess.STDOUT)
                    # print(output)
                    ds = [0 if "n/a" in x else float(x) for x in output.strip().split()]
                    self.coverage.append( np.array(ds) )
                except:
                    continue
        
        ### Linux platform
        else:
            # print("\tUsing ngslib on linux system...")
            from ngslib import BigWigFile
            self.coverage = []
            bwf = BigWigFile(bigwig_file)

            for gr in self.genomicRegions:
                depth = bwf.pileup(gr.chrom, max(0,int(gr.initial-stepsize/2)), 
                                             max(1,int(gr.final+stepsize/2)))
                ds = [depth[d] for d in range(0, gr.final-gr.initial, stepsize)]
                
                self.coverage.append( np.array(ds) )
            bwf.close()

            # import pyBigWig
            # self.coverage = []
            # bwf = pyBigWig.open(bigwig_file)
            # # print("1")
            # steps = int(len(self.genomicRegions[0])/stepsize)
            # for gr in self.genomicRegions:
            #     ds = bwf.stats(gr.chrom, gr.initial, gr.final, type="mean", nBins=steps)
            #     ds = [ x if x else 0 for x in ds ]
            #     self.coverage.append( np.array(ds) )
            #     # print(np.array(ds))
            # # print("2")
            # bwf.close()


        
    def phastCons46way_score(self, stepsize=100):
        """Load the phastCons46way bigwig files to fetch the scores as coverage.
        
        *Keyword arguments:*
        
        - stepsize -- used stepsize
        """
        self.coverage = []
        phastCons46way_dir = "/data/phastCons46way/"
        for gr in self.genomicRegions:
            bwf = BigWigFile(os.path.join(phastCons46way_dir, gr.chrom+".phastCons46way.bw"))
            depth = bwf.pileup(gr.chrom, gr.initial-stepsize/2, gr.final+stepsize/2)
            ds = []
            for i in range(0, gr.final-gr.initial):
                d = [ depth[j] for j in range(i,i+stepsize) ]
                ds.append(sum(d)/len(d))
                
            if gr.orientation == "-":
                self.coverage.append( np.array(list(reversed(ds))) )
            else:
                self.coverage.append( np.array(ds) )

            bwf.close()

    def norm_gc_content(self, cov, genome_path, chrom_sizes):
        chrom_sizes_dict = {}
        
        with open(chrom_sizes) as f:
            for line in f:
                line = line.strip()
                line = line.split('\t')
                c, e = line[0], int(line[1])
                chrom_sizes_dict[c] = e
        
        gc_cov, gc_avg, _ = get_gc_context(self.stepsize, self.binsize, genome_path, cov, chrom_sizes_dict)
        
        import warnings #todo: ugly, why do warnings occur?
        warnings.filterwarnings("ignore")
        
        for i in range(len(self.coverage)):
            assert len(self.coverage[i]) == len(gc_cov[i])
            self.coverage[i] = np.array(self.coverage[i])
            gc_cov[i] = np.array(gc_cov[i])
            gc_cov[i][gc_cov[i] < 10*-300] = gc_avg #sometimes zeros occur, do not consider
            self.coverage[i] = self.coverage[i] * gc_avg / gc_cov[i]
            self.coverage[i] = self.coverage[i].clip(0, max(max(self.coverage[i]), 0)) #neg. values to 0
            self.coverage[i] = self.coverage[i].astype(int)
            
    def count_unique_reads(self, bamFile):
        """Count the number of unique reads on for class variable <genomicRegions>.
        
        *Keyword arguments:*
        
        - bamFile -- path to bigwig file
        
        *Output:*
        
        number of unique reads
        
        """
        
        bam = pysam.Samfile(bamFile, "rb" )

        reads = []
        for i,region in enumerate(self.genomicRegions):
            for r in bam.fetch(region.chrom,region.initial,region.final):
                reads.append(r.qname)

        reads = list(set(reads))
        return len(reads)
