"""Container-only synthetic runner. Never adopts an existing unmarked directory."""
import argparse
import os
from pathlib import Path
import sys
from synthetic_dealership import ROOT, clean_environment, create


def seed(root):
    root = Path(root).resolve()
    if root.exists():
        clean_environment(root)  # Refuse unrelated or incomplete volumes.
        for file in ('dealer/graph.json', 'dealer/credentials.json'):
            if not (root/file).is_file():
                raise ValueError('Incomplete synthetic volume; refusing to replace data')
        return 'preserved'
    create(root)
    return 'created'


def serve(root, service):
    root = Path(root).resolve()
    env = clean_environment(root)
    env['PYTHONPATH'] = os.pathsep.join([str(ROOT/('backend' if service == 'dealer' else 'hub')), str(ROOT/'scripts')])
    port = '8317' if service == 'dealer' else '9317'
    os.chdir(root/service)
    os.execve(sys.executable, [sys.executable, '-m', 'uvicorn', f'synthetic_{service}:app',
                           '--host', '0.0.0.0', '--port', port, '--lifespan', 'off',
                           '--no-access-log'], env)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['seed','dealer','hub'])
    parser.add_argument('directory')
    args = parser.parse_args()
    if args.action == 'seed':
        print('Synthetic volume '+seed(args.directory))
    else:
        raise SystemExit(serve(args.directory, args.action))
