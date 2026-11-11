"""Resolve checked pairwise preferences, including explicit semantic equivalence."""
from itertools import combinations


def resolve(candidate_ids,relations):
    ids=sorted(candidate_ids)
    if not ids:return {'selected_id':None,'reason':'No eligible candidates'}
    if len(set(ids))!=len(ids):raise ValueError('Duplicate candidate ID')
    if len(ids)==1:return {'selected_id':ids[0],'equivalent_ids':ids,'reason':'One checked candidate'}
    pairs={}
    parent={i:i for i in ids}
    def find(x):
        while parent[x]!=x:x=parent[x]
        return x
    for r in relations:
        a,b=r['left'],r['right'];key=frozenset([a,b])
        if a not in parent or b not in parent or a==b or key in pairs:raise ValueError('Invalid/duplicate pair')
        if type(r['equivalent']) is not bool or r['winner'] not in {None,a,b}:raise ValueError('Invalid pair decision')
        if r['equivalent'] and r['winner'] is not None:raise ValueError('Equivalence is not a directional preference')
        pairs[key]=r
        if r['equivalent']:parent[find(b)]=find(a)
    if set(pairs)!={frozenset(pair) for pair in combinations(ids,2)}:raise ValueError('Missing pairwise comparison')
    groups={}
    for i in ids:groups.setdefault(find(i),[]).append(i)
    for group in groups.values():
        if any(not pairs[frozenset(pair)]['equivalent'] for pair in combinations(group,2)):
            return {'selected_id':None,'reason':'Inconsistent equivalence claims'}
    dominant=[]
    for group in groups.values():
        others=set(ids)-set(group)
        if all(pairs[frozenset([a,b])]['winner']==a for a in group for b in others):dominant.append(group)
    if len(dominant)!=1:return {'selected_id':None,'reason':'Preferences unresolved, cyclic or position-sensitive'}
    group=sorted(dominant[0])
    return {'selected_id':group[0],'equivalent_ids':group,
            'reason':'Canonical representative of a checked equivalence class' if len(group)>1 else 'Consistent pairwise winner'}
