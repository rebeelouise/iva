import inspect
import sys
import subprocess
import os
import shutil
import iva
import fastaq

class Error (Exception): pass


def build_kraken_virus_db(outdir, threads=1, minimizer_len=13, max_db_size=4):
    tasks = [
        ('kraken-build --download-taxonomy --db ' + outdir, 'progress.kraken-build.taxonomy.done'),
        ('kraken-build --download-library viruses --db ' + outdir, 'progress.kraken-build.library.done'),
        (' '.join([
            'kraken-build --build',
            '--db', outdir,
            '--max-db-size', str(max_db_size),
            '--minimizer-len', str(minimizer_len),
            '--threads', str(threads)
        ]), 'progress.kraken-build.build.done'),
        ('kraken-build --clean --db ' + outdir, 'progress.kraken-build.clean.done')
    ]

    for cmd, done_file in tasks:
        if os.path.exists(done_file):
            print('Skipping ', cmd, flush=True)
        else:
            print('Running:', cmd, flush=True)
            subprocess.check_output(cmd, shell=True)
            subprocess.check_output('touch ' + done_file, shell=True)


def get_genbank_virus_files(outdir):
    try:
        os.mkdir(outdir)
    except:
        raise Error('Error mkdir ' + outdir)

    cwd = os.getcwd()
    os.chdir(outdir)
    cmd = 'wget -q ftp://ftp.ncbi.nlm.nih.gov/genomes/Viruses/all.gbk.tar.gz'
    subprocess.check_output(cmd, shell=True)
    subprocess.check_output('tar -xf all.gbk.tar.gz', shell=True)
    os.chdir(cwd)


def make_embl_files(indir):
    original_dir = os.getcwd()
    this_module_dir =os.path.dirname(inspect.getfile(inspect.currentframe()))
    genbank2embl = os.path.abspath(os.path.join(this_module_dir, 'ratt', 'genbank2embl.pl'))

    for directory, x, gbk_files in sorted(os.walk(indir)):
        if directory == indir or len(gbk_files) == 0:
            continue
        os.chdir(directory)
        print('Converting', directory, end=' ', flush=True)
        for fname in gbk_files:
            # some genbank files have a 'CONTIG' line, which breaks bioperl's
            # conversion genbank --> embl and makes genbank2embl.pl hang
            subprocess.check_output('grep -v CONTIG ' + fname + ' > tmp.gbk; mv tmp.gbk ' + fname, shell=True)
            cmd = genbank2embl + ' ' + fname + ' ' + fname + '.embl'
            subprocess.check_output(cmd, shell=True, stderr=subprocess.DEVNULL)
            os.unlink(fname)
            print(fname, end=' ', flush=True)

        os.chdir(original_dir)
        print()

    os.chdir(original_dir)


def setup_ref_db(outdir, threads=1, minimizer_len=13, max_db_size=3):
    final_done_file = 'progress.setup.done'
    embl_done_file = 'progess.embl.done'
    outdir = os.path.abspath(outdir)
    if not os.path.exists(outdir):
        try:
            os.mkdir(outdir)
        except:
            raise Error('Error mkdir ' + outdir)

    cwd = os.getcwd()

    try:
        os.chdir(outdir)
    except:
        raise Error('Error chdir ' + outdir)

    if os.path.exists(final_done_file):
        print('Nothing to do! All files made already')
        return

    kraken_dir = 'Kraken_db'
    embl_dir = 'Library'

    if os.path.exists('progress.kraken-build.clean.done'):
        print('Kraken database already made. Skipping.')
    else:
        build_kraken_virus_db(kraken_dir, threads=threads, minimizer_len=minimizer_len, max_db_size=max_db_size)


    if os.path.exists(embl_done_file):
        print('EMBL/fasta files made already. Skipping.', flush=True)
    else:
        if os.path.exists(embl_dir):
            shutil.rmtree(embl_dir)
        print('Downloading virus genbank files', flush=True)
        get_genbank_virus_files(embl_dir)
        print('...finished. Making EMBL and fasta files', flush=True)
        make_embl_files(embl_dir)
        subprocess.check_output('touch ' + embl_done_file, shell=True)

    subprocess.check_output('touch ' + final_done_file, shell=True)
    os.chdir(cwd)


def run_kraken(database, reads, outprefix, preload=True, threads=1, mate_reads=None):
    kraken_out = outprefix + '.out'
    kraken_report = outprefix + '.report'
    cmd = ' '.join([
        'kraken',
        '--db', database,
        '--preload' if preload else '',
        '--threads', str(threads),
        '--output', kraken_out
    ])

    if mate_reads is not None:
        cmd += ' --paired ' + reads + ' ' + mate_reads
    else:
        cmd += ' ' + reads

    subprocess.check_output(cmd, shell=True, stderr=subprocess.DEVNULL)

    cmd = ' '.join([
        'kraken-report',
        '--db', database,
        kraken_out,
        '>', kraken_report
    ])
    subprocess.check_output(cmd, shell=True, stderr=subprocess.DEVNULL)
    os.unlink(kraken_out)


def get_most_common_species(kraken_out):
    f = fastaq.utils.open_file_read(kraken_out)
    max_count = -1
    species = None
    for line in f:
        a = line.rstrip().split()
        if a[3] == "S" and int(a[2]) > max_count:
            species = '_'.join(a[5:])
            max_count = int(a[2])

    fastaq.utils.close(f)
    return species.replace('-', '_')


def _dir_from_species(lib_dir, species):
    dirs = [x for x in os.listdir(lib_dir) if x.rsplit('_', 1)[0] == species]
    if len(dirs) == 0:
        raise Error('Error finding EMBL files directory from species "' + species + '". Cannot continue')
    elif len(dirs) > 1:
        print('Warning: >1 directory for species "' + species + '".\n' + dirs + '\n. Using ' + dirs[0])
    return os.path.join(lib_dir, dirs[0])


def choose_reference(root_dir, reads, outprefix, preload=True, threads=1, mate_reads=None):
    root_dir = os.path.abspath(root_dir)
    kraken_db = os.path.join(root_dir, 'Kraken_db')
    run_kraken(kraken_db, reads, outprefix, preload=preload, threads=threads, mate_reads=None)
    species = get_most_common_species(outprefix + '.report')
    lib_dir = os.path.join(root_dir, 'Library')
    return _dir_from_species(lib_dir, species)

