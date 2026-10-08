import argparse
import json
import sys
from .runner import run
from .locking import job_lock
from .store import Store

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--config',default='config/local.json')
    parser.add_argument('--new-cycle',action='store_true',help='Revisit completed queue, retaining deduplication')
    parser.add_argument('--scheduled',action='store_true',help='One scheduler tick; do not restart review/failed jobs')
    args = parser.parse_args()
    with open(args.config,encoding='utf-8') as f:
        config = json.load(f)
    try:
        with job_lock(config['storage']['database']):
            if args.scheduled:
                store=Store(config['storage']['database']); previous=store.load(config['job_id']); store.db.close()
                if previous and previous['state'] in ('needs_review','failed'):
                    print('Scheduler stopped: job needs operator review')
                    return 2
            result = run(config,args.new_cycle or args.scheduled)
    except BlockingIOError:
        print('Another process holds this job lock',file=sys.stderr)
        return 3
    print(json.dumps(result,ensure_ascii=False,indent=2))
    return 2 if result['state'] in ('needs_review','failed') else 0

if __name__ == '__main__':
    sys.exit(main())
