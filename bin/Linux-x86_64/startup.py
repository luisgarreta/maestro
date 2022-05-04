"""

 Maestro Startup Script

 Copyright Schrodinger, LLC. All rights reserved.
"""
import contextlib
import enum
import glob
import io
import optparse
import os
import pathlib
import re
import shlex
import shutil
import sys
import textwrap
import time
import traceback

import probe_opengl

from schrodinger.infra import mm
from schrodinger.infra.exception_handler_dir import exception_dialog
from schrodinger.job import server
from schrodinger.job import util as jobutil
from schrodinger.Qt.QtWidgets import QMessageBox
from schrodinger.Qt.QtWidgets import QDialog
from schrodinger.ui.qt.appframework2 import application
from schrodinger.utils import cmdline
from schrodinger.utils import fileutils
from schrodinger.utils import log
from schrodinger.utils import mmutil
from schrodinger.utils import subprocess

ASTERISK_LINE = "*" * 62
BACKEND = 'maestro'
LAST_REPORTED_TIME = time.perf_counter()
LD_LIBRARY_PATH = "LD_LIBRARY_PATH"
MAESTRO_EXEC = "MAESTRO_EXEC"
# If Maestro crashes in <= this time (in seconds), then check if fonts are
# installed
MAESTRO_FONT_CRASH_TIME = 120
OS_NAME = sys.platform
RESTART_EXIT_CODE = 255
SCHRODINGER_GL = "SCHRODINGER_GL"
SCHRODINGER_TEMP_PROJECT = "SCHRODINGER_TEMP_PROJECT"
SUPPORT_ERROR_MESSAGE = mm.mmfile_get_schrodinger_support_error_mesg()

log.logging_config(level=log.logging.INFO, format="%(message)s")
logger = log.get_logger()


@enum.unique
class PROFILE(str, enum.Enum):
    MAESTRO = "Maestro"
    BIOLUMINATE = "BioLuminate"
    ELEMENTS = "Elements"
    MATERIALS_SCIENCE = "MaterialsScience"


@enum.unique
class OS(str, enum.Enum):
    OSX = "darwin"
    LINUX = "linux"
    WINDOWS = "win32"


@enum.unique
class GLOption(enum.Enum):
    FORCE_MESA = enum.auto()
    AUTODETECT = enum.auto()
    FORCE_HARDWARE = enum.auto()


def report_timing(name):
    """
    Log time since report.

    :param name: descriptive name of time report
    :type name: str
    """
    global LAST_REPORTED_TIME

    if not int(os.environ.get("MAESTRO_REPORT_STARTUP_TIMES", 0)):
        return

    time_current = time.perf_counter()
    time_delta = time_current - LAST_REPORTED_TIME
    LAST_REPORTED_TIME = time_current

    time.asctime(time.localtime())
    logger.info('{0:45}: {1:10} (cpu) {2:10}'.format(name, time_delta,
                                                     time.strftime(
                                                         "%X%p",
                                                         time.localtime())))


def create_crash_dir():
    """
    Prepare log file path and make sure that app crash directory is available.

    :return: path to directory to store crash files
    :rtype: str
    """
    crash_dir = os.path.join(
        fileutils.get_directory_path(mm.DirectoryName_MMFILE_LOCAL_APPDATA),
        "appcrash")
    if OS_NAME == OS.WINDOWS:
        # We have SCHRODINGER_CRASH_DUMP_DIR only in case of Windows.
        # In case of Linux we write it in launch directory
        crash_dir_env = os.environ.get("SCHRODINGER_CRASH_DUMP_DIR", "")
        if crash_dir_env:
            if not os.path.isabs(crash_dir_env):
                logger.error("SCHRODINGER_CRASH_DUMP_DIR environment "
                             "variable is not an absolute path.")
                crash_dir = os.path.join(
                    fileutils.get_directory_path(
                        mm.DirectoryName_MMFILE_DOCUMENTS), "Schrodinger",
                    crash_dir_env)
            else:
                crash_dir = crash_dir_env

    elif OS_NAME == OS.OSX:
        # Set the crash_dir to /Users/<user_name>/Library/Logs/CrashReporter
        # directory, if it exists. Else, set <HOME>/Library/Logs/CrashReporter
        # directory as the crash directory.
        user_name = os.environ.get("USER", "")
        crash_dir = "/Users/" + user_name + "/Library/Logs/CrashReporter"
        if not os.path.exists(crash_dir):
            crash_dir = os.path.join(
                fileutils.get_directory_path(mm.DirectoryName_MMFILE_HOME),
                "Library/Logs/CrashReporter")

    os.makedirs(crash_dir, exist_ok=True)
    return crash_dir


def get_mae_err_log(crash_dir, process_id):
    """
    Return absolute path to maestro error log file.

    :param crash_dir: path to difrectory which stores crashes
    :type crash_dir: str

    :param process_id: PID of maestro process, to match GDB dumps
    :type process_id: id

    :rtype: str
    """
    mae_err_log_file = BACKEND + f"_error_{process_id}.txt"
    return os.path.join(crash_dir, mae_err_log_file)


def _run_machid():

    # Redirect the machid output to the Maestro Error file
    logger.info("\n\n********************** Machine and Product information "
                "**********************\n")
    cmd = [os.path.join(os.environ['SCHRODINGER'], 'machid')]
    _log_command_output(cmd)

    logger.info("\n\n**************************** User Environment "
                "****************************\n")
    for k, v in os.environ.items():
        logger.info(k + '=' + v)

    logger.info("")


def _log_command_output(cmd, shell=False):
    p = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        shell=shell,
        universal_newlines=True)
    output, error = p.communicate()
    output = output.strip()
    if p.returncode:
        logger.warning("WARNING: Couldn't get output of '%s' command.\n" % cmd)
        logger.warning(output)
        logger.warning(error)
    else:
        logger.info(output)


def _showLicenseError(mae_err_log):
    """
    Show configure gui to contact technical support for license.
    And print other information in the maestro_error*.txt file.

    :param mae_err_log: pathname to the maestro error log
    :param mae_err_log: str
    """
    cmd = [os.path.join(os.environ["SCHRODINGER"], "utilities", "configure")]
    subprocess.call(cmd)
    print(ASTERISK_LINE)
    logger.info(ASTERISK_LINE)
    print("You do not have a properly installed license.")
    print(SUPPORT_ERROR_MESSAGE)
    print(mae_err_log)
    print(ASTERISK_LINE)
    logger.info(ASTERISK_LINE)


def _mae_usage():
    usage = "\nMaestro startup script supports the following options:\n" \
            "  -v        : Display versions of Maestro and mmshare.\n" \
            "              Does not run Maestro\n" \
            "  -nosplash : Skip display of Maestro splash screen\n"
    if os.environ.get('SCHRODINGER_SRC', ""):
        usage += "  -DEBUGGER <debugger_name> :\n" \
            "              Run maestro with debugger. To debug with " \
            "valgrind you can use\n" \
            "              '-DEBUGGER \"valgrind --error-limit=no\"'\n" \
            "  -memcheck : Uses debugger specified in MEMORY_CHECKER_PROG " \
            "environment\n" \
            "              variable to launch Maestro. If that environment " \
            "variable is not set\n" \
            "              uses the 'valgrind --error-limit=no' to launch " \
            "Maestro.\n" \
            "              Set MEMORY_CHECKER_PROG environment variable to " \
            "override\n" \
            "              the default memory checker.\n"
    usage += "  -lsgfx    : List graphics setting.\n"
    if OS_NAME == OS.LINUX:
        usage += "  -strace: Runs maestro under strace.\n"

    usage += "  -envvar \"MY_VAR=MY_VAR_VALUE\" :\n" \
        "              Set MY_VAR to MY_VAR_VALUE in maestro environment.\n"
    usage += "  -printenv : Print environment variables set during startup." \
             "\n\nThe options listed below are also supported:"
    usage += "  -skipjobserverregistration : Skip job server registration.\n"

    if OS_NAME == OS.LINUX:
        usage += "  -forcedriver: use driver even if it is in the blacklist\n"
    logger.info(usage)


def _show_graphics_info():
    cmd = [os.path.join(os.environ['SCHRODINGER'], 'gfxinfo')]
    _log_command_output(cmd)


def _parse_args(argsList):
    """
    Parses the command line options
    """
    parser = cmdline.SingleDashOptionParser()

    # Override the help option given by SingleDashOptionParser instance
    parser.remove_option('-h')
    parser.add_option(
        "-h", "-help", "-HELP", action="store_true", dest="show_help")
    parser.remove_option('-v')
    parser.add_option("-v", action="store_true", dest="show_version")

    jc_options = [cmdline.DEBUG, cmdline.DEBUGGER]
    cmdline.add_jobcontrol_options(parser, jc_options)

    parser.add_option("-memcheck", action="store_true", dest="memcheck")
    parser.add_option("-envvar", action="append", dest="envvar")
    parser.add_option("-printenv", action="store_true", dest="printenv")
    parser.add_option(
        "-nosplash", action="store_false", dest="splash", default=True)
    parser.add_option("-ldd", action="store_true", dest="ldd")
    parser.add_option("-lddonly", action="store_true", dest="lddonly")
    if OS_NAME == OS.WINDOWS:
        parser.add_option("-squishtest", action="store_true", dest="squish")
    parser.add_option("-lsgfx", action="store_true", dest="lsgfx")
    if OS_NAME == OS.LINUX:
        parser.add_option("-strace", action="store_true", dest="strace")
    parser.add_option("-vtune", action="store_true", dest="vtune")
    parser.add_option("-nolicpopup", action="store_true", dest="nolicpopup")
    parser.add_option("-NOSGL", action="store_true", dest="nosgl")
    parser.add_option(
        "-skipjobserverregistration",
        action="store_true",
        dest="skipjobserverregistration")

    if OS_NAME == OS.WINDOWS:
        parser.add_option(
            "-forcedriver", action="store_true", dest="ignore_bad_drivers")

    options, otherArgs = parser.parse_args(args=argsList, ignore_unknown=True)
    if options.memcheck:
        memory_checker = os.environ.get("MEMORY_CHECKER_PROG", "")
        if memory_checker:
            options.debugger = memory_checker
        else:
            if OS_NAME == OS.WINDOWS:
                raise optparse.OptionError(
                    "-NOSGL and -SGL are mutually exclusive arguments", parser)

                print(
                    "Warning: The default memchecker program is not available.")
                options.memcheck = False
            else:
                options.debugger = "valgrind --error-limit=no --leak-check=full"

    if options.printenv:
        logger.setLevel(log.logging.DEBUG)

    if options.envvar:
        for envvar_pair in options.envvar:
            if "=" in envvar_pair:
                env_var, env_value = envvar_pair.split("=", 1)
                os.environ[env_var] = env_value
                logger.debug("%s: %s" % (env_var, os.environ[env_var]))
            else:
                print("Missing '=' for name-value separator in envvar '%s'" %
                      envvar_pair)

    backend_args = []
    if not options.splash:
        backend_args += ['-nosplash']

    if options.show_help:
        _mae_usage()
        backend_args += ['-h']
        options.splash = False

    if options.show_version:
        backend_args += ['-v']
        options.splash = False

    if options.lddonly:
        options.ldd = True
        options.splash = False

    if hasattr(options, 'lsgfx') and options.lsgfx:
        _show_graphics_info()
        sys.exit(0)

    if os.environ.get(SCHRODINGER_GL):
        if options.nosgl:
            raise optparse.OptionError(
                "-NOSGL and -SGL are mutually exclusive arguments", parser)
        options.GL = GLOption.FORCE_MESA
    elif options.nosgl:
        options.GL = GLOption.FORCE_HARDWARE
    else:
        options.GL = GLOption.AUTODETECT

    if OS_NAME == OS.WINDOWS:
        if options.ldd:
            raise optparse.OptionError(
                "-ldd option is not available on Windows", parser)
        if options.lddonly:
            raise optparse.OptionError(
                "-lddonly option is not available on Windows", parser)

    backend_args += otherArgs

    return options, backend_args


def get_profile_name(args_list):
    """
    Returns the current profile from full set of arguments used to start
    maestro.

    :param args_list: arguments passed to the maestro executable
    :type args_list: list(str)

    :rtype: PROFILE
    """
    # maps profile names to possible cmdline output
    # Users can start Maestro with any of the supported aliases like:
    # $SCHRODINGER/maestro -profile MatSci
    # $SCHRODINGER/maestro -profile MaterialScience
    # $SCHRODINGER/maestro -profile MaterialsScience
    # $SCHRODINGER/maestro -profile Materials
    # $SCHRODINGER/maestro -profile Biologics
    # $SCHRODINGER/maestro -profile BioLuminate
    # $SCHRODINGER/maestro -materials
    # $SCHRODINGER/maestro -elements
    # $SCHRODINGER/maestro -bioluminate
    SPECIAL_PROFILES = {
        PROFILE.ELEMENTS: {'elements', '-elements'},
        PROFILE.BIOLUMINATE: {'bioluminate', '-bioluminate', 'biologics'},
        PROFILE.MATERIALS_SCIENCE: {
            'materials', '-materials', 'matsci', 'materialscience',
            'materialsscience'
        }
    }

    # Do case insensitive comparision to make inline with Maestro
    lowercase_args_list = [arg.lower() for arg in args_list]
    for profile_name, possible_args in SPECIAL_PROFILES.items():
        for possible_arg in possible_args:
            if possible_arg in lowercase_args_list:
                index = lowercase_args_list.index(possible_arg)
                if (index > 0 and
                    (lowercase_args_list[index - 1] == '-profile') or
                    (possible_arg == '-elements' or
                     possible_arg == '-bioluminate' or
                     possible_arg == '-materials')):
                    return profile_name
    return PROFILE.MAESTRO


def _maestro_win_dmp_file_name(crash_dir, process_id):
    """
    This is Windows specific function.
    When Maestro crashes, it goes into the Windows crash folder and looks for
    latest .dmp file generated using the pid and returns its name.
    Windows .dmp file format: maestro.exe_<pid>_<dd><month><year>_<time>.dmp

    :param crash_dir: path to directory where crash dumps are stored
    :type crash_dir: str

    :param process_id: name of current pid
    :type process_id: int
    """
    date_file_list = []
    dmp_file_name = "maestro.EXE.dmp"

    # Get all .dmp files that matches maestro.exe_<pid>_*_*.dmp pattern
    # Windows reuses the pid, so it is possible that there will be more than
    # one .dmp file with the current pid.
    pattern = crash_dir + os.path.sep + "maestro.exe_"
    pattern = pattern + f"*_*_{process_id}.dmp"
    for filename in glob.glob(pattern):
        stats = os.stat(filename)
        # Get the 8th tuple element which is mtime i.e. last modified date
        lastmod_date = time.localtime(stats[8])
        date_file_tuple = lastmod_date, filename
        date_file_list.append(date_file_tuple)

    # Sort the maestro.exe_<pid>_*_*.dmp by modification date and return the
    # last modified .dmp file that matched the pattern.
    date_file_list_len = len(date_file_list)
    if date_file_list_len > 0:
        date_file_list.sort()
        date_file_tuple = date_file_list[date_file_list_len - 1]
        dmp_file_name = os.path.basename(date_file_tuple[1])

    return dmp_file_name


def _maestro_catch(exitcode, mae_err_log, minidump_filename):
    """
    Handle error reporting from a nonzero exit code from maestro.

    :param exitcode: exit code from maestro
    :type exitcode: int

    :param mae_err_log: path to maestro error log
    :type mae_err_log: str

    :param minidump_filename: path to maestro crash dump file
    :type minidump_filename: str
    """
    _show_graphics_info()
    if OS_NAME == OS.LINUX:
        logger.info("\nShell resource limits:")
        cmd = ['ulimit', '-a']
        _log_command_output(cmd, shell=True)

    # maestro_catch is called in case of exit status as 1, but it is not a
    # crash, hence adjust error message.
    # EV 86240
    # The error message for Linux will be displayed by main.cxx itself in case
    # of crash.
    if exitcode == 1 or OS_NAME == OS.WINDOWS:
        # Note: Don't use logger as it is now redirecting output into
        # mae_err_log file.
        print("Saving Maestro Error Report in...")
        print("'%s'" % mae_err_log)
        print()
    _run_machid()
    # maestro_catch is called in case of exit status as 1, but that is not a
    # crash, hence adjust error message.
    if exitcode == 1:
        # Note: Don't use logger as it is now redirecting output into
        # mae_err_log file.
        print(ASTERISK_LINE)
        print(SUPPORT_ERROR_MESSAGE)
        print(mae_err_log)
        print(ASTERISK_LINE)
    else:
        # EV 86240
        # The error message for Linux will be displayed by main.cxx itself.
        if OS_NAME == OS.WINDOWS:
            # Note: Don't use logger as it is now redirecting output into
            # mae_err_log file.
            print(ASTERISK_LINE)
            print(SUPPORT_ERROR_MESSAGE)
            print(mae_err_log)
            print(minidump_filename)
            print(ASTERISK_LINE)

    sys.exit(1)


def get_maestro_version_dir():
    """
    Get the version specific Maestro directory name, e.g.
    maestro-v9.1 -> maestro91

    :return: name of maestro folder for ~/.schrodinger
    :rtype: str
    """
    maestro_dir = get_maestro_dir()
    pos = os.path.basename(maestro_dir).rfind('.')
    if pos < 0:
        # maestro-v91114
        pat = r".*%s-v(\d)(\d+)(\d){3}" % BACKEND
    else:
        # maestro-v9.1
        pat = r".*%s-v(\d.*).(\d.*)" % BACKEND
    p = re.compile(pat)
    ver = p.match(maestro_dir)
    return BACKEND + ver.group(1) + ver.group(2)


def _validate_and_create(tmp_prj):
    """
    Create temporary project directory.

    :param tmp_prj: path to temporary directory
    :type tmp_prj: str

    :return: True if directory is invalid
    :rtype: bool

    If SCHRODINGER_TEMP_PROJECT is not set by user, startup script should
    not create it. main.cxx will set SCHRODINGER_TEMP_PROJECT as per
    EV 66916
    """
    if tmp_prj:
        if not os.path.isabs(tmp_prj):
            logger.debug(
                f"{SCHRODINGER_TEMP_PROJECT} directory '{tmp_prj}' is not "
                "an absolute path")
            return False
        if not os.path.isdir(tmp_prj):
            logger.info("Creating directory '%s'" % tmp_prj)
            try:
                os.makedirs(tmp_prj)
            except OSError:
                logger.debug(f"Failed to create {SCHRODINGER_TEMP_PROJECT} "
                             f"directory '{tmp_prj}' for scratch projects")
                return False
        return True
    else:
        return False


def _set_tmp_prj_from_maestro_preference(profile_name):
    """
    2. Look for the preference 'tempprojectlocation' in 'prefer.cmd' file
    """
    # Frame the path to prefer.cmd file

    prefer_cmd_path = os.path.join(
        fileutils.get_directory_path(mm.DirectoryName_MMFILE_APPDATA),
        get_maestro_version_dir(), 'profiles', profile_name, 'prefer.cmd')

    tmp_prj = ""
    # Read the prefer.cmd to fetch the tempprojectlocation value
    if os.path.isfile(prefer_cmd_path):
        with open(prefer_cmd_path) as fh:
            lines = fh.readlines()
        line = [
            line for line in reversed(lines)
            if line.startswith("prefer tempprojectlocation=")
        ]
        if line:
            # Take the last instance of 'prefer tempprojectlocation=' cmd
            line = line[0]
            tmp_prj = line[line.find("=") + 1:].strip().strip('"')
            if _validate_and_create(tmp_prj):
                logger.debug("Using Maestro preference for "
                             f"{SCHRODINGER_TEMP_PROJECT}")
            else:
                # tmp_prj is invalid or could not be created, setting tmp_prj
                # to "" so that the next rule will be tried
                tmp_prj = ""
    return tmp_prj


def _set_tmp_prj_from_TMPDIR_env_var():
    """
    3. Look for TMPDIR environment variable
    """
    tmp_prj = ""
    if os.environ.get("TMPDIR", ""):
        tmp_prj = os.environ.get("TMPDIR", "")
        if OS_NAME == OS.WINDOWS:
            if os.environ.get("USERNAME", ""):
                tmp_prj = os.path.join(tmp_prj, os.environ.get("USERNAME", ""))
        else:
            if os.environ.get("USER", ""):
                tmp_prj = os.path.join(tmp_prj, os.environ.get("USER", ""))
        if _validate_and_create(tmp_prj):
            logger.debug(f"Using TMPDIR as {SCHRODINGER_TEMP_PROJECT}")
        else:
            # tmp_prj is invalid, setting tmp_prj to "" so that the next
            # rule will be tried
            tmp_prj = ""
    return tmp_prj


def _set_tmp_prj_from_schrodinger_temp_dir():
    """
    4. Fallback to ~/.schrodinger/tmp, if nothing works out.
       This is the temp path as returned by 'schrodinger_dir -temp'
    """
    tmp_prj = mm.mmfile_get_directory_path(mm.DirectoryName_MMFILE_TEMP)
    if _validate_and_create(tmp_prj):
        logger.debug(f"Using default for {SCHRODINGER_TEMP_PROJECT}")
    else:
        # tmp_prj is invalid, setting tmp_prj to "" so that the next
        # rule will be tried
        tmp_prj = ""
        logger.error(f"Could not set up {SCHRODINGER_TEMP_PROJECT}")
        sys.exit(1)
    return tmp_prj


def _set_schrodinger_temp_project_env_var(profile_name):
    """
    If SCHRODINGER_TEMP_PROJECT is not set by user, set the same as per the
    below rules in that order:

    1. If SCHRODINGER_TEMP_PROJECT is already set, then user would have set
       it. So dont do anything.
    2. Look for the preference 'tempprojectlocation' in 'prefer.cmd' file
    3. Look for TMPDIR environment variable
    4. Fallback to ~/.schrodinger/tmp, if nothing works out. This is the temp
       path as returned by schrodinger_dir

    :param profile_name: name of the maestro profile
    :type profile_name: str
    """
    # Case 1
    # User might have set this from command line manually. Maestro
    # should retain this setting

    tmp_prj = os.environ.get(SCHRODINGER_TEMP_PROJECT, "")
    if tmp_prj:
        os.environ['SCHRODINGER_TEMP_PROJECT_SET_BY_USER'] = tmp_prj
    else:
        # Case 2:
        tmp_prj = _set_tmp_prj_from_maestro_preference(profile_name)
    if not tmp_prj:
        # Case 3:
        tmp_prj = _set_tmp_prj_from_TMPDIR_env_var()
    if not tmp_prj:
        # Case 4:
        tmp_prj = _set_tmp_prj_from_schrodinger_temp_dir()

    os.environ[SCHRODINGER_TEMP_PROJECT] = tmp_prj
    logger.debug(
        "SCHRODINGER_TEMP_PROJECT: %s" % os.environ[SCHRODINGER_TEMP_PROJECT])


def _configure_font_config():
    """
    Configure fontconfig's FONTCONFIG_FILE environment variable
    if it is not set.  If it is, then just use the value that was set.
    """
    fc_file = os.environ.get("FONTCONFIG_FILE", "")
    if fc_file == "":
        data_dir = jobutil.hunt("mmshare", jobutil.DirectoryType.DATA)
        fc_file = os.path.join(data_dir, "fonts.conf")
        os.environ['FONTCONFIG_FILE'] = fc_file
    logger.debug("FONTCONFIG_FILE: %s" % fc_file)


def _set_maestro_temp_location_env_var():
    """
    If MAESTRO_TEMP_LOCATION is not defined, first check for
    SCHRODINGER_TEMP_LOCATION, else use SCHRODINGER_TEMP_PROJECT. EV 93368
    """
    tmp_location = os.environ.get("MAESTRO_TEMP_LOCATION", "")
    if not tmp_location:
        if os.environ.get("SCHRODINGER_TEMP_LOCATION", ""):
            tmp_location = os.environ["SCHRODINGER_TEMP_LOCATION"]
            logger.debug("Using SCHRODINGER_TEMP_LOCATION for "
                         "MAESTRO_TEMP_LOCATION")
        elif os.environ.get(SCHRODINGER_TEMP_PROJECT, ""):
            logger.debug(f"Using {SCHRODINGER_TEMP_PROJECT} for "
                         "MAESTRO_TEMP_LOCATION")
            tmp_location = os.environ[SCHRODINGER_TEMP_PROJECT]
    tmp_location = os.path.join(tmp_location, str(os.getpid()))

    if not os.path.isabs(tmp_location):
        logger.error("MAESTRO_TEMP_LOCATION is not an absolute path")
        sys.exit(1)

    os.makedirs(tmp_location, exist_ok=True)

    os.environ['MAESTRO_TEMP_LOCATION'] = tmp_location
    logger.debug(
        "MAESTRO_TEMP_LOCATION: %s" % os.environ['MAESTRO_TEMP_LOCATION'])

    # SCHRODINGER_TEMP_LOCATION is set to the same value of
    # MAESTRO_TEMP_LOCATION as the python help module (mm_pyhelp.cxx) will look
    # for SCHRODINGER_TEMP_LOCATION to get the temp path
    os.environ["SCHRODINGER_TEMP_LOCATION"] = tmp_location


def _set_product_env_var(var, product, show_msg=True, exit=False):
    """
    Set the specified environment variable to the path for the given product,
    if the product is found.

    :param var: variable name, such as JAGUAR_EXEC
    :param type: str

    :param product: corresponding product name
    :type product: str

    :param show_msg: logs a message to the user if the environment variable
        is not found.
    :type show_msg: bool

    :param exit: If True, will call sys.exit
    :type exit: bool
    """
    if var not in os.environ:
        os.environ[var] = jobutil.hunt(product)
    _check_env_var(var, show_msg=show_msg, exit=exit)


def _set_library_path(var):
    """
    Adds var appropriate environment variable search directory for os.environ.
    Generally in the form of JAGUAR_EXEC, PSP_EXEC. If variable is not present
    in the environment, this is no-op.

    Since rpath is used exclusively for library path resolution on OS X, this
    is a no-op on OS X.

    :param var: environment variable
    :type var: str

    """
    if var not in os.environ:
        return
    if OS_NAME == OS.LINUX:
        product_lib_dir = re.sub('bin', 'lib', os.environ[var])
        os.environ[LD_LIBRARY_PATH] += ":" + product_lib_dir
    elif OS_NAME == OS.WINDOWS:
        product_lib_dir = os.environ[var]
        os.environ['PATH'] += ";" + product_lib_dir


def get_maestro_dir():
    return os.path.dirname(os.path.dirname(os.environ[MAESTRO_EXEC]))


def _check_env_var(var, msg="", show_msg=True, exit=False):
    if os.environ.get(var, ""):
        logger.debug("%s: %s" % (var, os.environ[var]))
    else:
        if show_msg:
            if msg:
                logger.info(msg)
            else:
                logger.warning(
                    "The variable '%s' is not defined. "
                    "It should have been set by the top-level '%s' script" %
                    (var, BACKEND))
        if exit:
            sys.exit(1)


def _check_display_env_var():
    """
    Checks the connectivity to the display.
    Please note: this is Linux specific function.
    """
    msg = "The DISPLAY environment variable is not defined." \
          "This variable must be set for Maestro to run"
    _check_env_var("DISPLAY", msg=msg, exit=True)


def _is_native_display():
    """
    Test if Maestro is using native display (direct rendering).
    """
    try:
        with os.popen('glxinfo') as process:
            if 'direct rendering: Yes' in process.read():
                return True
    except:
        return False

    return False


def prepend_sgl_lib_path(ld_library_path):
    """
    Return new LD_LIBRARY_PATH with Schrodinger Provided Mesa libraries.

    :param ld_library_path: environment representation of LD_LIBRARY_PATH
    :type ld_library_path: str

    :rtype: str
    """
    sgl_lib_path = os.path.join(
        re.sub('bin', 'lib', os.environ[MAESTRO_EXEC]), 'gl')
    return sgl_lib_path + ":" + ld_library_path


def check_opengl_linux(mae_exe, gl_option):
    """
    Check for valid OpenGL libraries on Linux platform. If software rendering is
    needed, add OpenGL libraries to LD_LIBRARY_PATH

    :param mae_exe: full path to maestro executable
    :type mae_exe: str

    :param gl_option: Use hardware, software or autodetect OpenGL rendering
    :type gl_option: GLOption
    """
    if OS_NAME != OS.LINUX:
        raise RuntimeError("This function is only valid on linux")
    if gl_option in (GLOption.FORCE_MESA, GLOption.FORCE_HARDWARE):
        return
    # Check if system OpenGL library is available
    cmd = ['ldd', mae_exe]
    p = subprocess.run(
        cmd,
        stderr=subprocess.STDOUT,
        stdout=subprocess.PIPE,
        universal_newlines=True)
    if p.returncode:
        logger.error(p.stdout)
        sys.exit(1)
    else:
        line = p.stdout[p.stdout.find('libGL.so'):]
        libgl_line = line[:line.find('\n')]
        if libgl_line.find('not found') > -1:
            logger.info("\nYou need to install the needed GL libraries "
                        "and drivers for your graphics card.\n"
                        "Without these, Maestro uses Schrodinger libGL "
                        "libraries, and will run much more\nslowly because "
                        "OpenGL rendering will be done in software, not "
                        "in hardware.\n")
            # Use the Schrodinger libGL instead of the system GL
            os.environ[LD_LIBRARY_PATH] = prepend_sgl_lib_path(
                os.environ[LD_LIBRARY_PATH])


def _prune_old_temp_projects(basedir):
    """
    Remove scratch projects which are last modified greater than 30 days ago.

    :param basedir: Directory where temporary projects are stored.
    :type basedir: pathlib.Path
    """
    report_timing("Prunning old temp projects - start")
    if not basedir.is_dir():
        return
    # Calculate time older than 30 days.
    now = time.time()
    past_time = (now - 30 * 60 * 60 * 24)

    for child_dir in basedir.iterdir():
        dirname = str(child_dir.stem)
        if re.search(mm.mmcommon_get_scratch_project_regular_expression(),
                     dirname):
            dir_stat = child_dir.stat()
            if dir_stat.st_mtime <= past_time:
                shutil.rmtree(child_dir, ignore_errors=True)

    report_timing("Prunning old temp projects - end")


def start_jobcon_processes(skip_job_server_registration):
    """
    Start needed jobcontrol processes before maestro starts up. This increases
    speed of immediately launching jobs, as well as reduces the number of
    errors.
    """
    if mmutil.feature_flag_is_enabled(mmutil.JOB_SERVER):
        server.ensure_localhost_server_running()
        if skip_job_server_registration:
            return
        import schrodinger.job.cert
        needs_configure = schrodinger.job.cert.servers_without_registration()
        if needs_configure:
            subprocess.run(["run", "jobserver_cert_gui.py"])
    else:
        _start_jserver()


def _start_jserver():
    """
    Starts jserver in a non blocking fashion.
    """
    report_timing("Starting Jserver")
    if OS_NAME == OS.WINDOWS:
        # Windows does not run process in background using
        # "$SCHRODINGER/utilities/jserver &" command, so we use Popen(),
        # but do not call communicate() in order to make it non-blocking.
        cmd = [
            os.path.join(os.environ["SCHRODINGER"], "utilities", "jserver"),
            '-defer'
        ]
        subprocess.Popen(
            cmd,
            stderr=subprocess.PIPE,
            stdout=subprocess.PIPE,
            universal_newlines=True)
    else:
        # For Linux and Mac, we call "$SCHRODINGER/utilities/jserver &"
        # which allows process to run as background process, so we call
        # os.system().
        # We can not use Popen() without communicate() on Linux/Mac because
        # perl process appear as defunct until startup.py terminate.
        cmd = os.path.join(os.environ["SCHRODINGER"], "utilities", "jserver")
        # Ensure that it works when $SCHRODINGER contains spaces in it.
        cmd = "\"" + cmd + "\" -defer >/dev/null 2>&1 &"
        os.system(cmd)
    report_timing("Started Jserver")


def _eula_accepted() -> bool:
    """
    Return true if user accepted to the End User License Agreement terms, false
    otherwise.
    """

    # create QApplication if does not exist
    app = application.get_application()
    sys.path.append(
        os.path.join(
            mm.mmfile_get_product_dir_path("mmshare"), "python", "scripts"))
    from enduserlicenseagreementdlg import EndUserLicenseAgreementDlg
    license_agreement = EndUserLicenseAgreementDlg()
    result = license_agreement.exec() == QDialog.Accepted
    sys.path.pop()
    return result


def _start_maestro(options, mae_exe, backend_args):
    """
    Launch maestro executable.

    :param options: parsed options for this script
    :type options: optparse.Values

    :param mae_exe: full path to maestro executable
    :type mae_exe: str

    :param backend_args: argv to pass to maestro executable
    :type backend_args: list(str)

    :raises SystemExit: if maestro executable exits non-zero
    """

    if OS_NAME == OS.LINUX:
        if options.strace:
            options.debugger = "strace"

    if options.debugger:
        dbg = shlex.split(options.debugger)
        cmd = dbg + [mae_exe]
        if dbg == ["totalview"]:
            cmd.append("-a")
        elif dbg == ["gdb"]:
            cmd.insert(1, "--args")
        elif dbg == ["lldb"]:
            cmd.append("--")
        if OS_NAME == OS.WINDOWS:
            subprocess.call(cmd)
            fileutils.force_remove(
                os.path.join(os.environ[MAESTRO_EXEC], BACKEND + ".sln"))
            fileutils.force_remove(
                os.path.join(os.environ[MAESTRO_EXEC], BACKEND + ".suo"))
        else:
            cmd += backend_args
            logger.info("Using debugger: '%s'" % ' '.join(cmd))
            subprocess.call(cmd)
    else:
        cmd = []
        if options.vtune:
            cmd = [
                "vtl", "activity", "vtune_mae", "-c", "callgraph", "-app",
                mae_exe
            ]
            cmd.extend(backend_args)
            cmd.extend(["-moi", mae_exe, 'run'])
        elif OS_NAME == OS.WINDOWS and options.squish:
            os.environ['SQUISH_LIBQTDIR'] = os.environ[MAESTRO_EXEC]
            cmd = ['dllpreload.exe', mae_exe] + backend_args
        else:
            cmd = [mae_exe] + backend_args

        report_timing("Finished prep.  Invoking maestro binary")

        exitcode = RESTART_EXIT_CODE
        crash_dir = create_crash_dir()
        maestro_start_time = time.time()
        while exitcode == RESTART_EXIT_CODE:
            maestro_start_time = time.time()
            maestro = subprocess.Popen(cmd, stderr=subprocess.STDOUT)
            maestro.communicate()
            exitcode = maestro.returncode
            process_id = maestro.pid
        maestro_end_time = time.time()
        mae_err_log = get_mae_err_log(crash_dir, process_id)
        # Initially prepare path builds log file path based on running
        # Python process. If maestro starts successfully, then we need
        # to prepare path according to maestro process id.

        report_timing("Done with maestro")

        # Check for a crash caused by missing fonts
        if OS_NAME == OS.LINUX and exitcode != 0 and maestro_end_time - \
                    maestro_start_time <= MAESTRO_FONT_CRASH_TIME:
            found_fonts = os.system('fc-match "Sans Serif" >/dev/null 2>&1')
            if found_fonts != 0:
                print("Required fonts could not be found.")
                print("You might need to install more fonts on your computer.")

        if exitcode != 0:
            # Setting logger to write messages into the maestro error log file
            log.logging_config(
                level=log.logging.INFO,
                format="%(message)s",
                file=mae_err_log,
                filemode='a')
            logger.info("")
            # These exit status are coming from mm_main.h or mmerr.h
            if exitcode == 3:
                _showLicenseError(mae_err_log)
            elif exitcode in {2, 4, 6, 7, 8}:
                print("Exiting...")
            # This case does not occur on Windows. Instead a dialog box is
            # shown to indicate the missing library.
            elif OS_NAME != OS.WINDOWS and exitcode == 127:
                print("Maestro: Could not load shared library")
                print("Exiting...")
            else:
                minidump_filename = _maestro_win_dmp_file_name(
                    crash_dir, process_id)
                _maestro_catch(exitcode, crash_dir, mae_err_log)

            report_timing("Error.  Exiting startup.py")

            sys.exit(exitcode)

        else:
            # No error. Remove the Maestro log file
            mae_log_file = os.path.join(
                fileutils.get_directory_path(fileutils.TEMP),
                "maestro_" + str(maestro.pid) + ".log")
            if os.path.exists(mae_log_file):
                os.remove(mae_log_file)
            report_timing("Returned cleanly.  Exiting startup.py")


def in_compatibility_mode(mae_exe):
    """
    Checks if Maestro running in compatibility mode on Windows.

    :param mae_exe: Maestro executable
    :type mae_exe: string
    """
    import check_registry
    mae_full_exe = os.path.join(os.environ[MAESTRO_EXEC], mae_exe)
    return check_registry.check_compatibilty_mode(mae_full_exe)


def show_fatal_maestro_error(message):
    """
    Display error dialog to user. This function blocks until user dismisses
    the dialog.

    :param message: plain text version of message
    :type message: str
    """
    # create QApplication if does not exist
    app = application.get_application()
    msg_text = "Maestro had a fatal error, full text is below:\n\n" + message
    msg_html = msg_text.replace("\r\n", "<br />")
    msg_html = msg_text.replace("\n", "<br />")
    err = exception_dialog.ExceptionDialog(
        msg_html, msg_text, show_ignore=False)
    err.exec()


def show_compatibility_mode_message():
    """
    Shows Message Box about integrated Intel graphics card with
    a defective driver and running Maestro in compatibility mode.
    """
    # create QApplication if does not exist
    app = application.get_application()
    msg = QMessageBox()
    msg.setIcon(QMessageBox.Warning)
    msg.setText(
        textwrap.dedent("""
        Your computer has an integrated Intel graphics card
        with a defective driver."""))
    msg.setInformativeText(
        textwrap.dedent("""
        Please check that you are using the latest available
        version of the graphics card driver for your card.

        We recommend checking on the manufacturer's website
        first if there is an updated driver version available. If
        not, there may be newer versions on Intel's website.

        If there are no updated driver versions available for your
        card or if updating the driver does not help, you can try
        to start Maestro in the "Windows 7" or "Windows 8
        compatibility mode". Right-click on the Maestro icon,
        select "Properties" and go to the "Compatibility" tab.
        Check the box for "Run this program in compatibility
        mode for" and then select "Windows 7" or "Windows 8"
        from the drop-down menu. Click on "Apply" and try to
        restart Maestro.

        If the problem still remains, please send us the
        diagnostics archive following the steps described on:
        https://www.schrodinger.com/kb/1692

        Please note that we do recommend a dedicated graphics
        card, such as provided by NVIDIA, to ensure optimal
        performance with Maestro.

        https://www.schrodinger.com/kb/404869"""))
    msg.setWindowTitle("Warning")
    msg.exec_()


def needs_mesa_windows(ignore_bad_drivers, compatibility_mode):
    """
    Queries current OpenGL driver and determines if we should use Mesa OpenGL
    library. Windows only.

    :param ignore_bad_drivers: If True, disregard the known bad drivers when
        deciding whether to use Mesa.
    :type ignore_bad_drivers: bool

    :param compatibility_mode: If True, running Windows in compatibility mode
    :type compatibility_mode: bool

    :rtype: bool
    :return: True if Mesa libraries are needed.
    """
    supports_opengl2, good_driver = probe_opengl.probe_driver_capabilities()

    if not supports_opengl2:
        logger.info("No native OpenGL2 support, switching to Mesa")
        return True

    return (not ignore_bad_drivers and not good_driver and
            not compatibility_mode)


def check_opengl_windows(mae_exe, gl_option, ignore_bad_drivers):
    """
    Returns name of maestro executable, which will be different if Mesa
    libraries are needed.

    :param mae_exe: path to maestro executable
    :type mae_exe: str

    :param gl_option: Use hardware, software or autodetect OpenGL rendering
    :type gl_option: GLOption

    :param ignore_bad_drivers: If True, ignore bad drivers for OpenGL
        consideration
    :type ignore_bad_drivers: bool

    :return: path to maestro executable
    :rtype: str
    """
    if OS_NAME != OS.WINDOWS:
        raise RuntimeError("This function is only valid on windows.")
    # If there is no valid OpenGL 2 available,
    # use opengl32.dll from msys2 mesa package
    # mingw-w64-x86_64-mesa-17.3.3-1
    if gl_option != GLOption.FORCE_HARDWARE:
        compatibility_mode = in_compatibility_mode(mae_exe)

        if gl_option is GLOption.FORCE_MESA or needs_mesa_windows(
                ignore_bad_drivers, compatibility_mode):
            mae_exe = os.path.join('mesa', mae_exe)
    return mae_exe


def assert_maestro_existence(mae_exe):
    """
    Raise SystemExit if mae_exe does not exist.

    :param mae_exe: full path to maestro executable
    :trype mae_exe: str
    """
    if not (os.path.isfile(mae_exe) and os.access(mae_exe, os.X_OK)):
        logger.critical("Program '%s' does not exist or lacks execute "
                        "permission." % mae_exe)
        sys.exit(4)


def _main(options, backend_args):

    print()
    logger.info(ASTERISK_LINE)
    logger.info("Maestro Molecular Modeling Interface")
    if OS_NAME == OS.WINDOWS:
        logger.info("Maestro is a product of Schroedinger, Inc.")
    else:
        tmp = 'Schrödinger'
        logger.info("Maestro is a product of %s, Inc." % tmp)
    logger.info("Legal notices can be viewed by clicking Help->About Maestro")
    logger.info(ASTERISK_LINE)
    logger.debug("\nChecking environment variables...\n")

    if OS_NAME == OS.LINUX:
        _check_display_env_var()

    msg = "The SCHRODINGER environment variable not defined.\n" \
          "It should be set to the pathname for the directory where your " \
          "Schrodinger products and license are installed."
    _check_env_var("SCHRODINGER", msg=msg, exit=True)
    _check_env_var("MMSHARE_EXEC", exit=True)
    _check_env_var(MAESTRO_EXEC, exit=True)

    _set_product_env_var("MMSHARE_EXEC", "mmshare", exit=True)
    _set_product_env_var("MMOD_EXEC", "macromodel", show_msg=False)
    _set_product_env_var("JAGUAR_EXEC", "jaguar", show_msg=False)
    _set_product_env_var("PSP_EXEC", "psp", show_msg=False)
    _set_product_env_var("COMBIGLIDE_EXEC", "combiglide", show_msg=False)
    _set_product_env_var("DESMOND_EXEC", "desmond", show_msg=False)
    _set_product_env_var("SCISOL_EXEC", "scisol", show_msg=False)
    _set_product_env_var("CANVAS_EXEC", "canvas", show_msg=False)

    _set_library_path("DESMOND_EXEC")
    _set_library_path("CANVAS_EXEC")

    if OS_NAME == OS.WINDOWS:
        logger.debug("PATH: %s" % os.environ['PATH'])
    elif OS_NAME == OS.LINUX:
        logger.debug("LD_LIBRARY_PATH: %s" % os.environ[LD_LIBRARY_PATH])

    if not os.environ.get("SCHRODINGER_NICE", ""):
        os.environ['SCHRODINGER_NICE'] = "local"
    else:
        logger.debug("SCHRODINGER_NICE: %s" % os.environ["SCHRODINGER_NICE"])

    if not os.environ.get('MMRESDIR', ""):
        maestro_data = jobutil.hunt("maestro", jobutil.DirectoryType.DATA)
        os.environ['MMRESDIR'] = os.path.join(maestro_data, "res")
    else:
        logger.debug("MMRESDIR: %s" % os.environ['MMRESDIR'])

    if OS_NAME == OS.OSX:
        _configure_font_config()

    _set_schrodinger_temp_project_env_var(
        profile_name=get_profile_name(backend_args))

    _set_maestro_temp_location_env_var()

    # Ev 111154
    if os.environ.get("SCHRODINGER_JOBDB", False) and \
            os.environ.get("SCHRODINGER_JOBDB2", False):
        if os.environ['SCHRODINGER_JOBDB'] != "" and \
            os.environ['SCHRODINGER_JOBDB2'] != "" and \
            os.path.normpath(os.environ['SCHRODINGER_JOBDB']) == \
                os.path.normpath(os.environ['SCHRODINGER_JOBDB2']):
            logger.critical(
                "SCHRODINGER_JOBDB2 is set to the same location "
                "as SCHRODINGER_JOBDB which will lead to problems if you try"
                " to run a job. Please unset SCHRODINGER_JOBDB2 or set it to"
                " a different location.")
            sys.exit(1)

    if not options.show_version:
        logger.debug("\nEnvironment variables successfully initialized. "
                     "Starting up Maestro...")
    logger.debug("")

    mae_exe = 'maestro'
    if OS_NAME == OS.WINDOWS:
        mae_exe += '.exe'
        mae_exe = check_opengl_windows(mae_exe, options.GL,
                                       options.ignore_bad_drivers)

    # Make sure binary is really available
    mae_exe = os.path.join(os.environ[MAESTRO_EXEC], mae_exe)
    assert_maestro_existence(mae_exe)

    if options.ldd:
        if OS_NAME == OS.OSX:
            if not shutil.which("otool"):
                logger.info("The option -lddonly is only available if "
                            "Xcode is installed.")
                sys.exit(1)

            cmd = ["otool", "-L", mae_exe]
        else:
            cmd = ["ldd", mae_exe]
        subprocess.run(cmd)
        if options.lddonly:
            sys.exit(0)

    if OS_NAME == OS.LINUX:
        # Detect non-native display
        if options.GL is GLOption.AUTODETECT and not _is_native_display():
            os.environ[SCHRODINGER_GL] = 'on'
            # Add Schrodinger GL library path to LD_LIBRARY_PATH
            os.environ[LD_LIBRARY_PATH] = prepend_sgl_lib_path(
                os.environ[LD_LIBRARY_PATH])

        # Check for GL libraries for Linux (if -SGL was not used)
        check_opengl_linux(mae_exe, options.GL)

    _prune_old_temp_projects(pathlib.Path(os.environ[SCHRODINGER_TEMP_PROJECT]))

    if not options.show_help:
        start_jobcon_processes(options.skipjobserverregistration)
        if mmutil.feature_flag_is_enabled(
                mmutil.MAESTRO_REQUIRE_EXPLICIT_EULA) and (
                    not _eula_accepted()):
            return
    _start_maestro(options, mae_exe, backend_args)

    fileutils.force_rmtree(os.environ["MAESTRO_TEMP_LOCATION"])


@contextlib.contextmanager
def log_and_exit():
    """
    Create a logging handler which buffers output and displays
    an error to user.
    """
    log_output = io.StringIO()
    handler = log.logging.StreamHandler(log_output)
    logger.addHandler(handler)
    try:
        yield
    except (BrokenPipeError, KeyboardInterrupt):
        sys.exit(1)
    except SystemExit as e:
        if e.code and e.code != 0:
            show_fatal_maestro_error(log_output.getvalue())
        raise
    except Exception as e:
        traceback.print_exc()
        traceback.print_exc(file=log_output)
        show_fatal_maestro_error(log_output.getvalue())
        sys.exit(1)
    finally:
        # for testing
        logger.removeHandler(handler)


@log_and_exit()
def main():
    report_timing("startup.py __main__")
    options, backend_args = _parse_args(sys.argv[1:])
    _main(options, backend_args)


if __name__ == '__main__':
    main()
