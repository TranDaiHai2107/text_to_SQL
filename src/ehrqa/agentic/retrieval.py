"""Sequential schema/catalog/examples retrieval; fixed three demonstrations."""
import re

STOP=set('the a an of in on for to is are was were what which how many patient patients this last first year month day hospital show list me please'.split())


def terms(text):return set(re.findall(r'[^\W\d_]+',text.casefold(),flags=re.UNICODE))-STOP


def schema_first(question,schema):
    q=terms(question)
    ranked=sorted(schema.tables,key=lambda t:(-len(q & terms(t.replace('_',' ')+' '+schema.descriptions.get(t,'')+' '+' '.join(schema.tables[t]))),t))
    selected=set(ranked[:4])|({'patients','admissions'}&set(schema.tables))
    names=schema.join_closure(selected)
    return {'tables':names,'text':'\n'.join(schema.ddl[t] for t in names),
            'full_schema_available':True,'relationships':schema.payload(names)['relationships'],
            'retrieval_kind':'schema_lexical_plus_declared_join_paths','found':True}


def catalog_search(connection,schema,question,tables,definitions,limit=24):
    tokens=sorted((t for t in terms(question) if len(t)>=3),key=lambda x:(-len(x),x))[:8]
    records={}
    for table,column,code in definitions:
        if not schema.has_ref(table+'.'+column) or not schema.has_ref(table+'.'+code):continue
        # Catalog scope depends on schema retrieval, with dictionary fallback for
        # recall. Candidate absence remains unknown, not evidence of absence.
        if table not in tables and not table.startswith('d_'):continue
        clauses=[];params=[]
        for token in tokens:
            clauses.append('LOWER("'+column+'") LIKE ? ESCAPE \'\\\'')
            params.append('%'+token.replace('\\','\\\\').replace('%','\\%').replace('_','\\_')+'%')
        if not clauses:continue
        extras=[c for c in ['icd_version','linksto','abbreviation','unitname','fluid','category'] if c in schema.tables[table] and c not in {code,column}]
        extra_sql=''.join(',"'+c+'"' for c in extras)
        sql='SELECT DISTINCT "'+code+'","'+column+'"'+extra_sql+' FROM "'+table+'" WHERE '+ ' OR '.join(clauses)+' ORDER BY "'+column+'","'+code+'" LIMIT 24'
        for row in connection.execute(sql,params):
            value,label=row[:2]
            if label is None:continue
            label=str(label)
            overlap=len(terms(label)&terms(question))
            exact=bool(re.search(r'(?<!\w)'+re.escape(label.casefold())+r'(?!\w)',question.casefold()))
            metadata=dict(zip(extras,row[2:]))
            key=table+':'+column+':'+str(value)+':'+str(metadata.get('icd_version',''))+':'+label
            records[key]={'id':key,'table':table,'column':column,'code_column':code,'code':value,'label':label,
                'match':'exact_surface' if exact else 'lexical_candidate','score':int(exact)*100+overlap,
                'candidate_list_complete':False}
            records[key].update(metadata)
    return sorted(records.values(),key=lambda r:(-r['score'],r['id']))[:limit]


class SequentialRAG:
    def __init__(self,database,examples,*,schema_callback=None,clinical_callback=None,catalog_callback=None):
        self.db=database
        self.examples_callback=examples
        self.schema_callback=schema_callback
        self.clinical_callback=clinical_callback
        self.catalog_callback=catalog_callback

    def schema(self,question):
        result=self.schema_callback(question) if self.schema_callback else schema_first(question,self.db.schema)
        result['tables']=self.db.schema.join_closure(result.get('tables',[]))
        if not result['tables']:result['tables']=sorted(self.db.schema.tables)
        result['relationships']=self.db.schema.payload(result['tables'])['relationships']
        result['text']='\n'.join(self.db.schema.ddl[t] for t in result['tables'])
        return result

    def clinical(self,question,schema_context):
        records=self.db.catalog_search(question,schema_context['tables'])
        if self.catalog_callback:
            extra=self.catalog_callback(question,schema_context)
            known={r['id'] for r in records}
            records.extend(r for r in extra if r['id'] not in known)
        legacy=self.clinical_callback(question) if self.clinical_callback else {'codes':[],'found':False}
        if hasattr(self.db,'lookup_codes'):
            extra=self.db.lookup_codes(legacy.get('codes',[]))
            known={r['id'] for r in records}
            records.extend(r for r in extra if r['id'] not in known)
        # Existing ICD layer remains available, but retrieved codes are evidence
        # candidates rather than mandatory OR filters.
        return {'records':records,'legacy_icd':legacy,'candidate_list_complete':False,
                'retrieval_kind':'lexical_plus_dense_dictionary' if self.catalog_callback else 'catalog_plus_legacy_semantic_icd',
                'schema_tables_used':schema_context['tables'],'found':bool(records) or legacy.get('found',False)}

    def examples(self,question,*,query_id=None):
        # Original or contextualized multi-turn question, same fixed count;
        # no self-taught examples or test-label-based selection.
        return self.examples_callback(question) if query_id is None else self.examples_callback(question,query_id=query_id)



