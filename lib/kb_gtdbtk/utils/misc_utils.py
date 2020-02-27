import uuid
import errno
import os

from installed_clients.AssemblyUtilClient import AssemblyUtil
from installed_clients.DataFileUtilClient import DataFileUtil
from installed_clients.KBaseReportClient import KBaseReport
from installed_clients.MetagenomeUtilsClient import MetagenomeUtils
from installed_clients.WorkspaceClient import Workspace
from shutil import copyfile


# copied from https://github.com/kbaseapps/kb_cmash/blob/master/lib/kb_cmash/utils/misc_utils.py
# small modifications

# key of the returned map is a unique ID for the assembly data, not specified but usually
# the santitized UPA of the assembly object or a UUID
def load_fastas(config, scratch, upa):
    '''
    '''
    dfu = DataFileUtil(config['callback_url'])
    au = AssemblyUtil(config['callback_url'])
    mgu = MetagenomeUtils(config['callback_url'])
    ws = Workspace(config['workspace-url'])

    obj_data = dfu.get_objects({"object_refs": [upa]})['data'][0]
    upa = str(obj_data['info'][6]) + '/' + str(obj_data['info'][0]) + '/' + str(
        obj_data['info'][4])
    obj_type = obj_data['info'][2]

    id_to_assy_info = {}
    if 'KBaseSets.GenomeSet' in obj_type:
        upas = [gsi['ref'] for gsi in obj_data['data']['items']]
    elif 'KBaseSearch.GenomeSet' in obj_type:
        upas = [gse['ref'] for gse in obj_data['data']['elements'].values()]
    elif "KBaseGenomes.Genome" in obj_type:
        upas = [upa]
    elif "KBaseGenomes.ContigSet" in obj_type or "KBaseGenomeAnnotations.Assembly" in obj_type:
        # in this case we use the assembly file util to get the fasta file
        # file_output = os.path.join(scratch, "input_fasta.fa")
        faf = au.get_assembly_as_fasta({"ref": upa, 'filename': upa_to_path(scratch, upa)})
        return {file_safe_upa(upa): faf}
    elif "KBaseSets.AssemblySet" in obj_type:
        for item_upa in obj_data['data']['items']:
            faf = au.get_assembly_as_fasta(
                {"ref": upa + ';' + item_upa['ref'],
                 'filename': upa_to_path(scratch, item_upa['ref'])})
            id_to_assy_info[file_safe_upa(item_upa['ref'])] = faf
        return id_to_assy_info
    elif 'KBaseMetagenomes.BinnedContigs' in obj_type:
        return handle_binned_contigs(upa, mgu, scratch)
    
    for genome_upa in upas:
        # this could be sped up by batching the get_objects call
        # does assy file util not take bulk calls?
        # maybe doesn't matter since Shock doesn't handle bulk calls
        if upa != genome_upa:  # for single genomes, upa and genome_upa will be the same
            genome_upa = upa + ';' + genome_upa
        genome_data = ws.get_objects2( {'objects':[{"ref": genome_upa}]})['data'][0]['data']
        target_upa = genome_data.get('contigset_ref') or genome_data.get('assembly_ref')
        assembly_upa = genome_upa + ';' + target_upa
        faf = au.get_assembly_as_fasta({
            'ref': assembly_upa,
            'filename': upa_to_path(scratch, target_upa)
            })
        id_to_assy_info[file_safe_upa(target_upa)] = faf

    return id_to_assy_info


def handle_binned_contigs(upa, mgu, target_dir):
    # any CoaC issues here are in MetagenomeUtils
    ret = {}
    bin_file_dir = mgu.binned_contigs_to_file(
        {'input_ref': upa, 'save_to_shock': 0})['bin_file_directory']
    for (dirpath, dirnames, filenames) in os.walk(bin_file_dir):
        for fasta_file in filenames:
            # not sure why we're normalizing the extension, but that's how the old code did it
            # *shrug*
            fasta_fixed_ext = os.path.splitext(fasta_file)[0] + '.fa'
            # bin filenames can be basically anything. rename to UUID and return mapping
            id_ = str(uuid.uuid4())
            fasta_path = os.path.join(target_dir, id_)
            copyfile(os.path.join(bin_file_dir, fasta_file), fasta_path)
            # Should I verify that the bins have contigs?
            # is it possible to have empty bins?
            ret[id_] = {'path': fasta_path, 'assembly_name': fasta_fixed_ext}
        break  # not sure why this is necessary
    return ret


def upa_to_path(scratch, upa):
    return os.path.join(scratch, file_safe_upa(upa))


def file_safe_upa(upa):
    return upa.replace('/', '_')


# 3.2 and 3.5 have much improved options
# https://stackoverflow.com/questions/600268/mkdir-p-functionality-in-python
def mkdir_p(path):
    try:
        os.makedirs(path)
    except OSError as exc:  # Python ≥ 2.5
        if exc.errno == errno.EEXIST and os.path.isdir(path):
            pass
        else:
            raise


# TODO switch ws name for ws id
def create_html_report(callback_url, output_path, workspace_name):
    '''
    '''
    dfu = DataFileUtil(callback_url)
    report_name = 'GTDBTk_report_' + str(uuid.uuid4())
    report = KBaseReport(callback_url)
    copyfile(os.path.join(os.path.dirname(__file__), 'index.html'), 
             os.path.join(output_path, 'index.html'))

    report_shock_id = dfu.file_to_shock({'file_path': output_path,
                                        'pack': 'zip'})['shock_id']

    html_file = {
        'shock_id': report_shock_id,
        'name': 'index.html',
        'label': 'index.html',
        'description': 'HTML report for GTDBTk Classify'
        }
    
    report_info = report.create_extended_report({
                    'direct_html_link_index': 0,
                    'html_links': [html_file],
                    'report_object_name': report_name,
                    'workspace_name': workspace_name
                })
    return {
        'report_name': report_info['name'],
        'report_ref': report_info['ref']
    }