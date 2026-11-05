#!/usr/bin/env python3
"""Load the private settings and select bundled or external PostgreSQL."""
import os
import sys
from deployment import ROOT, compose_environment, read_config

env, files = compose_environment(read_config())
os.chdir(ROOT)
args = ['docker', 'compose', '--project-directory', str(ROOT), '--env-file', os.devnull]
for path in files:
    args += ['-f', str(path)]
# Explicit files and /dev/null disable implicit .env and COMPOSE_FILE discovery.
os.execvpe('docker', args + sys.argv[1:], env)
