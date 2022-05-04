"""

 HPPMAP startup script.
"""

# Maintainer: Hiral Oza, Karthik Rajagopalan

import os
import subprocess
import sys
from shutil import copy as shutil_copy

from schrodinger.job import launcher
from schrodinger.utils import cmdline
from schrodinger.utils import fileutils

###############################Global variables ###############################
backend = "hppmap"
backendArgs = []
inpath = ""

###############################################################################


def print_usage():
    usage = """
Generate hydrophilic and phobic maps

Usage: hppmap [<options>] <jobname>

   <jobname> - file containing the input parameters
                  (may not be required in later version)

Options:
   -HOST <host> - Run job on a remote host.
   -LOCAL       - Run the job in the current directory, rather than
                    in a temporary scratch directory
   -WAIT        - Do not return until the job completes.
   -NICE        - Run the job at reduced priority.
    """

    if os.environ.get('SCHRODINGER_SRC', ""):
        usage += """
   -DEBUGGER <program>
                - Run hppmap in the foreground with the debugger
                    called <program>.
        """

    usage += """
   -HELP        - Print this message and exit.
    """

    print(usage)
    sys.exit(1)


def parse_args(argsList):
    """
    Parses the command line options
    """
    global backend, backendArgs, inpath

    parser = cmdline.SingleDashOptionParser()

    # Override the help option given by SingleDashOptionParser instance
    parser.remove_option('-h')
    parser.add_option("-HELP", action="store_true", dest="show_help")

    jc_options = [cmdline.WAIT, cmdline.DEBUG, cmdline.LOCAL, cmdline.DEBUGGER]
    cmdline.add_jobcontrol_options(parser, jc_options)

    options, otherArgs = parser.parse_args(args=argsList, ignore_unknown=True)

    if options.show_help:
        print_usage()

    for (index, item) in enumerate(otherArgs):
        if not item.startswith('-'):
            inpath = item
            backendArgs += otherArgs[index + 1:]
            break
        else:
            backendArgs += [item]

    return options


def launch_job(options):
    """
    Sets the proper environment and executes the job using job control
    """
    global backend, backendArgs, inpath

    if not inpath:
        print_usage()

    infile = os.path.basename(inpath)
    if infile != inpath:
        try:
            shutil_copy(inpath, infile)
        except Exception as err:
            print(err)

    jobname, ext = fileutils.splitext(infile)
    print("Jobname:", jobname)

    script = os.path.join(os.environ['REMOTE_MAESTRO_EXEC'], backend)
    scriptLauncher = launcher.Launcher(
        script=script,
        copyscript=False,
        jobname=jobname,
        prog='Sitemap',
        wait=options.wait,
        local=options.local,
        debugger=options.debugger)

    # set backend arguments
    scriptLauncher.addScriptArgs([infile])

    infile_exts = ['.inp', '.mae']
    for suffix in infile_exts:
        file = jobname + suffix
        scriptLauncher.addInputFile(file)
    if os.path.isfile(jobname + '_ligand.mae'):
        scriptLauncher.addInputFile(jobname + '_ligand.mae')

    outfile_exts = ['.out', '_philic.vis', '_phobic.vis']
    for suffix in outfile_exts:
        file = jobname + suffix
        scriptLauncher.addOutputFile(file)

    scriptLauncher.setStdOutErrFile(jobname + '.out')
    scriptLauncher.addLogFile(jobname + '.log')

    envs = ["SCHRODINGER=" + os.environ['REMOTE_SCHRODINGER']]
    envs += ["MAESTRO_EXEC=" + os.environ['REMOTE_MAESTRO_EXEC']]
    envs += ["MMSHARE_EXEC=" + os.environ['REMOTE_MMSHARE_EXEC']]
    for env in envs:
        scriptLauncher.addEnv(env)

    try:
        scriptLauncher.launch()
    except Exception as e:
        print("Error:", type(e))
        print(e.args)
        sys.exit(1)


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print_usage()

    opts = parse_args(sys.argv[1:])

    launch_job(opts)
#EOF
