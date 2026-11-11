"""Deterministic evidence handles: models cite IDs, never reconstruct SQL spans."""
from sqlglot import Dialect,exp,parse_one
from sqlglot.tokens import TokenType


def align_span(sql,fragment,dialect='sqlite'):
    if not isinstance(fragment,str) or not fragment.strip():return None
    if fragment in sql:return fragment
    try:
        tokenizer=Dialect.get_or_raise(dialect)
        hay=tokenizer.tokenize(sql);needle=tokenizer.tokenize(fragment)
        if not needle:return None
        def key(t):return (t.token_type,t.text if t.token_type in {TokenType.STRING,TokenType.IDENTIFIER} else t.text.casefold())
        wanted=[key(t) for t in needle]
        for start in range(len(hay)-len(needle)+1):
            if [key(t) for t in hay[start:start+len(needle)]]==wanted:
                return sql[hay[start].start:hay[start+len(needle)-1].end+1]
    except Exception:return None
    return None


def build_catalog(sql,prefix,dialect='sqlite',limit=64):
    tree=parse_one(sql,read=dialect);items=[];seen=set()
    def add(node):
        text=align_span(sql,node.sql(dialect=dialect),dialect)
        if text and text not in seen and len(text)<=320 and len(items)<limit-1:
            seen.add(text);items.append({'id':prefix+':e'+str(len(items)+1),'kind':type(node).__name__,'sql':text})
    for select in tree.find_all(exp.Select):
        for projection in select.expressions:add(projection)
    types=(exp.Predicate,exp.Window,exp.AggFunc,exp.Group,exp.Order,exp.Limit,exp.Join)
    for node in tree.walk():
        if isinstance(node,types):add(node)
    for node in tree.walk():
        if isinstance(node,(exp.Column,exp.Table)):add(node)
    items.append({'id':prefix+':query','kind':'whole_query','sql':sql})
    return items


def public_catalog(catalog):
    return [{k:v for k,v in item.items() if not (item['kind']=='whole_query' and k=='sql')} for item in catalog]


def resolve_ids(catalog,ids):
    if not isinstance(ids,list) or not 1<=len(ids)<=8 or any(not isinstance(i,str) for i in ids):
        raise ValueError('Cite 1-8 evidence IDs from the provided catalog')
    known={item['id']:item['sql'] for item in catalog}
    if any(i not in known for i in ids):raise ValueError('Unknown evidence ID; use IDs from this candidate, not another candidate')
    return [known[i] for i in ids]
