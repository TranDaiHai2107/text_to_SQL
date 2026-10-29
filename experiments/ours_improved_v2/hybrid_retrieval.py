"""Hybrid example retrieval and metadata grounding without test annotations."""
from collections import Counter,defaultdict
from contextlib import closing
import math
import re
import sqlite3
import threading
from common import BASELINE,DB,load,question_rows,normalized_question
from retrieval import ThreeRAG,dictionary_records

STOP={'what','which','how','is','are','was','were','the','a','an','of','for','to','in','on','at','and','with',
      'me','give','show','tell','patient','patients','recorded','record','records','please','there','has','have','had'}
PLURALS={'drugs':'drug','tests':'test','diagnoses':'diagnosis','procedures':'procedure','admissions':'admission',
         'visits':'visit','encounters':'encounter','measurements':'measurement','patients':'patient'}


def terms(text):
    return [PLURALS.get(t,t) for t in re.findall(r'[a-z][a-z0-9]*',text.casefold()) if t not in STOP and not t.isdigit()]


class BM25:
    def __init__(self,texts):
        self.lengths=[]
        self.postings=defaultdict(list)
        for i,text in enumerate(texts):
            tokens=terms(text)
            self.lengths.append(len(tokens))
            for token,count in Counter(tokens).items():
                self.postings[token].append((i,count))
        self.n=len(texts)
        self.average=sum(self.lengths)/max(1,self.n)

    def search(self,query,k=32):
        scores=defaultdict(float)
        for token in set(terms(query)):
            hits=self.postings.get(token,[])
            weight=math.log(1+(self.n-len(hits)+.5)/(len(hits)+.5))
            for i,count in hits:
                denominator=count+1.5*(.25+.75*self.lengths[i]/max(1,self.average))
                scores[i]+=weight*count*2.5/denominator
        return sorted(scores,key=lambda i:(-scores[i],i))[:k]


def enriched_catalog():
    records={row['id']:dict(row) for row in dictionary_records()}
    values={}
    with closing(sqlite3.connect(DB.resolve().as_uri()+'?mode=ro',uri=True)) as con:
        for table,column in [('d_items','label'),('d_labitems','label'),
                             ('d_icd_diagnoses','long_title'),('d_icd_procedures','long_title')]:
            values[(table,column)]={r[0] for r in con.execute(f'SELECT DISTINCT {column} FROM {table} WHERE {column} IS NOT NULL')}
        for code,label,abbreviation,linksto in con.execute('SELECT itemid,label,abbreviation,linksto FROM d_items'):
            key='d_items:'+str(code)
            if key in records:
                records[key].update(column='label',abbreviation=abbreviation or '',linksto=linksto or '')
        for key,row in records.items():
            row.setdefault('column','long_title' if row['source'].startswith('d_icd_') else 'label' if row['source'].startswith('d_') else 'drug')
        for column in ['spec_type_desc','test_name','org_name']:
            items=[r[0] for r in con.execute(f'SELECT DISTINCT {column} FROM microbiologyevents WHERE {column} IS NOT NULL ORDER BY {column}')]
            values[('microbiologyevents',column)]=set(items)
            for label in items:
                key='microbiologyevents:'+column+':'+label
                records[key]={'id':key,'source':'microbiologyevents','column':column,'code':label,'label':label}
    return records,values


class HybridRAG:
    def __init__(self):
        self.base=ThreeRAG(knowledge_splits=('train','dev'))
        self.manifest=self.base.build()
        self.schema=self.base.schema
        self.lock=threading.Lock()
        self.examples=[]
        for split in ['train','dev']:
            labels=load(BASELINE/'data/gold'/split/'label.json')
            self.examples.extend({'id':r['id'],'question':r['question'],'sql':labels[r['id']],
                                  'source':'EHRSQL_'+split} for r in question_rows(split))
        self.by_id={r['id']:r for r in self.examples}
        self.lexical=BM25([r['question'] for r in self.examples])
        self.catalog,self.known_values=enriched_catalog()
        self.medical=list(self.catalog.values())
        self.medical_lexical=BM25([r['source']+' '+r['column']+' '+r['label'] for r in self.medical])

    def retrieve(self,question,exclude_id=None):
        with self.lock:
            ctx=self.base.retrieve(question,'full_schema')
            result=self.base.collections[self.base.examples_collection].query(
                query_embeddings=self.base.query_cache[question],n_results=32,
                include=['metadatas','distances'])
        excluded={key for key,row in self.by_id.items() if key==exclude_id or normalized_question(row['question'])==normalized_question(question)} if exclude_id else set()
        ranks=defaultdict(float)
        pools=[result['ids'][0],[self.examples[i]['id'] for i in self.lexical.search(question,40)]]
        for pool in pools:
            for rank,key in enumerate(pool):
                if key not in excluded:
                    ranks[key]+=1/(40+rank)
        ordered=sorted(ranks,key=lambda key:(-ranks[key],key))
        examples=[self.by_id[key] for key in ordered[:4]]
        null_neighbors=[self.by_id[key] for key in ordered if self.by_id[key]['sql']=='null'][:2]
        # Lexical catalog candidates recover exact names missed by generic dense
        # embeddings, including microbiology values. Dense candidates remain.
        candidates=[self.medical[i] for i in self.medical_lexical.search(question,5)]
        candidates += [self.catalog[r['id']] for r in ctx['medical'] if r['id'] in self.catalog]
        seen=set()
        medical=[]
        for row in candidates:
            if row['id'] not in seen:
                seen.add(row['id'])
                medical.append(row)
        return {'tables':sorted(self.schema),'medical':medical[:10],'examples':examples,
                'null_neighbors':null_neighbors,'knowledge_splits':['train','dev'],
                'excluded_self_id':exclude_id,'self_exclusion_count':len(excluded)}
