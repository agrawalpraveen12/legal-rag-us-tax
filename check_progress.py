import json, os

cp = 'reports/eval_checkpoint.json'
if not os.path.exists(cp):
    print('No checkpoint file - eval not started yet')
else:
    with open(cp) as f:
        c = json.load(f)
    recs = c.get('records', [])
    print(f'Progress: {len(recs)}/100')
    print(f'Keys in checkpoint: {list(c.keys())}')
    if recs:
        print(f'Last query: {recs[-1].get("query_id")}')
    else:
        print('No records yet')
