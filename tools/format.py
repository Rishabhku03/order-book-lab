import argparse
import os
import subprocess
from pathlib import Path
import clang_format
from common import ROOT

p=argparse.ArgumentParser();p.add_argument('--check',action='store_true');args=p.parse_args()
binary=Path(clang_format.__file__).parent/'data'/'bin'/('clang-format.exe' if os.name=='nt' else 'clang-format')
files=[str(f) for folder in ('include','src','tests','bench','fuzz') for f in sorted((ROOT/folder).rglob('*')) if f.suffix in ('.hpp','.cpp')]
subprocess.run([str(binary),*(['--dry-run','--Werror'] if args.check else ['-i']),*files],check=True)
