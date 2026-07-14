import json

with open('reports/eval_checkpoint.json') as f:
    c = json.load(f)

records = c['records']
successful = [r for r in records if r['status'] == 'success']
errors = [r for r in records if r['status'] != 'success']
print(f'Successful: {len(successful)}/100')
print(f'Errors: {len(errors)}')

def avg(lst): return sum(lst)/len(lst) if lst else 0

metrics = {
    'Hybrid Recall@1':   avg([r['hybrid_recall_1'] for r in successful]),
    'Hybrid Recall@3':   avg([r['hybrid_recall_3'] for r in successful]),
    'Hybrid Recall@5':   avg([r['hybrid_recall_5'] for r in successful]),
    'Hybrid Recall@10':  avg([r['hybrid_recall_10'] for r in successful]),
    'Hybrid MRR':        avg([r['hybrid_mrr'] for r in successful]),
    'Reranked Recall@1': avg([r['reranked_recall_1'] for r in successful]),
    'Reranked Recall@3': avg([r['reranked_recall_3'] for r in successful]),
    'Reranked Recall@5': avg([r['reranked_recall_5'] for r in successful]),
    'Reranked Recall@8': avg([r['reranked_recall_8'] for r in successful]),
    'Reranked MRR':      avg([r['reranked_mrr'] for r in successful]),
    'Citation Accuracy': avg([r['citation_accuracy'] for r in successful]),
    'Faithfulness':      avg([r['faithfulness'] for r in successful]),
    'Refusal Rate':      avg([1 if r['is_refused'] else 0 for r in successful]),
}

print('\n=== OVERALL METRICS ===')
for k,v in metrics.items():
    print(f'{k}: {v:.1%}')

print('\n=== BY DOC TYPE ===')
for dt in ['act','judgment','pov','tax']:
    recs = [r for r in successful if r['doc_type']==dt]
    if recs:
        r8  = avg([r['reranked_recall_8'] for r in recs])
        ca  = avg([r['citation_accuracy'] for r in recs])
        fa  = avg([r['faithfulness'] for r in recs])
        print(f'{dt} (n={len(recs)}): Recall@8={r8:.1%} | CitAcc={ca:.1%} | Faith={fa:.1%}')

print('\n=== BY DIFFICULTY ===')
for diff in ['factual','interpretive','multi_hop','unanswerable']:
    recs = [r for r in successful if r['difficulty']==diff]
    if recs:
        r8  = avg([r['reranked_recall_8'] for r in recs])
        ca  = avg([r['citation_accuracy'] for r in recs])
        fa  = avg([r['faithfulness'] for r in recs])
        print(f'{diff} (n={len(recs)}): Recall@8={r8:.1%} | CitAcc={ca:.1%} | Faith={fa:.1%}')

print('\n=== CITATION BUG CHECK ===')
bug = [r for r in successful if r['citation_accuracy']==0 and not r['is_refused'] and r['generated_answer'] and 'Page' in r['generated_answer']]
print(f'Answers with Page in text but empty generated_citations: {len(bug)}')
