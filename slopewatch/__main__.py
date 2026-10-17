import argparse
import json
from pathlib import Path
import sys
from .models import training_csv,train,ModelError

def main():
    parser=argparse.ArgumentParser(description='SlopeWatch NER research tools')
    sub=parser.add_subparsers(dest='command',required=True)
    example=sub.add_parser('example-training');example.add_argument('--output',type=Path,required=True)
    training=sub.add_parser('train');training.add_argument('csv',type=Path);training.add_argument('--output',type=Path,required=True);training.add_argument('--name',default='Local research candidate')
    args=parser.parse_args()
    try:
        if args.command=='example-training':args.output.write_text(training_csv());return 0
        if args.csv.stat().st_size>2_000_000:raise ModelError('CSV exceeds 2 MB.')
        model=train(args.csv.read_text(encoding='utf-8-sig'),args.name)
        args.output.write_text(json.dumps(model,indent=2)+'\n');print(json.dumps({k:v for k,v in model.items() if k!='trees'},indent=2));return 0
    except (OSError,UnicodeError,ModelError) as exc:print(str(exc),file=sys.stderr);return 2
if __name__=='__main__':sys.exit(main())
