"""Connect the full agentic pipeline to the MIMIC-IV PostgreSQL app."""
import json

from .database import QueryResult
from .schema import Schema
from .retrieval import catalog_search,SequentialRAG


class PostgresDatabase:
    def __init__(self,engine,records,execute_callback,max_rows=10000):
        self.engine=engine
        self.schema=Schema.from_records(records,'postgres')
        self.execute_callback=execute_callback
        self.max_rows=max_rows

    def execute(self,sql,question=''):
        inspection=self.schema.inspect(sql,question)
        if not inspection['valid']:raise ValueError('; '.join(inspection['errors']))
        from sqlalchemy.exc import OperationalError
        try:df=self.execute_callback(sql,max_rows=self.max_rows+1)
        except OperationalError:raise ConnectionError('PostgreSQL unavailable/timeout') from None
        import pandas as pd
        rows=[tuple(None if pd.isna(v) else v for v in row) for row in df.itertuples(index=False,name=None)]
        return QueryResult(list(df.columns),rows[:self.max_rows],len(df)<=self.max_rows)

    def catalog_search(self,question,tables,limit=24):
        from sqlalchemy import text
        definitions=[('d_icd_diagnoses','long_title','icd_code'),('d_icd_procedures','long_title','icd_code'),
            ('d_labitems','label','itemid'),('d_items','label','itemid'),('transfers','careunit','careunit'),
            ('prescriptions','drug','drug'),('prescriptions','route','route'),
            ('microbiologyevents','org_name','org_name'),('microbiologyevents','spec_type_desc','spec_type_desc')]
        with self.engine.connect().execution_options(postgresql_readonly=True) as conn:
            with conn.begin():
                conn.execute(text('SET LOCAL statement_timeout = 5000'))
                class Bound:
                    def execute(self,sql,params):
                        parts=sql.split('?')
                        rebuilt=parts[0]+''.join(':p'+str(i)+part for i,part in enumerate(parts[1:]))
                        return conn.execute(text(rebuilt),{'p'+str(i):v for i,v in enumerate(params)})
                return catalog_search(Bound(),self.schema,question,tables,definitions,limit)

    def lookup_codes(self,codes):
        from sqlalchemy import text
        output=[]
        with self.engine.connect().execution_options(postgresql_readonly=True) as c:
            with c.begin():
                c.execute(text('SET LOCAL statement_timeout = 5000'))
                for item in codes:
                    for table in ['d_icd_diagnoses','d_icd_procedures']:
                        if table not in self.schema.tables:continue
                        sql=f'SELECT icd_code,icd_version,long_title FROM {table} WHERE icd_code=:code AND icd_version=:version LIMIT 4'
                        for code,version,label in c.execute(text(sql),{'code':item['icd_code'],'version':item['icd_version']}):
                            output.append({'id':f'{table}:icd_code:{code}:{version}:{label}','table':table,
                                'column':'long_title','code_column':'icd_code','code':code,'icd_version':version,
                                'label':label,'match':'legacy_semantic_candidate','candidate_list_complete':False})
        return output


def application_pipeline(*,engine,execute_callback,schema_callback,clinical_callback,examples_callback,max_repairs=2):
    from ehrqa.config import SCHEMA_FILE,EXAMPLES_FILE,BASE_DIR,MAX_EVAL_ROWS
    from .gateway import Gateway,ModelSettings
    from .pipeline import FullAgentic,Config
    db=PostgresDatabase(engine,json.loads(SCHEMA_FILE.read_text(encoding='utf-8')),execute_callback,MAX_EVAL_ROWS)
    examples=json.loads(EXAMPLES_FILE.read_text(encoding='utf-8'))
    source_ids={(r['question_vi'],r['sql']):r['id'] for r in examples}
    def traced_examples(question):
        context=examples_callback(question)
        context['items']=[{**r,'id':source_ids.get((r['question_vi'],r['sql']),'unmapped'),
                           'source':'application_examples'} for r in context['items']]
        return context
    rag=SequentialRAG(db,traced_examples,schema_callback=schema_callback,clinical_callback=clinical_callback)
    return FullAgentic(db,rag,Gateway(ModelSettings.from_env()),
                       Config('postgres',max_repairs=max_repairs,log_dir=BASE_DIR/'results/agentic_traces'))


def legacy_result(output):
    import pandas as pd
    selected=output.get('selected')
    history=[]
    for candidate in output['candidates']:
        history.extend({**h,'candidate_id':candidate['id']} for h in candidate.get('history',[]))
    if not history and output['status']=='error':history=[{'attempt':1,'sql':output['sql'],'error':output['reason']}]
    result=selected['result'] if selected else None
    return {**output,'success':output['status']=='answered','df':pd.DataFrame(result.rows,columns=result.columns) if result else None,
            'attempts':max((h['attempt'] for h in history),default=1),'history':history}
