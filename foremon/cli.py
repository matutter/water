import asyncio
from foremon.errors import ForemonError
from foremon.task import ForemonTask
from foremon.config import ForemonConfig, PyProjectConfig
import os
import os.path as op
import re
import shlex
from importlib.util import find_spec
from typing import Coroutine, List, Tuple

import click
from click.core import Context
from watchdog.events import FileSystemEvent

from . import __version__
from .display import *
from .monitor import Monitor


def want_string(ctx, param, value: Tuple[str]):
    return ' '.join(list(value))


def want_list(ctx, param, value: Tuple[str]):
    """ Returns list of all items in value """
    l = []
    [l.extend(re.split(r'[\s,]+', v)) for v in list(value)]
    return l


def expand_exec(ctx, param, value: Tuple[str]):
    return list(value)


def expand_ext(ctx, param, value: Tuple[str]):
    value = want_list(None, None, value)
    return [(v if v.startswith('*') else '*'+v) for v in value]


def relative_if_cwd(path: str) -> str:
    """
    Converts `path` to a relative path iff it is child path of the cwd.
    """
    cwd: str = os.getcwd()
    if path.startswith(cwd):
        return op.relpath(path)
    return path


def guess_args(args: str) -> str:
    if not args:
        return args
    argv = shlex.split(args)
    if not argv:
        return args

    arg0: str = argv[0]

    if arg0.endswith('.py'):
        # Attempt to insert python interpreter before script path if script is not executable
        is_x = os.access(arg0, os.X_OK)
        if not is_x:
            argv.insert(0, relative_if_cwd(sys.executable))
        # Attempt to insert `python -m` before module name if arg[0] is dir
    elif op.isdir(arg0):
        init_file = op.join(arg0, '__main__.py')
        if op.isfile(init_file):
            argv = [relative_if_cwd(sys.executable), '-m'] + argv

    else:
        # Attempt run as module that isn't local
        spec = find_spec(arg0)
        if spec is not None:
            argv = [relative_if_cwd(sys.executable), '-m'] + argv

    # shlex.join not in py3.7
    return " ".join(argv)


class Util:

    """
    A class of hookable static methods.
    """
    @staticmethod
    def print_version(ctx: Context, param, value):
        if not value or ctx.resilient_parsing:
            return
        try:
            print(__version__)
        except:
            pass
        finally:
            ctx.exit()

    @staticmethod
    def before_run(task: ForemonTask, trigger: Any):

        if not isinstance(trigger, FileSystemEvent):
            return

        ev: FileSystemEvent = trigger
        path: str = ev.src_path
        # display relative paths shorter
        cwd = os.getcwd()
        if path.startswith(cwd):
            path = path[len(cwd)+1:]
        display_info(f'triggered because {path} was {ev.event_type}')

    @staticmethod
    def get_input():
        return sys.stdin

    @staticmethod
    def run_until_complete(coro: Coroutine):
        try:
            loop = asyncio.get_event_loop()
            loop.run_until_complete(coro)
        except KeyboardInterrupt:
            pass

    @staticmethod
    def add_tasks(m: Monitor, conf: ForemonConfig, verbose: bool = False) -> None:
        task = ForemonTask(conf)
        if verbose:
            task.add_before_callback(Util.before_run)
        m.add_task(task)
        display_debug("task", task.name, "ready for monitor")
        for sub in conf.configs:
            Util.add_tasks(m, sub, verbose)

    @staticmethod
    def start_monitor(m: Monitor, dry_run: bool = False):
        if dry_run:
            display_success('dry run complete')
        else:
            Util.run_until_complete(m.start_interactive())


@click.command(context_settings=dict(ignore_unknown_options=True))
@click.option('--version', is_flag=True, callback=Util.print_version,
              expose_value=False, is_eager=True,
              help='Print version and exit.')
@click.option('-f', '--config-file',
              type=click.Path(exists=True),
              help='Path to file config.')
@click.option('-e', '--ext',
              default='*', multiple=True,
              show_default=True, callback=expand_ext,
              help='File extensions to watch.')
@click.option('-w', '--watch',
              default='.', show_default=True,
              multiple=True, callback=want_list,
              help='File or directory patterns to watched for changes.')
@click.option('-i', '--ignore',
              multiple=True, default=[], callback=want_list,
              help='File or directory patterns to ignore.')
@click.option('-V', '--verbose',
              is_flag=True, default=False,
              help='Show details on what is causing restarts.')
# Deprecated
# @click.option('-P', '--parallel',
#               is_flag=True, default=False,
#               help='Allow scripts to execute in parallel if changes occur while another is running.')
@click.option('-x', '--exec',
              multiple=True, default=[], callback=expand_exec,
              help='Script to execute.')
@click.option('-u', '--unsafe',
              is_flag=True, default=False,
              help='Do not apply the default ignore list (.git, __pycache__/, etc...).')
@click.option('-n', '--no-guess',
              is_flag=True, default=False,
              help='Do not try to run commands as a script or module.')
@click.option('-C', '--chdir',
              help='Change to this directory before starting.')
@click.option('--dry-run', is_flag=True, hidden=True)
@click.argument('args', callback=want_string, nargs=-1)
def foremon(ext: List[str], watch: List[str], ignore: List[str],
            verbose: bool, unsafe: bool, no_guess: bool,
            exec: List[str], args: str,
            config_file: str = None, chdir: Optional[str] = None, dry_run: bool = False):

    set_display_verbose(verbose)

    if args and not no_guess:
        args = guess_args(args)

    scripts = list(filter(lambda s: s, exec[:] + [args]))

    conf = None
    if config_file:
        with open(config_file, 'r') as fd:
            project = PyProjectConfig.parse_toml(fd.read())
            conf = project.tools.foremon

            if conf is None:
                display_debug(
                    'no [tools.foremon] section specified in', config_file)
            else:
                display_success(
                    'loaded [tools.foremon] config from', config_file)

    if conf is None:
        conf = ForemonConfig(scripts=scripts)
    elif scripts:
        conf.scripts.extend(scripts)

    if not conf.scripts:
        display_warning("No script or executable specified, nothing to do ...")
        exit(2)

    if unsafe:
        conf.ignore_defaults.clear()

    if chdir:
        conf.cwd = chdir

    if ignore:
        conf.ignore.extend(ignore)

    if watch:
        conf.paths = watch.copy()

    if ext:
        conf.patterns = ext.copy()

    try:
        m = Monitor(pipe=Util.get_input())

        Util.add_tasks(m, conf, verbose=verbose)

        print(Util.start_monitor)
        Util.start_monitor(m, dry_run=dry_run)
    except ForemonError as e:
        display_error(f'error {e.code}: {e.message}')
        exit(e.code)


def main():
    set_display_name('foremon')
    return foremon.main(prog_name=get_display_name())
