"""Structure-aware retrieval over the pinned train/dev knowledge corpus.

No API calls or test annotations. The existing dense index is reused unchanged;
question masks and structural features are deterministic, local reranking tools.
"""
from collections import Counter,defaultdict
from contextlib import closing
import hashlib
import math
import re
import sqlite3
import threading
from sqlglot import exp,parse_one

from infrastructure import HybridRAG,BASELINE,DB,load,question_rows,normalized_question


CATEGORICAL_COLUMNS={
    'cost':('event_type',),
    'admissions':('admission_type','admission_location','discharge_location','language','insurance','marital_status'),
    'transfers':('eventtype','careunit'),
    'icustays':('first_careunit','last_careunit'),
    'prescriptions':('route','dose_unit_rx'),
    'patients':('gender',),
}
STOP={'a','an','the','of','on','in','at','for','is','was','are','were','has','have','had','what','which',
      'me','give','show','tell','please','patient','patients','recorded','record','records'}
TEMPORAL_WORDS={'first','last','earliest','latest','before','after','since','until','within','year','month','day',
                'years','months','days','week','weeks','today','yesterday'}


def tokens(text):
    return re.findall(r'[a-z][a-z0-9]*',text.casefold())


def features(question):
    """Question-only intent features; literals never become answer evidence."""
    q=question.casefold()
    patterns={
        'aggregate:count':r'\b(how many|number of|count|how often)\b',
        'aggregate:average':r'\b(average|mean|avg)\b',
        'aggregate:sum':r'\b(total|sum)\b',
        'aggregate:median':r'\bmedian\b',
        'quantile:percentile':r'\b(percentile|percentiles|quartile)\b',
        'ranking:extreme':r'\b(highest|lowest|largest|smallest|maximum|minimum|most|least|top)\b',
        'grouping:group':r'\b(each|per|grouped by|group by|by gender|by age)\b',
        'temporal:first':r'\b(first|earliest)\b',
        'temporal:last':r'\b(last|latest|recent)\b',
        'temporal:before':r'\bbefore\b',
        'temporal:after':r'\bafter\b',
        'temporal:interval':r'\b(since|until|within|between|during)\b',
        'calendar:year':r'\byears?\b',
        'calendar:month':r'\bmonths?\b',
        'calendar:day':r'\b(days?|today|yesterday)\b',
        'calendar:week':r'\bweeks?\b',
        'calendar:absolute':r'\b\d{4}-\d{1,2}(?:-\d{1,2})?\b|\b\d{1,2}/\d{1,2}\b',
        'negation:excluded':r'\b(not|never|without|except|no)\b',
        'scope:icu':r'\b(icu|intensive care)\b',
        'scope:admission':r'\b(admission|admitted|hospital|visit|discharge)\b',
        'clinical:diagnosis':r'\b(diagnosis|diagnosed|diagnoses|disease|icd)\b',
        'clinical:procedure':r'\b(procedure|procedures|surgery|operation)\b',
        'clinical:prescription':r'\b(drug|drugs|prescribed|prescription|medication|dose|dosage)\b',
        'clinical:microbiology':r'\b(culture|organism|specimen|microbiology|bacteria)\b',
        'clinical:lab':r'\b(lab|laboratory|test|tests)\b',
        'clinical:cost':r'\b(cost|costs|expensive|cheapest|charge|charges)\b',
        'clinical:measurement':r'\b(height|weight|temperature|heart rate|blood pressure|oxygen|respiration)\b',
        'scope:transfer':r'\b(transfer|transferred|care unit|careunit)\b',
    }
    return frozenset(key for key,pattern in patterns.items() if re.search(pattern,q))


def jaccard(a,b):
    return len(a&b)/len(a|b) if a or b else 0.


def sql_structure(sql):
    """AST features of known train/dev SQL only, never target/test SQL."""
    if sql.strip().casefold()=='null':
        return frozenset({'answer:null'})
    try:
        tree=parse_one(sql,read='sqlite')
    except Exception:
        return frozenset({'parse:unavailable'})
    found=set()
    if tree.find(exp.Group): found.add('shape:group_by')
    if tree.find(exp.Join): found.add('shape:join')
    if tree.find(exp.Order): found.add('shape:order')
    if tree.find(exp.Limit): found.add('shape:limit')
    if tree.find(exp.Window): found.add('shape:window')
    if len(list(tree.find_all(exp.Select)))>1: found.add('shape:nested')
    for function in tree.find_all(exp.Func):
        name=(function.name if isinstance(function,exp.Anonymous) else function.sql_name()).upper()
        if name in {'COUNT','AVG','SUM','MIN','MAX','MEDIAN'}:
            found.add('aggregate:'+{'AVG':'average'}.get(name,name.casefold()))
        if name in {'RANK','DENSE_RANK','ROW_NUMBER','PERCENT_RANK','CUME_DIST','NTILE'}:
            found.add('window:rank')
        if name in {'PERCENTILE_CONT','PERCENTILE_DISC','PERCENT_RANK','CUME_DIST','NTILE','QUANTILE'}:
            found.add('quantile:percentile')
    return frozenset(found)


def operator_expectations(question):
    """Soft alternative operators inferred from question wording, not rules."""
    intent=features(question)
    expected=[]
    for name in ['count','average','sum','median']:
        feature='aggregate:'+name
        if feature in intent: expected.append(frozenset({feature}))
    if 'grouping:group' in intent:
        expected.append(frozenset({'shape:group_by','shape:window'}))
    if intent&{'temporal:first','temporal:last','ranking:extreme'}:
        expected.append(frozenset({'shape:order','aggregate:min','aggregate:max','window:rank'}))
    if 'quantile:percentile' in intent:
        expected.append(frozenset({'quantile:percentile','window:rank','shape:order'}))
    if re.search(r'\b(above|below|greater than|less than)\s+(?:the\s+)?average\b',question,re.I):
        expected.append(frozenset({'shape:nested','shape:window'}))
    return expected


def operator_compatibility(expectations,known_sql_features):
    return sum(bool(alternatives&known_sql_features) for alternatives in expectations)/len(expectations) if expectations else .5


class BM25:
    def __init__(self,texts):
        self.lengths=[]
        self.postings=defaultdict(list)
        for index,text in enumerate(texts):
            terms=[t for t in tokens(text) if t not in STOP]
            self.lengths.append(len(terms))
            for term,count in Counter(terms).items():
                self.postings[term].append((index,count))
        self.n=len(self.lengths)
        self.average=sum(self.lengths)/max(1,self.n)

    def search(self,question,k=64):
        scores=defaultdict(float)
        for term in set(tokens(question))-STOP:
            hits=self.postings.get(term,[])
            weight=math.log(1+(self.n-len(hits)+.5)/(len(hits)+.5))
            for index,count in hits:
                scores[index]+=weight*count*2.5/(count+1.5*(.25+.75*self.lengths[index]/max(1,self.average)))
        return sorted(scores,key=lambda index:(-scores[index],index))[:k]


class LiteralMasker:
    """Longest token-phrase matches; never consume temporal operator words."""
    def __init__(self,labels):
        self.trie={}
        for label in labels:
            parts=tokens(str(label))
            if not parts or len(parts)>16 or any(part in TEMPORAL_WORDS for part in parts):
                continue
            if len(parts)==1 and (parts[0] in STOP or len(parts[0])<3):
                continue
            node=self.trie
            for part in parts:
                node=node.setdefault(part,{})
            node['__end__']=True

    def mask(self,text):
        text=text.casefold()
        text=re.sub(r'\b\d{8}\b',' patient_identifier ',text)
        text=re.sub(r'\b\d{4}-\d{1,2}(?:-\d{1,2})?(?:[ t]\d{1,2}:\d{2}(?::\d{2})?)?\b',' calendar_date ',text)
        text=re.sub(r'\b\d{1,2}/\d{1,2}(?:/\d{2,4})?\b',' calendar_date ',text)
        text=re.sub(r'\b(?:19|20|21|22)\d{2}\b',' calendar_year ',text)
        text=re.sub(r'\b\d+(?:\.\d+)?(?:st|nd|rd|th)?\b',' numeric_quantity ',text)
        # Quoted clinical literals can be lengthy or absent from the catalog.
        text=re.sub(r"'[^']+'|\"[^\"]+\"",' clinical_value ',text)
        pieces=tokens(text)
        result=[]
        start=0
        while start<len(pieces):
            node=self.trie
            end=start
            match=None
            while end<len(pieces) and pieces[end] in node:
                node=node[pieces[end]]
                end+=1
                if '__end__' in node:
                    match=end
            if match is not None:
                result.append('clinical_value')
                start=match
            else:
                result.append(pieces[start])
                start+=1
        # Keep temporal/ranking/percentile words. Remaining raw quantities need
        # not match to retrieve the same SQL pattern, but retain their position.
        return ' '.join(result)


def categorical_catalog(db=DB):
    """Low-cardinality metadata only; no patient identifiers or result rows."""
    records=[]
    values={}
    missing=[]
    with closing(sqlite3.connect(db.resolve().as_uri()+'?mode=ro',uri=True)) as con:
        con.execute('PRAGMA query_only=ON')
        for table,columns in CATEGORICAL_COLUMNS.items():
            actual={r[1] for r in con.execute(f'PRAGMA table_info("{table}")')}
            for column in columns:
                if column not in actual:
                    missing.append(table+'.'+column)
                    continue
                items=[r[0] for r in con.execute(f'SELECT DISTINCT "{column}" FROM "{table}" WHERE "{column}" IS NOT NULL ORDER BY "{column}"')]
                values[(table,column)]=set(items)
                for value in items:
                    label=str(value)
                    records.append({'id':table+':'+column+':'+label,'source':table,'column':column,
                                    'code':label,'label':label,'catalog_kind':'categorical_value'})
    return records,values,missing


class StructuredRAG:
    def __init__(self,excluded_ids=()):
        self.hybrid=HybridRAG()
        self.schema=self.hybrid.schema
        self.examples=self.hybrid.examples
        self.by_id=self.hybrid.by_id
        requested=set(excluded_ids)
        unknown=requested-set(self.by_id)
        if unknown:
            raise ValueError('Excluded knowledge IDs must belong to train/dev')
        blocked_questions={normalized_question(self.by_id[key]['question']) for key in requested}
        self.excluded_ids={key for key,row in self.by_id.items() if key in requested or normalized_question(row['question']) in blocked_questions}
        self.excluded_questions=blocked_questions
        extra,values,missing=categorical_catalog()
        self.catalog={**self.hybrid.catalog,**{r['id']:r for r in extra}}
        self.known_values={key:set(items) for key,items in self.hybrid.known_values.items()}
        self.known_values.update(values)
        self.known_values[('prescriptions','drug')]={r['label'] for r in self.hybrid.catalog.values() if r['source']=='prescriptions' and r['column']=='drug'}
        self.medical=list(self.catalog.values())
        self.masker=LiteralMasker(r['label'] for r in self.medical)
        self.masked=[self.masker.mask(r['question']) for r in self.examples]
        self.masked_terms=[set(tokens(text))-STOP for text in self.masked]
        self.example_features=[features(r['question']) for r in self.examples]
        self.example_sql_features=[sql_structure(r['sql']) for r in self.examples]
        self.masked_lexical=BM25(self.masked)
        self.medical_lexical=BM25([r['source']+' '+r['column']+' '+r['label'] for r in self.medical])
        self.index_by_id={r['id']:index for index,r in enumerate(self.examples)}
        self._masked_vectors={}
        self.lock=self.hybrid.lock
        self.manifest={**self.hybrid.manifest,'retriever':'masked_question_and_known_SQL_structure_reranker_v3',
            'SQL_structure_protocol':'Question-inferred soft operators compared to train/dev SQL AST; no preliminary or target SQL used',
            'knowledge_SQL_parse_failures':sum('parse:unavailable' in fs for fs in self.example_sql_features),
            'dense_index_reused_unchanged':True,'full_schema_retained':True,'catalog_records':len(self.catalog),
            'categorical_columns':{table:[column for column in columns if (table,column) in values] for table,columns in CATEGORICAL_COLUMNS.items()},
            'categorical_metadata_records':len(extra),'missing_optional_categorical_columns':missing,
            'excluded_knowledge_ids_count':len(self.excluded_ids),
            'excluded_knowledge_ids_sha256':hashlib.sha256('\n'.join(sorted(self.excluded_ids)).encode()).hexdigest(),
            'active_knowledge_questions':len(self.by_id)-len(self.excluded_ids),
            'catalog_policy':'Dictionary and categorical metadata; candidate top-K is never evidence of unavailability'}

    def retrieve(self,question,route='direct',exclude_id=None):
        masked=self.masker.mask(question)
        with self.lock:
            # Reuse full-schema dense clinical retrieval and existing vectors.
            base=self.hybrid.base
            context=base.retrieve(question,'full_schema')
            collection=base.collections[base.examples_collection]
            dense=collection.query(query_embeddings=base.query_cache[question],n_results=min(64,len(self.by_id)),include=['distances'])
            if masked not in self._masked_vectors:
                self._masked_vectors[masked]=base.model.encode([masked],normalize_embeddings=True,show_progress_bar=False).tolist()
            structural_dense=collection.query(query_embeddings=self._masked_vectors[masked],n_results=min(64,len(self.by_id)),include=['distances'])
        blocked=set(self.excluded_ids)
        if exclude_id is not None:
            blocked.add(exclude_id)
            target=normalized_question(self.by_id[exclude_id]['question'] if exclude_id in self.by_id else question)
            blocked.update(key for key,row in self.by_id.items() if normalized_question(row['question'])==target)
        pools=[dense['ids'][0],structural_dense['ids'][0],
               [self.examples[index]['id'] for index in self.hybrid.lexical.search(question,64)],
               [self.examples[index]['id'] for index in self.masked_lexical.search(masked,64)]]
        ranks=defaultdict(float)
        distances={key:distance for key,distance in zip(dense['ids'][0],dense['distances'][0])}
        weights=(1.2,.8,1.,1.) if route=='direct' else (.8,1.2,.8,1.2)
        for pool,weight in zip(pools,weights):
            for rank,key in enumerate(pool):
                if key in self.by_id and key not in blocked:
                    ranks[key]+=weight/(40+rank)
        # Even pathological exclusions must not allow fallback to blocked data.
        if len(ranks)<4:
            for row in self.examples:
                if row['id'] not in blocked:
                    ranks.setdefault(row['id'],0.)
        query_features=features(question)
        expected_operators=operator_expectations(question)
        query_terms=set(tokens(masked))-STOP
        maximum=max(ranks.values(),default=1.) or 1.
        scored=[]
        for key,rank_score in ranks.items():
            index=self.index_by_id[key]
            type_match=jaccard(query_features,self.example_features[index])
            masked_match=jaccard(query_terms,self.masked_terms[index])
            sql_match=operator_compatibility(expected_operators,self.example_sql_features[index])
            score=.40*rank_score/maximum+.25*type_match+.20*masked_match+.15*sql_match
            scored.append((score,key,type_match,masked_match,sql_match))
        scored.sort(key=lambda row:(-row[0],row[1]))
        selected=[]
        remaining=list(scored)
        while remaining and len(selected)<4:
            def diversity_score(row):
                index=self.index_by_id[row[1]]
                duplicate=max((float(self.masked[index]==self.masked[self.index_by_id[old[1]]]) for old in selected),default=0.)
                return row[0]-.08*duplicate
            chosen=max(remaining,key=lambda row:(diversity_score(row),row[0],row[1]))
            selected.append(chosen)
            remaining.remove(chosen)
        def example(row):
            score,key,type_match,masked_match,sql_match=row
            return {**self.by_id[key],'retrieval_score':score,'question_type_agreement':type_match,
                    'masked_question_similarity':masked_match,'dense_distance':distances.get(key),
                    'SQL_structure_agreement':sql_match,'known_SQL_features':sorted(self.example_sql_features[self.index_by_id[key]])}
        examples=[example(row) for row in selected]
        null_neighbors=[example(row) for row in scored if self.by_id[row[1]]['sql']=='null'][:2]
        # Exact entity names first, then lexical/dense candidates; source.column
        # accompanies every value. An absent candidate never implies no answer.
        normalized=' '+normalized_question(question)+' '
        exact=[]
        for row in self.medical:
            label=normalized_question(str(row['label']))
            if len(label)>=3 and ' '+label+' ' in normalized:
                exact.append(row)
        exact.sort(key=lambda row:(-len(normalized_question(str(row['label']))),row['id']))
        medical_candidates=exact+[self.medical[index] for index in self.medical_lexical.search(question,12)]
        medical_candidates += [self.catalog[row['id']] for row in context['medical'] if row['id'] in self.catalog]
        seen=set()
        medical=[]
        for row in medical_candidates:
            if row['id'] not in seen:
                seen.add(row['id'])
                medical.append(dict(row))
        selected_ids={row['id'] for row in examples+null_neighbors}
        if selected_ids&blocked:
            raise AssertionError('Excluded calibration knowledge reached the prompt')
        top=[row[0] for row in scored[:2]]
        confidence={'kind':'retrieval_metadata_not_probability','example_support_count':len(examples),
            'top_rerank_score':top[0] if top else None,'top_score_margin':top[0]-top[1] if len(top)>1 else None,
            'mean_question_type_agreement':sum(row['question_type_agreement'] for row in examples)/len(examples) if examples else None,
            'mean_SQL_structure_agreement':sum(row['SQL_structure_agreement'] for row in examples)/len(examples) if examples else None,
            'best_dense_cosine_similarity':max((1-distance for key,distance in distances.items() if key not in blocked),default=None),
            'exact_catalog_matches':len(exact),'null_neighbor_count':len(null_neighbors)}
        return {'tables':sorted(self.schema),'medical':medical[:16],'examples':examples,'null_neighbors':null_neighbors,
            'knowledge_splits':['train','dev'],'excluded_self_id':exclude_id,'self_exclusion_count':len(blocked),
            'global_exclusion_count':len(self.excluded_ids),'masked_question':masked,'question_features':sorted(query_features),
            'question_operator_expectations':[sorted(alternatives) for alternatives in expected_operators],
            'retrieval_route':route,'retrieval_confidence':confidence,'catalog_candidates_exhaustive':False,
            'catalog_availability_note':'Top-K candidates are suggestions; lack of a match does not establish unanswerability.'}
