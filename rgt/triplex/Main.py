# Python Libraries
from __future__ import print_function
from __future__ import division
import sys
import os.path
import argparse 
import time, datetime, getpass, fnmatch
# Local Libraries
# Distal Libraries
from rgt.GenomicRegionSet import GenomicRegionSet
from triplexTools import TriplexSearch, PromoterTest, RandomTest
from SequenceSet import Sequence, SequenceSet
from Util import SequenceType

dir = os.getcwd()

# To do: merge absolute path and relative path

"""
Statistical tests and plotting tools for triplex binding site analysis

Author: Joseph Kuo
"""

##########################################################################
##### UNIVERSAL FUNCTIONS ################################################
##########################################################################

def print2(summary, string):
    """ Show the message on the console and also save in summary. """
    print(string)
    summary.append(string)
    
def output_summary(summary, directory, filename):
    """Save the summary log file into the defined directory"""
    pd = os.path.join(dir,directory)
    try: os.stat(pd)
    except: os.mkdir(pd)    
    if summary:
        with open(os.path.join(pd,"parameters.txt"),'w') as f:
            print("********* RGT Triplex: Summary information *********", file=f)
            for s in summary:
                print(s, file=f)
    
def check_dir(path):
    """Check the availability of the given directory and creat it"""
    try:
        os.stat(path)
    except:
        os.mkdir(path)

def main():
    ##########################################################################
    ##### PARAMETERS #########################################################
    ##########################################################################
    
    parser = argparse.ArgumentParser(description='Provides \
                                     triplex binding sites searching tool and \
                                     various Statistical tests for analysis. \
                                     \nAuthor: Joseph Kuo', 
                                     formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    subparsers = parser.add_subparsers(help='sub-command help',dest='mode')
    
    ################### Triplex search #######################################

    parser_search = subparsers.add_parser('search', help='Search the possible triplex binding sites \
                                                          between single strand (RNA) and \
                                                          double strand (DNA)')
    parser_search.add_argument('-r', '-RNA', type=str, help="Input file name for RNA (in fasta format)")
    parser_search.add_argument('-d', '-DNA', type=str, help="Input file name for DNA (in fasta or bed format)")
    
    parser_search.add_argument('-rt', choices= ['fasta', 'bed'], default='fasta', 
                               help="Input file type (fasta or bed)")
    parser_search.add_argument('-dt', choices= ['fasta', 'bed'], default='fasta', 
                               help="Input file type (fasta or bed)")

    parser_search.add_argument('-o', type=str, help="Output directory name")
    parser_search.add_argument('-genome',type=str, help='Define the directory where the genome FASTA files locate.')
    
    parser_search.add_argument('-min',type=int, default=8, help="Minimum length of binding site (Default: 4)")
    parser_search.add_argument('-max',type=int, default=None, help="Maxmum length of binding site (Default is infinite)")
    parser_search.add_argument('-m',type=str, default="RYMPA", help="Define the motif for binding site searching (Default is RYMPA)")
    parser_search.add_argument('-mp', action="store_true", help="Perform multiprocessing for faster computation.")
    
    ################### Promoter test ##########################################

    h_promotor = "Evaluate the difference between the promotor regions of the given genes and the other genes by the potential triplex forming sites on DNA with the given RNA."
    parser_promotertest = subparsers.add_parser('promoter', help=h_promotor)
    parser_promotertest.add_argument('-r', '-RNA', type=str, help="Input file name for RNA (in fasta format)")
    parser_promotertest.add_argument('-de', help="Input file for defferentially expression gene list ")
    parser_promotertest.add_argument('-pl', type=int, default=1000, 
                                   help="Define the promotor length (Default: 1000)")
    parser_promotertest.add_argument('-o', help="Output directory name for all the results and temporary files")
    parser_promotertest.add_argument('-organism',default='hg19', help='Define the organism. (Default: hg19)')
    parser_promotertest.add_argument('-a', type=int, default=0.05, help="Define alpha level for rejection p value (Default: 0)")
    parser_promotertest.add_argument('-ac', type=str, default=None, help="Input file for RNA accecibility ")
    parser_promotertest.add_argument('-cf', type=float, default=0.01, help="Define the cut off value for RNA accecibility")
    parser_promotertest.add_argument('-rt', action="store_true", default=False, help="Remove temporary files (bed, fa, txp...)")
    
    
    ################### Random test ##########################################
    h_random = "Test validation of the binding sites of triplex on the genome by randomization."
    parser_randomtest = subparsers.add_parser('randomtest', help=h_random)
    parser_randomtest.add_argument('-r', '-RNA', type=str, help="Input file name for RNA (in fasta format)")
    parser_randomtest.add_argument('-d', help="Input BED file for interested regions on DNA")
    parser_randomtest.add_argument('-o', help="Output directory name for all the results and temporary files")
    parser_randomtest.add_argument('-organism',default='hg19', help='Define the organism. (Default: hg19)')
    parser_randomtest.add_argument('-a', type=int, default=0.05, help="Define alpha level for rejection p value (Default: 0)")
    parser_randomtest.add_argument('-n', type=int, default=10000, 
                                   help="Number of times for randomization (Default: 10000)")
    parser_randomtest.add_argument('-rt', action="store_true", default=False, help="Remove temporary files (bed, fa, txp...)")
  

    ################### Parsing the arguments ################################
    if len(sys.argv) == 1:
        parser.print_help()
        sys.exit(1)
    elif len(sys.argv) == 2: 
        # retrieve subparsers from parser
        subparsers_actions = [action for action in parser._actions if isinstance(action, argparse._SubParsersAction)]
        # there will probably only be one subparser_action,but better save than sorry
        for subparsers_action in subparsers_actions:
            # get all subparsers and print help
            for choice, subparser in subparsers_action.choices.items():
                if choice == sys.argv[1]:
                    print("\nYou need more arguments.")
                    print("\nSubparser '{}'".format(choice))        
                    subparser.print_help()
        sys.exit(1)
    else:   
        args = parser.parse_args()
        if not args.o: 
            print("Please define the output diractory name. \n")
            sys.exit(1)

        t0 = time.time()
        # Normalised output path
        args.o = os.path.normpath(os.path.join(dir,args.o))
        
        # Input parameters dictionary
        summary = []
        summary.append("Time: " + datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        summary.append("User: " + getpass.getuser())
        summary.append("\nCommand:\n\t$ " + " ".join(sys.argv))

    ################################################################################
    ##### Search ###################################################################
    ################################################################################

    if args.mode == 'search':
        
        ############################################################################
        ##### Both RNA and DNA input ###############################################
        if args.r and args.d: 
            print2(summary, "\nSearch potential triplex forming binding sites between RNA and DNA")
            # Normalised paths
            args.r = os.path.normpath(os.path.join(dir,args.r)) 
            args.d = os.path.normpath(os.path.join(dir,args.d))
            triplex = TriplexSearch()
            
            ##### Read RNA sequences ###############################################
            print2(summary, "Step 1: Searching potential binding sites on RNA")
            rnaname = os.path.basename(args.r).split(".")[0]
            rnas = SequenceSet(name=rnaname, seq_type=SequenceType.RNA)
            
            if args.rt == 'fasta': # Input is FASTA
                print2(summary, "\tRead RNA in FASTA: "+args.r)
                rnas.read_fasta(args.r)
            else: # Input is BED
                if not args.genome: 
                    print("Please add the directory where the genome FASTA files locate.\n")
                    sys.exit(1)
                
                args.genome = os.path.normpath(os.path.join(dir,args.genome))    # Normalised paths
                print2(summary, "\tRead RNA in BED: "+args.r)
                print2(summary, "\tRefer to genome in FASTA: "+args.genome)
                rnas.read_bed(args.r, args.genome)
            
            ##### Search RNA potential binding sites ###############################
            # Save parameters
            print2(summary, "\tMotif: "+args.m)
            print2(summary, "\tMinimum length: "+args.min+" bp")
            if args.max: print2(summary, "\tMaximum length: "+args.max+" bp")
            else: print2(summary, "\tMaximum length: infinite")
            
            rbs = triplex.search_bindingsites(sequence_set=rnas, seq_type=SequenceType.RNA, 
                                              motif=args.m, min_len=args.min, max_len=args.max)
            rbs.write_bs(os.path.join(args.o, rnaname+".rbs"))
            t1 = time.time()
            print2(summary, "\tRunning time : " + str(datetime.timedelta(seconds=round(t1-t0))))
            print2(summary, "\tRNA binding sites are saved in: "+os.path.join(args.o, rnaname+".rbs"))
            
            
            ##### Read DNA sequences ###############################################
            print2(summary, "Step 2: Searching potential binding sites on DNA")
            dnaname = os.path.basename(args.d).split(".")[0]
            dnas = SequenceSet(name=dnaname, seq_type=SequenceType.DNA)
            
            if args.dt == 'fasta': # Input is FASTA
                print2(summary, "\tRead DNA in FASTA: "+args.d)
                dnas.read_fasta(args.d)
                
            else: # Input is BED
                if not args.genome: 
                    print("Please add the directory where the genome FASTA files locate.\n")
                    sys.exit(1)
                
                args.genome = os.path.normpath(os.path.join(dir,args.genome))    # Normalised paths
                print2(summary, "\tRead DNA in BED: "+args.d)
                print2(summary, "\tRefer to genome in FASTA: "+args.genome)
                dnas.read_bed(args.d, args.genome)
            
            ##### Search DNA potential binding sites ###############################
            # Save parameters
            print2(summary, "\tMinimum length: "+args.min+" bp")
            if args.max: print2(summary, "\tMaximum length: "+args.max+" bp")
            else: print2(summary, "\tMaximum length: infinite")
            
            dbs = triplex.search_bindingsites(sequence_set=dnas, seq_type=SequenceType.DNA, 
                                              motif=args.m, min_len=args.min, max_len=args.max)
            dbs.write_bs(os.path.join(args.o, dnaname+".dbs"))
            t2 = time.time()
            print2(summary, "\tRunning time : " + str(datetime.timedelta(seconds=round(t2-t1))))
            print2(summary, "\tDNA binding sites are saved in: "+os.path.join(args.o, dnaname+".dbs"))
            
            ##### Compare the binding sites between RNA and DNA ####################
            output_summary(summary, args.o, "summary.log")
        ############################################################################
        ##### Only RNA input #######################################################
        elif args.r and not args.d:
            print2(summary, "\nSearch potential triplex forming binding sites on RNA")
            
            args.r = os.path.normpath(os.path.join(dir,args.r))   # Normalised paths
            rnaname = os.path.basename(args.r).split(".")[0]
            rnas = SequenceSet(name=rnaname, seq_type=SequenceType.RNA)
            
            # Input is FASTA
            if args.rt == 'fasta':
                print2(summary, "\tRead RNA in FASTA: "+args.r)
                rnas.read_fasta(args.r)

            # Input is BED
            else:
                if not args.genome: 
                    print("Please add the directory where the genome FASTA files locate.\n")
                    sys.exit(1)
                
                args.genome = os.path.normpath(os.path.join(dir,args.genome))    # Normalised paths
                print2(summary, "\tRead RNA in BED: "+args.r)
                print2(summary, "\tRefer to genome in FASTA: "+args.genome)
                rnas.read_bed(args.r, args.genome)
            
            triplex = TriplexSearch()
            print2(summary, "\tMotif: "+args.m)
            print2(summary, "\tMinimum length: "+str(args.min))
            print2(summary, "\tMaximum length: "+str(args.max))

            bs = triplex.search_bindingsites(sequence_set=rnas, seq_type=SequenceType.RNA, 
                                             motif=args.m, min_len=args.min, max_len=args.max, multiprocess=args.mp)

            bs.write_rbs(os.path.join(args.o, rnaname+".rbs"))
            t1 = time.time()
            print2(summary, "\nTotal running time is : " + str(datetime.timedelta(seconds=round(t1-t0))))
            print2(summary, "Results are saved in: "+os.path.join(args.o, rnaname+".rbs"))
            output_summary(summary, args.o, "summary.log")
         
        ############################################################################
        ##### Only DNA input #######################################################
        elif args.d and not args.r:
            print2(summary, "\nSearch potential triplex forming binding sites on DNA")
            
            args.d = os.path.normpath(os.path.join(dir,args.d))   # Normalised paths
            dnaname = os.path.basename(args.d).split(".")[0]
            dnas = SequenceSet(name=dnaname, seq_type=SequenceType.DNA)
            
            # Input is FASTA
            if args.dt == 'fasta':
                print2(summary, "\tRead DNA in FASTA: "+args.d)
                dnas.read_fasta(args.d)

            # Input is BED
            else:
                if not args.genome: 
                    print("Please add the directory where the genome FASTA files locate.\n")
                    sys.exit(1)
                args.genome = os.path.normpath(os.path.join(dir,args.genome))   # Normalised paths
                print2(summary, "\tRead DNA in BED: "+args.d)
                print2(summary, "\tRefer to genome in FASTA: "+args.genome)
                dnas.read_bed(os.path.join(dir, args.d), args.genome)
            
            triplex = TriplexSearch()
            print2(summary, "\tMinimum length: "+str(args.min))
            print2(summary, "\tMaximum length: "+str(args.max))
            bs = triplex.search_bindingsites(sequence_set=dnas, seq_type=SequenceType.DNA, 
                                             motif=args.m, min_len=args.min, max_len=args.max, multiprocess=args.mp)

            bs.write_dbs(os.path.join(args.o, dnaname+".dbs"))
            t1 = time.time()
            print2(summary, "\nTotal running time is : " + str(datetime.timedelta(seconds=round(t1-t0))))
            print2(summary, "Results are saved in: "+os.path.join(args.o, dnaname+".dbs"))
            output_summary(summary, args.o, "summary.log")
            
            
        # No input
        else:
            print("Please define either RNA strand or DNA strand (or both) as inputs\n")
        
    ################################################################################
    ##### Fischer ##################################################################
    ################################################################################
    if args.mode == 'promoter':
        print2(summary, "\n"+h_promotor)
        args.r = os.path.normpath(os.path.join(dir,args.r))
        args.o = os.path.normpath(os.path.join(dir,args.o))
        check_dir(args.o)
        
        # Get GenomicRegionSet from the given genes
        print2(summary, "Step 1: Calculate the triplex forming sites on RNA and DNA.")
        promoter = PromoterTest(gene_list_file=args.de, organism=args.organism, promoterLength=args.pl)
        #promoter.search_triplex(rna=args.r, temp=args.o, remove_temp=args.rt)
        t1 = time.time()
        print2(summary, "\tRunning time is : " + str(datetime.timedelta(seconds=round(t1-t0))))

        print2(summary, "Step 2: Calculate the frequency of DNA binding sites within the promotors.")
        promoter.count_frequency(temp=args.o, remove_temp=args.rt)
        promoter.fisher_exact()
        t2 = time.time()
        print2(summary, "\tRunning time is : " + str(datetime.timedelta(seconds=round(t2-t1))))

        print2(summary, "Step 3: Generate plot and output html files.")
        promoter.plot_frequency_rna(rna=args.r, dir=args.o, ac=args.ac, cut_off=args.cf)
        #promoter.plot_de(dir=args.o)
        promoter.gen_html(directory=args.o, align=50, alpha=args.a)
        t3 = time.time()
        print2(summary, "\tRunning time is : " + str(datetime.timedelta(seconds=round(t3-t2))))
        print2(summary, "\nTotal running time is : " + str(datetime.timedelta(seconds=round(t3-t0))))
    
        output_summary(summary, args.o, "summary.log")
    ################################################################################
    ##### Random ###################################################################
    ################################################################################
    if args.mode == 'randomtest':
        print2(summary, "\n"+h_random)
        args.r = os.path.normpath(os.path.join(dir,args.r))
        args.o = os.path.normpath(os.path.join(dir,args.o))
        check_dir(args.o)
        
        randomtest = RandomTest(rna_fasta=args.r, dna_region=args.d, organism=args.organism)

        randomtest.target_dna(temp=args.o, remove_temp=args.rt)
        randomtest.random_test(repeats=args.n, temp=args.o, remove_temp=args.rt)
