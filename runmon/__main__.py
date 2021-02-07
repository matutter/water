import asyncio
import os
import os.path as op
import re
import sys
from typing import List, Optional, Tuple, final

import click
from click.core import Context
from colors import color as Color256
from watchdog.events import FileSystemEvent

from .display import *
from .monitor import Monitor

set_display_name('runmon')


def want_string(ctx, param, value: Tuple[str]):
    return ' '.join(list(value))


def want_list(ctx, param, value: Tuple[str]):
    """ Returns list of all items in value """
    l = []
    [l.extend(re.split(r'[\s,]+', v)) for v in list(value)]
    return l


def expand_ext(ctx, param, value: Tuple[str]):
    value = want_list(None, None, value)
    return [(v if v.startswith('*') else '*'+v) for v in value]


def before_run(m: Monitor, ev: FileSystemEvent, scripts: List[str]):
    display_info(f'triggered because {ev.src_path} was {ev.event_type}')


def print_version(ctx: Context, param, value):
    if not value or ctx.resilient_parsing:
        return
    try:
        ver_file = op.join(op.dirname(__file__), 'VERSION.txt')
        with open(ver_file, 'r') as fd:
            click.echo(fd.read(20).strip())
    except:
        pass
    finally:
        ctx.exit()


@click.command()
@click.option('--version', is_flag=True, callback=print_version,
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
@click.option('-x', '--exec',
              multiple=True, default=[], callback=want_list,
              help='Script to execute.')
@click.option('-u', '--unsafe',
              is_flag=True, default=False,
              help='Do not apply the default ignore list (.git, __pycache__/, etc...).')
@click.argument('args', callback=want_string, nargs=-1)
def runmon(ext: List[str], watch: List[str], ignore: List[str],
           verbose: bool, unsafe: bool,
           exec: List[str], args: str, config_file: str = None):

    if not unsafe:
        ignore.extend(['.git/*', '__pycache__/*', '.*'])

    m = Monitor()

    scripts = list(filter(lambda s: s, exec[:] + [args]))

    if not scripts:
        display_warning("No script or executable specified, nothing to do ...")
        exit(2)

    m.add_runner(scripts, watch, ext, ignore=ignore)

    if verbose:
        m.before_run(before_run)

    m.start_interactive()


if __name__ == '__main__':
    runmon.main(prog_name=get_display_name())