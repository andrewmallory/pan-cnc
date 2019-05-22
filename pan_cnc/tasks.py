# Copyright (c) 2018, Palo Alto Networks
#
# Permission to use, copy, modify, and/or distribute this software for any
# purpose with or without fee is hereby granted, provided that the above
# copyright notice and this permission notice appear in all copies.
#
# THE SOFTWARE IS PROVIDED "AS IS" AND THE AUTHOR DISCLAIMS ALL WARRANTIES
# WITH REGARD TO THIS SOFTWARE INCLUDING ALL IMPLIED WARRANTIES OF
# MERCHANTABILITY AND FITNESS. IN NO EVENT SHALL THE AUTHOR BE LIABLE FOR
# ANY SPECIAL, DIRECT, INDIRECT, OR CONSEQUENTIAL DAMAGES OR ANY DAMAGES
# WHATSOEVER RESULTING FROM LOSS OF USE, DATA OR PROFITS, WHETHER IN AN
# ACTION OF CONTRACT, NEGLIGENCE OR OTHER TORTIOUS ACTION, ARISING OUT OF
# OR IN CONNECTION WITH THE USE OR PERFORMANCE OF THIS SOFTWARE.

# Author: Nathan Embery nembery@paloaltonetworks.com

"""
Palo Alto Networks pan-cnc

pan-cnc is a library to build simple GUIs and workflows primarily to interact with various APIs

Please see http://github.com/PaloAltoNetworks/pan-cnc for more information

This software is provided without support, warranty, or guarantee.
Use at your own risk.
"""

import asyncio
import json
import os
import subprocess
from subprocess import Popen

from celery import shared_task, current_task


class OutputHolder(object):
    full_output = ''

    def __init__(self):
        self.full_output = ''

    def add_output(self, message):
        self.full_output += message

    def get_output(self):
        return self.full_output


async def cmd_runner(cmd_seq, cwd, env, o: OutputHolder):
    p = await asyncio.create_subprocess_shell(' '.join(cmd_seq),
                                              stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT,
                                              cwd=cwd, env=env)

    while True:
        line = await p.stdout.readline()
        if line == b'':
            break

        o.add_output(line.decode())
        current_task.update_state(state='PROGRESS', meta=o.get_output())

    await p.wait()
    return p.returncode


def exec_local_task(cmd_seq: list, cwd: str, env=None) -> str:
    print('Kicking off new task - exe local task')
    process_env = os.environ.copy()
    if env is not None and type(env) is dict:
        process_env.update(env)

    o = OutputHolder()
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    r = loop.run_until_complete(cmd_runner(cmd_seq, cwd, process_env, o))
    loop.stop()
    print(f'Task {current_task.request.id} return code is {r}')
    state = dict()
    state['returncode'] = r
    state['out'] = o.get_output()
    state['err'] = ''
    return json.dumps(state)


def exec_sync_local_task(cmd_seq: list, cwd: str, env=None) -> str:
    """
    Execute local Task in a subprocess thread. Capture stdout and stderr together
    and update the task after the task is done. This should only be used for things we know will happen very fast
    :param cmd_seq: Command to run and all it's arguments
    :param cwd: working directory in which to start the command
    :param env: dict of env variables where k,v == env var name, env var value
    :return: JSON encoded string - dict containing the following keys: returncode, out, err
    """
    print(f'Executing new task  with id: {current_task.request.id}')

    process_env = os.environ.copy()
    if env is not None and type(env) is dict:
        process_env.update(env)

    p = Popen(cmd_seq, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, bufsize=1, universal_newlines=True,
              env=process_env)
    stdout, stderr = p.communicate()
    rc = p.returncode
    print(f'Task {current_task.request.id} return code is {rc}')
    state = dict()
    state['returncode'] = rc
    state['out'] = stdout
    state['err'] = stderr
    return json.dumps(state)


@shared_task
def terraform_validate(terraform_dir, tf_vars):
    print('Executing task terraform validate')
    cmd_seq = ['terraform', 'validate', '-no-color']
    for k, v in tf_vars.items():
        cmd_seq.append('-var')
        cmd_seq.append(f'{k}={v}')

    return exec_local_task(cmd_seq, terraform_dir)


@shared_task
def terraform_init(terraform_dir, tf_vars):
    print('Executing task terraform init')
    cmd_seq = ['terraform', 'init', '-no-color']
    # for k, v in tf_vars.items():
    #     cmd_seq.append('-var')
    #     cmd_seq.append(f'{k}={v}')

    return exec_local_task(cmd_seq, terraform_dir)


@shared_task
def terraform_plan(terraform_dir, tf_vars):
    print('Executing task terraform plan')
    cmd_seq = ['terraform', 'plan', '-no-color', '-out=.cnc_plan']
    for k, v in tf_vars.items():
        cmd_seq.append('-var')
        cmd_seq.append(f'{k}={v}')

    return exec_local_task(cmd_seq, terraform_dir)


@shared_task
def terraform_apply(terraform_dir, tf_vars):
    print('Executing task terraform apply')
    cmd_seq = ['terraform', 'apply', '-no-color', '-auto-approve', './.cnc_plan']
    return exec_local_task(cmd_seq, terraform_dir)


@shared_task
def terraform_output(terraform_dir, tf_vars):
    print('Executing task terraform output')
    cmd_seq = ['terraform', 'output', '-no-color', '-json']
    print(cmd_seq)
    return exec_sync_local_task(cmd_seq, terraform_dir)


@shared_task
def terraform_destroy(terraform_dir, tf_vars):
    print('Executing task terraform destroy')
    cmd_seq = ['terraform', 'destroy', '-no-color', '-auto-approve']
    for k, v in tf_vars.items():
        cmd_seq.append('-var')
        cmd_seq.append(f'{k}={v}')

    return exec_local_task(cmd_seq, terraform_dir)


@shared_task
def terraform_refresh(terraform_dir, tf_vars):
    print('Executing task terraform status')
    cmd_seq = ['terraform', 'refresh', '-no-color']
    for k, v in tf_vars.items():
        cmd_seq.append('-var')
        cmd_seq.append(f'{k}={v}')

    print(cmd_seq)
    return exec_local_task(cmd_seq, terraform_dir)


@shared_task
def python3_init_env(working_dir):
    print('Executing task Python3 init')
    cmd_seq = ['python3', '-m', 'virtualenv', '.venv']
    env = dict()
    env['PYTHONUNBUFFERED'] = "1"
    return exec_local_task(cmd_seq, working_dir, env)


@shared_task
def python3_init_with_deps(working_dir):
    print('Executing task Python3 init with Dependencies')
    cmd_seq = ['python3', '-m', 'virtualenv', '.venv', '&&',
               './.venv/bin/python3', '-m', 'pip', 'install', '-r', 'requirements.txt']
    env = dict()
    env['PYTHONUNBUFFERED'] = "1"
    return exec_local_task(cmd_seq, working_dir, env)


@shared_task
def python3_init_existing(working_dir):
    print('Executing task Python3 init with Dependencies')
    cmd_seq = ['./.venv/bin/python3', '-m', 'pip', 'install', '--upgrade', '-r', 'requirements.txt']
    env = dict()
    env['PYTHONUNBUFFERED'] = "1"
    return exec_local_task(cmd_seq, working_dir, env)


@shared_task
def python3_execute_script(working_dir, script, args):
    print(f'Executing task Python3 {script}')
    cmd_seq = ['./.venv/bin/python3', '-u', script]

    for k, v in args.items():
        cmd_seq.append(f'--{k}="{v}"')

    env = dict()
    env['PYTHONUNBUFFERED'] = "1"
    return exec_local_task(cmd_seq, working_dir, env)


@shared_task
def python3_execute_bare_script(working_dir, script, args):
    print(f'Executing task Python3 {script}')
    cmd_seq = ['python3', '-u', script]

    for k, v in args.items():
        cmd_seq.append(f'--{k}="{v}"')

    env = dict()
    env['PYTHONUNBUFFERED'] = "1"
    return exec_local_task(cmd_seq, working_dir, env)

