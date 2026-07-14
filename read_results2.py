import json

with open('reports/evaluation_results.json') as f:
    r = json.load(f)

records = r.get('results', r.get('records', []))
successful = [x for x in records if x.get('status') == 'success']

def avg(lst): return sum(lst)/len(lst) if lst else 0

print(f'Successful: {len(successful)}/{len(records)}')
print()
print('=== OVERALL METRICS ===')
print(f'Reranked Recall@8: {avg([x.get("reranked_recall_8",0) for x in successful]):.1%}')
print(f'Reranked MRR:      {avg([x.get("reranked_mrr",0) for x in successful]):.1%}')
print(f'Citation Accuracy: {avg([x.get("citation_accuracy",0) for x in successful]):.1%}')
print(f'Faithfulness:      {avg([x.get("faithfulness",0) for x in successful]):.1%}')
print(f'Refusal Rate:      {avg([1 if x.get("is_refused") else 0 for x in successful]):.1%}')

print()
print('=== BY DOC TYPE ===')
for dt in ['act','judgment','pov','tax']:
    recs = [x for x in successful if x.get('doc_type')==dt]
    if recs:
        print(f'{dt} (n={len(recs)}): Recall@8={avg([x.get("reranked_recall_8",0) for x in recs]):.1%} | CitAcc={avg([x.get("citation_accuracy",0) for x in recs]):.1%} | Faith={avg([x.get("faithfulness",0) for x in recs]):.1%}')

print()
print('=== BY DIFFICULTY ===')
for diff in ['factual','interpretive','multi_hop','unanswerable']:
    recs = [x for x in successful if x.get('difficulty')==diff]
    if recs:
        print(f'{diff} (n={len(recs)}): Recall@8={avg([x.get("reranked_recall_8",0) for x in recs]):.1%} | CitAcc={avg([x.get("citation_accuracy",0) for x in recs]):.1%} | Faith={avg([x.get("faithfulness",0) for x in recs]):.1%}')

print()
m = r.get('aggregated_metrics', {})
if m:
    print('=== AGGREGATED METRICS (from file) ===')
    for k,v in m.items():
        print(f'{k}: {v}')
