
import argparse
import subprocess as subp
import os
import gzip
from time import gmtime, strftime
import matplotlib
matplotlib.use('Agg')
import numpy as np
import matplotlib.pyplot as plt
from pylab import rcParams

def parse_args():
    parser = argparse.ArgumentParser(description='3DChromatin_ReplicateQC main script')

    #individual parsers
    metadata_samples_parser=argparse.ArgumentParser(add_help=False)
    metadata_samples_parser.add_argument('--metadata_samples',required=True,help='required. A file where each row represents a sample, and the entries are "samplename samplefile". Each of these will be processed. Note: each samplename in the file MUST be unique. Each samplefile listed here should follow the format "chr1 bin1 chr2 bin2 value"')

    metadata_pairs_parser=argparse.ArgumentParser(add_help=False)
    metadata_pairs_parser.add_argument('--metadata_pairs',required=True,help='required. Each row is a pair of sample names to be compared, in the format "samplename1 samplename2". Important: sample names used here need to correspond to the first column of the --metadata_samples file.')

    bins_parser=argparse.ArgumentParser(add_help=False)
    bins_parser.add_argument('--bins',required=True,help='required. A (gzipped) bed file of the all bins used in the analysis. It should have 4 columns: "chr start end name", where the name of the bin corresponds to the bins used in the contact maps. For each chromosome, the bins must be ordered by their genomic position, which can be done with \"sort -k1,1 -k2,2n in.bed > in.sorted.bed\"')

    re_fragments_parser=argparse.ArgumentParser(add_help=False)
    re_fragments_parser.add_argument('--re_fragments',action='store_true',help='Add this flag if the bins are not uniform bins in the genome (e.g. if they are restriction-fragment-based). By default, the code assumes the bins are of uniform length.')

    outdir_parser=argparse.ArgumentParser(add_help=False)
    outdir_parser.add_argument('--outdir',default='replicateQC',required=True,help='Name of output directory. DEFAULT: replicateQC')
    
    parameter_file_parser=argparse.ArgumentParser(add_help=False)
    parameter_file_parser.add_argument('--parameters_file',help='File with parameters for reproducibility and QC analysis. See the documentation for details.')

    concise_analysis_parser=argparse.ArgumentParser(add_help=False)
    concise_analysis_parser.add_argument('--concise_analysis',action='store_true',help='Set this flag to obtain a concise analysis, which means replicateQC is measured but plots that might be more time/memory consuming are not created.')

    running_mode_parser=argparse.ArgumentParser(add_help=False)
    running_mode_parser.add_argument('--running_mode',default='NA',help='The mode in which to run the analysis. This allows you to choose whether the analysis will be run as is, or submitted as a job through sge or slurm. Available options are: "NA" (default, no jobs are submitted), "sge", "slurm"')

    subset_chromosomes_parser=argparse.ArgumentParser(add_help=False)
    subset_chromosomes_parser.add_argument('--subset_chromosomes',default='NA',help='Comma-delimited list of chromosomes for which you want to run the analysis. By default the analysis runs on all chromosomes for which there are data. This is useful for quick testing')

    #TODO: parameters for scge, slurm
    #TODO: jobs waiting for each other
    methods_parser=argparse.ArgumentParser(add_help=False)
    methods_parser.add_argument('--methods',default='all',help='Which method to use for measuring concordance or QC. Comma-delimited list. Possible methods: "GenomeDISCO", "HiCRep", "HiC-Spector", "QuASAR-Rep", "QuASAR-QC". By default all methods are run') 

    subparsers = parser.add_subparsers(help='3DChromatin_ReplicateQC help', dest='command')
    subparsers.required = True #http://bugs.python.org/issue9253#msg186387

    #parsers for commands
    all_parser=subparsers.add_parser('run_all',
                                     parents=[metadata_samples_parser,metadata_pairs_parser,bins_parser,re_fragments_parser,methods_parser,parameter_file_parser,outdir_parser,running_mode_parser,concise_analysis_parser,subset_chromosomes_parser],
                            help='Run all steps in the reproducibility/QC analysis with this single command')

    split_parser=subparsers.add_parser('split',
                                       parents=[metadata_samples_parser,bins_parser,re_fragments_parser,methods_parser,outdir_parser,running_mode_parser,subset_chromosomes_parser],
                            help='(step 1) split files by chromosome')

    qc_parser=subparsers.add_parser('qc',
                                    parents=[metadata_samples_parser,methods_parser,parameter_file_parser,outdir_parser,running_mode_parser,concise_analysis_parser,subset_chromosomes_parser],
                                    help='(step 2.a) compute QC per sample')

    reproducibility_parser=subparsers.add_parser('reproducibility',
                                                 parents=[metadata_pairs_parser,methods_parser,parameter_file_parser,outdir_parser,running_mode_parser,concise_analysis_parser,subset_chromosomes_parser],
                                                 help='(step 2.b) compute reproducibility of replicate pairs')

    summary_parser=subparsers.add_parser('summary',
                                           parents=[metadata_samples_parser,metadata_pairs_parser,bins_parser,re_fragments_parser,methods_parser,parameter_file_parser,outdir_parser,running_mode_parser,concise_analysis_parser,subset_chromosomes_parser],
                            help='(step 3) create html report of the results')

    args = vars(parser.parse_args())
    command = args.pop("command", None)
    return command, args

def write_resolution(nodes,resolution_filename):
    resolution_file=open(resolution_filename,'w')
    node_sizes=[]
    for line in gzip.open(nodes,'r'):
        items=line.strip().split('\t')
        chromo,start,end,name=items[0],items[1],items[2],items[3]
        node_sizes.append(int(end)-int(start))
    resolution=int(np.median(np.array(node_sizes)))
    resolution_file.write(str(resolution)+'\n')

def quasar_makePartition(outdir,nodes,resolution,restriction_fragment_level,subset_chromosomes,running_mode):
    quasar_data=outdir+'/data/forQuASAR'
    subp.check_output(['bash','-c','mkdir -p '+quasar_data])
    nodes_partition=quasar_data+'/nodes.partition'
    partition_script_file=outdir+'/scripts/forQuASAR/QuASARpartition.sh'
    subp.check_output(['bash','-c','mkdir -p '+os.path.dirname(partition_script_file)])
    partition_script=open(partition_script_file,'w')
    partition_script.write("#!/bin/sh"+'\n')
    partition_script.write('source '+bashrc_file+'\n')
    re_text=''
    if restriction_fragment_level==True:
        re_text=' --re'
    partition_script.write('${mypython} '+os.path.dirname(os.path.realpath(__file__))+"/software/make_partition_from_bedfile.py --nodes "+nodes+' --partition '+nodes_partition+' --subset_chromosomes '+subset_chromosomes+' --resolution '+resolution+re_text+'\n')
    partition_script.close()
    run_script(partition_script_file,running_mode)

def quasar_makeDatasets(metadata_samples,outdir,subset_chromosomes,resolution,running_mode):
    quasar_data=outdir+'/data/forQuASAR'
    nodes_partition=quasar_data+'/nodes.partition'
    script_forquasar_file=outdir+'/scripts/forQuASAR/QuASARmakeData.sh'
    subp.check_output(['bash','-c','mkdir -p '+os.path.dirname(script_forquasar_file)])
    script_forquasar=open(script_forquasar_file,'w')
    script_forquasar.write("#!/bin/sh"+'\n')
    script_forquasar.write('source '+bashrc_file+'\n')
    for line in open(metadata_samples,'r').readlines():
        items=line.strip().split()
        samplename=items[0]
        samplefile=items[1]
        full_dataset=quasar_data+'/'+samplename+'.fulldata.gz'
        quasar_output=quasar_data+'/'+samplename+'.quasar_data'
        quasar_project=quasar_data+'/'+samplename+'.quasar_project'
        quasar_transform=quasar_data+'/'+samplename+'.quasar_transform'
        if subset_chromosomes=='NA':
            #all chromosomes                                                                                           
            script_forquasar.write('zcat -f  '+samplefile+' | sed \'s/chr//g\' | awk \'{print "chr"$1"\\t"$2"\\tchr"$3"\\t"$4"\\t"$5}\' | gzip > '+full_dataset+'\n')
        else:
            script_forquasar.write('rm '+full_dataset+'\n')
            for chromosome in subset_chromosomes.split(','):
                #TODO: keep inter-chromosomals                                                                         
                script_forquasar.write('zcat -f  '+samplefile+' | awk \'{print "chr"$1"\t"$2"\tchr"$3"\t"$4"\t"$5}\' | sed \'s/chrchr/chr/g\' | awk -v chromo='+chromosome+' \'{if (($1==$3) && ($1==chromo)) print $0}\' >> '+full_dataset+'.tmp'+'\n')
            script_forquasar.write('zcat -f  '+full_dataset+'.tmp | gzip > '+full_dataset+'\n')
            script_forquasar.write('rm '+full_dataset+'.tmp'+'\n')

        #make quasar dataset
        script_forquasar.write('${mypython} '+os.path.dirname(os.path.realpath(__file__))+"/software/encode_data_to_hifive.py "+full_dataset+" "+nodes_partition+' '+quasar_output+'\n')
        script_forquasar.write('rm '+full_dataset+'\n')
        
        #make project
        script_forquasar.write('${mypython} -c "import hifive; hic=hifive.HiC(\''+quasar_project+'\',\'w\'); hic.load_data(\''+quasar_output+'\');hic.filter_fends(mininteractions=1); hic.save()"'+'\n')

        #quasar tranformation
        script_forquasar.write('${mypython} '+os.path.dirname(os.path.realpath(__file__))+'/software/hifive/bin/find_quasar_transform '+quasar_project+' '+quasar_transform+' -r '+resolution+'\n')

        #plot the quasar transformation
        script_forquasar.write('${mypython} '+os.path.dirname(os.path.realpath(__file__))+'/software/plot_quasar_transform.py --transform '+quasar_transform+' --out '+quasar_transform+'\n')

        #remove intermediate files
        script_forquasar.write('rm '+full_dataset+' '+quasar_output+' '+quasar_project+'\n')

    script_forquasar.close()
    run_script(script_forquasar_file,running_mode)

def split_by_chromosome(metadata_samples,bins,re_fragments,methods,outdir,running_mode,subset_chromosomes):
    nodes=os.path.abspath(bins)
    outdir=os.path.abspath(outdir)
    metadata_samples=os.path.abspath(metadata_samples)
    methods_list=methods.split(',')

    #make the directory structure for the reproducibility analysis
    subp.check_output(['bash','-c','mkdir -p '+outdir+'/scripts'])
    subp.check_output(['bash','-c','mkdir -p '+outdir+'/data/metadata'])
    subp.check_output(['bash','-c','mkdir -p '+outdir+'/data/edges'])
    subp.check_output(['bash','-c','mkdir -p '+outdir+'/data/nodes'])
    subp.check_output(['bash','-c','mkdir -p '+outdir+'/results'])
    
    #make a list of all the chromosomes in the nodes file
    subp.check_output(['bash','-c','zcat -f '+nodes+' | cut -f1 | sort | uniq | awk \'{print "chr"$0}\' | sed \'s/chrchr/chr/g\' | gzip > '+outdir+'/data/metadata/chromosomes.gz'])
    #figure out resolution here and use it in the other steps
    resolution_file=outdir+'/data/metadata/resolution.txt'
    write_resolution(nodes,resolution_file)
    resolution=open(resolution_file,'r').readlines()[0].split()[0]

    if 'QuASAR-QC' in methods_list or 'QuASAR-Rep' in methods_list:
        #make nodes for quasar
        quasar_makePartition(outdir,nodes,resolution,re_fragments,subset_chromosomes,running_mode)
        #create hifive datasets from original files (genomewide)
        quasar_makeDatasets(metadata_samples,outdir,subset_chromosomes,resolution,running_mode)

    if 'GenomeDISCO' in methods_list or 'HiCRep' in methods_list or 'HiC-Spector' in methods_list:
        #split the data into chromosomes
        for chromo_line in gzip.open(outdir+'/data/metadata/chromosomes.gz','r').readlines():
            chromo=chromo_line.strip()
            if subset_chromosomes!='NA':
                if chromo not in subset_chromosomes.split(','):
                    continue
            #nodes ===============
            script_nodes_file=outdir+'/scripts/split/nodes/'+chromo+'.nodes.split_files_by_chromosome.sh'
            subp.check_output(['bash','-c','mkdir -p '+os.path.dirname(script_nodes_file)])
            script_nodes=open(script_nodes_file,'w')
            script_nodes.write("#!/bin/sh"+'\n')
            script_nodes.write('source '+bashrc_file+'\n')
            nodefile=outdir+'/data/nodes/nodes.'+chromo+'.gz'

            print '3DChromatin_ReplicateQC | '+strftime("%c")+' | Splitting nodes '+chromo

            script_nodes.write("zcat -f "+nodes+' | awk \'{print "chr"$1"\\t"$2"\\t"$3"\\t"$4"\\tincluded"}\' | sed \'s/chrchr/chr/g\' | awk -v chromosome='+chromo+' \'{if ($1==chromosome) print $0}\' | gzip > '+nodefile+'\n')

            script_nodes.close()
            run_script(script_nodes_file,running_mode)

            #edges =====================
            for line in open(metadata_samples,'r').readlines():
                items=line.strip().split()
                samplename=items[0]
                
                print '3DChromatin_ReplicateQC | '+strftime("%c")+' | Splitting '+samplename+' '+chromo

                samplefile=items[1]
                script_edges_file=outdir+'/scripts/split/'+samplename+'/'+chromo+'.'+samplename+'.split_files_by_chromosome.sh'
                subp.check_output(['bash','-c','mkdir -p '+os.path.dirname(script_edges_file)])
                script_edges=open(script_edges_file,'w')
                script_edges.write("#!/bin/sh"+'\n')
                script_edges.write('source '+bashrc_file+'\n')
                edgefile=outdir+'/data/edges/'+samplename+'/'+samplename+'.'+chromo+'.gz'
                script_edges.write('mkdir -p '+os.path.dirname(edgefile)+'\n')
                script_edges.write('zcat -f '+samplefile+' | awk \'{print "chr"$1"\\t"$2"\\tchr"$3"\\t"$4"\\t"$5}\' | sed \'s/chrchr/chr/g\' | awk -v chromosome='+chromo+' \'{if ($1==chromosome && $3==chromosome) print $2"\\t"$4"\\t"$5}\' | gzip > '+edgefile+'\n')
                script_edges.close()
                run_script(script_edges_file,running_mode)

def run_script(script_name,running_mode):
    subp.check_output(['bash','-c','chmod 755 '+script_name])
    if running_mode=='NA':
        output=subp.check_output(['bash','-c',script_name])
        if output!='':
            print output
    if running_mode=='write_script':
        pass
    if running_mode=='sge':
        memo='3G'
        output=subp.check_output(['bash','-c','qsub -l h_vmem='+memo+' -o '+script_name+'.o -e '+script_name+'.e '+script_name])
    #TODO: if you choose slurm, then you need to change the settings and provide a file with settings
    if running_mode=='slurm':
        memo='50G'
        partition='akundaje'
        output=subp.check_output(['bash','-c','sbatch --mem '+memo+' -o '+script_name+'.o -e '+script_name+'.e'+' -p '+partition+' '+script_name])

def read_parameters_file(parameters_file):
    parameters={}
    for line in open(parameters_file,'r').readlines():
        items=line.strip().split('\t')
        method_name,param_name,param_value=items[0],items[1],items[2]
        if method_name not in parameters:
            parameters[method_name]={}
        parameters[method_name][param_name]=param_value
    return parameters

def QuASAR_rep_wrapper(outdir,parameters,samplename1,samplename2,running_mode):
    script_comparison_file=outdir+'/scripts/QuASAR-Rep/'+samplename1+'.vs.'+samplename2+'/'+samplename1+'.vs.'+samplename2+'.QuASAR-Rep.sh'
    subp.check_output(['bash','-c','mkdir -p '+os.path.dirname(script_comparison_file)])
    script_comparison=open(script_comparison_file,'w')
    script_comparison.write("#!/bin/sh"+'\n')
    script_comparison.write('source '+bashrc_file+'\n')
    outpath=outdir+'/results/QuASAR-Rep/'+samplename1+'.vs.'+samplename2+'/'+samplename1+'.vs.'+samplename2+'.QuASAR-Rep.scores.txt'
    subp.check_output(['bash','-c','mkdir -p '+os.path.dirname(outpath)])
    quasar_data=outdir+'/data/forQuASAR'
    quasar_transform1=quasar_data+'/'+samplename1+'.quasar_transform'
    quasar_transform2=quasar_data+'/'+samplename2+'.quasar_transform'
    script_comparison.write('${mypython} '+os.path.abspath(os.path.dirname(os.path.realpath(__file__)))+"/software/hifive/bin/find_quasar_replicate_score"+' '+quasar_transform1+' '+quasar_transform2+' '+outpath+'\n') 
    script_comparison.write('${mypython} '+os.path.abspath(os.path.dirname(os.path.realpath(__file__)))+"/software/plot_quasar_scatter.py"+' '+quasar_transform1+' '+quasar_transform2+' '+outpath+'\n')
    script_comparison.close()
    run_script(script_comparison_file,running_mode)

def quasar_qc_wrapper(outdir,parameters,samplename,running_mode):
    script_comparison_file=outdir+'/scripts/QuASAR-QC/'+samplename+'/'+samplename+'.QuASAR-QC.sh'
    subp.check_output(['bash','-c','mkdir -p '+os.path.dirname(script_comparison_file)])
    script_comparison=open(script_comparison_file,'w')
    script_comparison.write("#!/bin/sh"+'\n')
    script_comparison.write('source '+bashrc_file+'\n')
    outpath=outdir+'/results/QuASAR-QC/'+samplename+'/'+samplename+'QuASAR-QC.scores.txt'
    subp.check_output(['bash','-c','mkdir -p '+os.path.dirname(outpath)])
    script_comparison.write('${mypython} '+os.path.abspath(os.path.dirname(os.path.realpath(__file__))+"/software/hifive/bin/find_quasar_quality_score")+' '+quasar_transform+' '+outpath+'\n')
    script_comparison.close()
    run_script(script_comparison_file,running_mode)

def HiCRep_wrapper(outdir,parameters,concise_analysis,samplename1,samplename2,chromo,running_mode,f1,f2,nodefile):
    script_comparison_file=outdir+'/scripts/HiCRep/'+samplename1+'.'+samplename2+'/'+chromo+'.'+samplename1+'.vs.'+samplename2+'.sh'
    subp.check_output(['bash','-c','mkdir -p '+os.path.dirname(script_comparison_file)])
    script_comparison=open(script_comparison_file,'w')
    script_comparison.write("#!/bin/sh"+'\n')
    script_comparison.write('source '+bashrc_file+'\n')
    if os.path.isfile(f1) and os.path.getsize(f1)>20:
        if os.path.isfile(f2) and os.path.getsize(f2)>20:
            outpath=outdir+'/results/HiCRep/'+samplename1+'.vs.'+samplename2+'/'+chromo+'.'+samplename1+'.vs.'+samplename2+'.scores.txt'
            subp.check_output(['bash','-c','mkdir -p '+os.path.dirname(outpath)])
            hicrepcode=os.path.abspath(os.path.dirname(os.path.realpath(__file__))+"/software/HiCRep_wrapper.R")
            script_comparison.write("Rscript "+hicrepcode+' '+f1+' '+f2+' '+outpath+' '+parameters['HiCRep']['maxdist']+' '+parameters['HiCRep']['resolution']+' '+nodefile+' '+parameters['HiCRep']['h']+' '+samplename1+' '+samplename2+'\n')
            script_comparison.close()
            run_script(script_comparison_file,running_mode)
    
def HiCSpector_wrapper(metadata_pairs,outdir,parameters,concise_analysis,samplename1,samplename2):
    pass

def GenomeDISCO_wrapper(outdir,parameters,concise_analysis,samplename1,samplename2,chromo,running_mode,f1,f2,nodefile):
    script_comparison_file=outdir+'/scripts/GenomeDISCO/'+samplename1+'.'+samplename2+'/'+chromo+'.'+samplename1+'.'+samplename2+'.sh'                     
                          
    subp.check_output(['bash','-c','mkdir -p '+os.path.dirname(script_comparison_file)])              
    script_comparison=open(script_comparison_file,'w')                                                
    script_comparison.write("#!/bin/sh"+'\n')                                                         
    script_comparison.write('source '+bashrc_file+'\n')                                               
    if os.path.isfile(f1) and os.path.getsize(f1)>20:                                                 
        if os.path.isfile(f2) and os.path.getsize(f2)>20:                                             
            concise_analysis_text=''                                                                  
            if concise_analysis:                                                                      
                concise_analysis_text=' --concise_analysis'                                           
            #get the sample that goes for subsampling
            subsampling=parameters['GenomeDISCO']['subsampling']
            if parameters['GenomeDISCO']['subsampling']!='NA' and parameters['GenomeDISCO']['subsampling']!='lowest':
                subsampling_sample=parameters['GenomeDISCO']['subsampling']
                subsampling=outdir+'/data/edges/'+subsampling_sample+'/'+subsampling_sample+'.'+chromo+'.gz'

            outpath=outdir+'/results/GenomeDISCO/'+samplename1+'.vs.'+samplename2                     
            subp.check_output(['bash','-c','mkdir -p '+outpath])                                      
            script_comparison.write("$mypython -W ignore "+os.path.abspath(os.path.dirname(os.path.dirname(os.path.realpath(__file__)))+"/genomedisco/compute_reproducibility.py")+" --m1 "+f1+" --m2 "+f2+" --m1name "+samplename1+" --m2name "+samplename2+" --node_file "+nodefile+" --outdir "+outpath+" --outpref "+chromo+" --m_subsample "+subsampling+" --approximation 10000000 --norm "+parameters['GenomeDISCO']['norm']+" --method RandomWalks "+" --tmin "+parameters['GenomeDISCO']['tmin']+" --tmax "+parameters['GenomeDISCO']['tmax']+concise_analysis_text+'\n')                                               
            script_comparison.close()                                                                 
            run_script(script_comparison_file,running_mode) 

def compute_reproducibility(metadata_pairs,methods,parameters_file,outdir,running_mode,concise_analysis,subset_chromosomes):
    methods_list=methods.split(',')
    parameters=read_parameters_file(parameters_file)

    outdir=os.path.abspath(outdir)
    metadata_pairs=os.path.abspath(metadata_pairs)

    for line in open(metadata_pairs,'r').readlines():                                                     
        items=line.strip().split()                                                                       
        samplename1,samplename2=items[0],items[1]
        for chromo_line in gzip.open(outdir+'/data/metadata/chromosomes.gz','r').readlines():               
            chromo=chromo_line.strip()
            if subset_chromosomes!='NA':
                if chromo not in subset_chromosomes.split(','):
                    continue

            f1=outdir+'/data/edges/'+samplename1+'/'+samplename1+'.'+chromo+'.gz'
            f2=outdir+'/data/edges/'+samplename2+'/'+samplename2+'.'+chromo+'.gz'
            nodefile=outdir+'/data/nodes/nodes.'+chromo+'.gz'

            if "GenomeDISCO" in methods_list:
                print strftime("%c")+'\n'+'running GenomeDISCO | computing reproducibility for '+samplename1+'.vs.'+samplename2+' '+chromo
                GenomeDISCO_wrapper(outdir,parameters,concise_analysis,samplename1,samplename2,chromo,running_mode,f1,f2,nodefile)

            if "HiCRep" in methods_list:
                print strftime("%c")+'\n'+'running HiCRep | computing reproducibility for '+samplename1+'.vs.'+samplename2+' '+chromo
                HiCRep_wrapper(outdir,parameters,concise_analysis,samplename1,samplename2,chromo,running_mode,f1,f2,nodefile)

            if "HiC-Spector" in methods_list:
                print strftime("%c")+'\n'+'running HiC-Spector | computing reproducibility for '+samplename1+'.vs.'+samplename2+' '+chromo
                print "coming soon"

            if "QuASAR-Rep" in methods_list:
                print strftime("%c")+'\n'+'running QuASAR-Rep | computing reproducibility for '+samplename1+'.vs.'+samplename2+' (running on all chromosomes at once)'
                QuASAR_rep_wrapper(outdir,parameters,samplename1,samplename2,running_mode)

def get_qc(metadata_samples,methods,parameter_file,outdir,running_mode,concise_analysis,subset_chromosomes):
    pass

def summary(metadata_samples,metadata_pairs,bins,re_fragments,methods,parameters_file,outdir,running_mode,concise_analysis,subset_chromosomes):
    
    methods_list=methods.split(',')

    #compile scores across methods per chromosome, + genomewide
    scores={}
    subp.check_output(['bash','-c','mkdir -p '+outdir+'/results/summary'])
    for method in methods_list:
        if method=="QuASAR-QC":
            continue
        scores[method]={}
        subp.check_output(['bash','-c','mkdir -p '+outdir+'/results/summary/'+method])
        for line in open(metadata_pairs,'r').readlines():
            items=line.strip().split()
            samplename1,samplename2=items[0],items[1]
            scores[method][samplename1+'.vs.'+samplename2]={}
            for chromo_line in gzip.open(outdir+'/data/metadata/chromosomes.gz','r').readlines():
                chromo=chromo_line.strip()
                if subset_chromosomes!='NA':
                    if chromo not in subset_chromosomes.split(','):
                        continue
            
                pair_text=samplename1+'.vs.'+samplename2+'/'+chromo+'.'+samplename1+'.vs.'+samplename2+'.scores.txt'
                current_score=float(open(outdir+'/results/'+method+'/'+pair_text,'r').readlines()[0].strip().split('\t')[2])
                scores[method][samplename1+'.vs.'+samplename2][chromo]=current_score
                if 'genomewide_list' not in scores[method][samplename1+'.vs.'+samplename2].keys():
                    scores[method][samplename1+'.vs.'+samplename2]['genomewide_list']=[]
                scores[method][samplename1+'.vs.'+samplename2]['genomewide_list'].append(current_score)

        for chromo_line in gzip.open(outdir+'/data/metadata/chromosomes.gz','r').readlines():
            chromo=chromo_line.strip()
            if subset_chromosomes!='NA':
                if chromo not in subset_chromosomes.split(','):
                    continue
            chromofile=open(outdir+'/results/summary/'+method+'/'+method+'.'+chromo+'.txt','w')
            chromofile.write('#Sample1\tSample2\tScore'+'\n')
            for line in open(metadata_pairs,'r').readlines():
                items=line.strip().split()
                samplename1,samplename2=items[0],items[1]
                chromofile.write(samplename1+'\t'+samplename2+'\t'+str(scores[method][samplename1+'.vs.'+samplename2][chromo])+'\n')
            chromofile.close()
            print outdir+'/results/summary/'+method+'/'+method+'.'+chromo+'.txt'

        genomewide_file=open(outdir+'/results/summary/'+method+'/'+method+'.genomewide.txt','w')
        for line in open(metadata_pairs,'r').readlines():
            items=line.strip().split()
            samplename1,samplename2=items[0],items[1]
            genomewide_file.write(samplename1+'\t'+samplename2+'\t'+str(np.mean(np.array(scores[method][samplename1+'.vs.'+samplename2]['genomewide_list'])))+'\n')
        genomewide_file.close()

        '''
        #make the heatmap
        heatmap_script_file=outdir+'/results/summary/heatmap.sh'
        heatmap_script=open(heatmap_script_file,'w')
        heatmap_script.write("#!/bin/sh"+'\n')
        heatmap_script.write('source '+bashrc_file+'\n')
        heatmap_script.write("Rscript "+os.path.abspath(os.path.dirname(os.path.realpath(__file__))+"/scripts/plot_score_heatmap.R")+' '+outdir+'/results/summary/'+method+'/'+method+'.genomewide.txt'+' '+outdir+'/results/summary/'+method+'/'+method+'.genomewide.pdf'+'\n')
        heatmap_script.close()
        run_script(heatmap_script_file,'NA')
        '''

def run_all(metadata_samples,metadata_pairs,bins,re_fragments,methods,parameter_file,outdir,running_mode,concise_analysis,subset_chromosomes):
    split_by_chromosome(metadata_samples,bins,re_fragments,methods,outdir,running_mode,subset_chromosomes)
    get_qc(metadata_samples,methods,parameter_file,outdir,running_mode,concise_analysis,subset_chromosomes)
    compute_reproducibility(metadata_pairs,methods,parameter_file,outdir,running_mode,concise_analysis,subset_chromosomes)
    summary(metadata_samples,metadata_pairs,bins,re_fragments,methods,parameter_file,outdir,running_mode,concise_analysis,subset_chromosomes)

def main():
    command_methods = {'split': split_by_chromosome,
                       'qc': get_qc,
                         'reproducibility': compute_reproducibility,
                         'summary': summary,
                       'run_all': run_all}
    command, args = parse_args()

    #find bashrc file to source
    global bashrc_file
    methods_list=args['methods'].split(',')
    if "GenomeDISCO" in methods_list and len(methods_list)==1:
        bashrc_file=os.path.abspath(os.path.dirname(os.path.dirname(os.path.realpath(__file__))))+"/scripts/bashrc.genomedisco"
    else:
        bashrc_file=os.path.abspath(os.path.dirname(os.path.dirname(os.path.realpath(__file__))))+"/scripts/bashrc.all_methods"
    command_methods[command](**args)


if __name__ == "__main__":
    main()