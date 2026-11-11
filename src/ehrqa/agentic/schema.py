"""Profile-specific schema, relationship grounding and read-only SQL inspection."""
from collections import deque
from dataclasses import dataclass, field
import re

from sqlglot import exp, parse, parse_one
from sqlglot.optimizer.qualify import qualify
from sqlglot.optimizer.scope import traverse_scope
from sqlglot.optimizer.normalize_identifiers import normalize_identifiers

TABLE_MEANINGS={
    'patients':'Patient demographics and mortality',
    'admissions':'Hospital admissions, encounter scope, admission and discharge',
    'transfers':'Hospital location and care-unit transfer history',
    'icustays':'Intensive care stays, ICU unit and stay scope',
    'diagnoses_icd':'Diagnosis events and ICD disease codes',
    'procedures_icd':'Procedures and treatment events with ICD codes',
    'd_icd_diagnoses':'Dictionary mapping diagnosis ICD codes to disease titles',
    'd_icd_procedures':'Dictionary mapping procedure ICD codes to procedure titles',
    'd_labitems':'Laboratory item dictionary', 'd_items':'ICU measurement, input and output item dictionary',
    'labevents':'Laboratory measurements and test results', 'chartevents':'ICU vital signs and observed measurements',
    'inputevents':'ICU administered inputs and fluids','outputevents':'ICU outputs including urine and drainage',
    'prescriptions':'Historical prescribed medications, doses and administration routes',
    'microbiologyevents':'Microbiology specimen tests, organisms and culture results',
    'cost':'Recorded costs of typed clinical events'}


@dataclass
class Schema:
    tables: dict
    ddl: dict
    dialect: str
    descriptions: dict = field(default_factory=dict)
    edges: list = field(default_factory=list)

    def __post_init__(self):
        for table in self.tables:self.descriptions.setdefault(table,TABLE_MEANINGS.get(table,table))

    @classmethod
    def from_records(cls, records, dialect='postgres'):
        tables,ddl,descriptions={},{},{}
        for row in records:
            tree=parse_one(row['ddl'],read=dialect)
            name=row['table']
            tables[name]={c.name:c.args['kind'].sql(dialect=dialect) for c in tree.find_all(exp.ColumnDef)}
            ddl[name]=row['ddl']
            descriptions[name]=row.get('description_en',row.get('description_vi',name))
        s=cls(tables,ddl,dialect,descriptions)
        s.add_declared_relations()
        return s

    def has_ref(self, ref):
        if not isinstance(ref,str) or ref.count('.')!=1:return False
        t,c=ref.split('.')
        return t in self.tables and c in self.tables[t]

    def has_edge(self,left,right):
        return bool(self.edge_path(left,right))

    def edge_path(self,left,right):
        """Equality of grounded keys is transitive; column names alone aren't."""
        if not self.has_ref(left) or not self.has_ref(right):return []
        if left==right:return [left]
        graph={}
        for edge in self.edges:
            a,b=edge['left'],edge['right']
            graph.setdefault(a,set()).add(b);graph.setdefault(b,set()).add(a)
        queue=deque([[left]]);seen=set()
        while queue:
            path=queue.popleft();node=path[-1]
            if node==right:return path
            if node in seen:continue
            seen.add(node)
            queue.extend(path+[n] for n in sorted(graph.get(node,set())-seen))
        return []

    def add_edge(self,left,right,source):
        if self.has_ref(left) and self.has_ref(right) and not any({e['left'],e['right']}=={left,right} for e in self.edges):
            self.edges.append({'left':left,'right':right,'source':source})

    def add_declared_relations(self):
        # Explicit domain relationships, not guessed joins on any equal name.
        self.add_edge('patients.subject_id','admissions.subject_id','declared_domain_relation')
        for t in ['diagnoses_icd','procedures_icd','labevents','microbiologyevents','prescriptions','transfers',
                  'icustays','services','hcpcsevents','poe','emar','pharmacy','drgcodes','chartevents',
                  'inputevents','outputevents','datetimeevents','procedureevents','ingredientevents','omr']:
            self.add_edge('patients.subject_id',t+'.subject_id','declared_patient_identity')
        for t in ['diagnoses_icd','procedures_icd','labevents','microbiologyevents','prescriptions',
                  'transfers','icustays','services','hcpcsevents','poe','emar','pharmacy','drgcodes']:
            self.add_edge('admissions.hadm_id',t+'.hadm_id','declared_domain_relation')
        for event,dictionary,code in [('diagnoses_icd','d_icd_diagnoses','icd_code'),('procedures_icd','d_icd_procedures','icd_code'),('labevents','d_labitems','itemid'),('hcpcsevents','d_hcpcs','hcpcs_cd')]:
            self.add_edge(event+'.'+code,dictionary+'.'+('code' if code=='hcpcs_cd' else code),'declared_dictionary_relation')
            if code=='icd_code':self.add_edge(event+'.icd_version',dictionary+'.icd_version','required_composite_key')
        for t in ['chartevents','inputevents','outputevents','datetimeevents','procedureevents','ingredientevents']:
            self.add_edge('icustays.stay_id',t+'.stay_id','declared_domain_relation')
            self.add_edge(t+'.itemid','d_items.itemid','declared_dictionary_relation')
        for key in ['emar_id','emar_seq']:self.add_edge('emar.'+key,'emar_detail.'+key,'required_composite_key')
        for key in ['poe_id','poe_seq']:self.add_edge('poe.'+key,'poe_detail.'+key,'required_composite_key')

    def join_closure(self, tables):
        selected=set(tables)&set(self.tables)
        graph={t:set() for t in self.tables}
        for e in self.edges:
            a,b=e['left'].split('.')[0],e['right'].split('.')[0]
            graph[a].add(b);graph[b].add(a)
        targets=sorted(selected)
        if targets:
            for target in targets[1:]:
                queue=deque([[targets[0]]]);seen=set()
                while queue:
                    path=queue.popleft();node=path[-1]
                    if node==target:selected.update(path);break
                    if node in seen:continue
                    seen.add(node)
                    queue.extend(path+[n] for n in sorted(graph[node]-seen))
        return sorted(selected)

    def payload(self,tables=None):
        names=sorted(self.tables if tables is None else set(tables)&set(self.tables))
        return {'dialect':self.dialect,'tables':{t:{'ddl':self.ddl[t],'description':self.descriptions.get(t,t)} for t in names},
                'relationships':[e for e in self.edges if e['left'].split('.')[0] in names and e['right'].split('.')[0] in names]}

    def inspect(self,sql,question=''):
        result={'valid':False,'errors':[],'warnings':[],'tables':[],'used_refs':[],'output_columns':[]}
        try:
            trees=[t for t in parse(sql,read=self.dialect) if t is not None]
            if len(trees)!=1 or not isinstance(trees[0],exp.Query):raise ValueError('Exactly one SELECT/CTE is required')
            tree=normalize_identifiers(trees[0],dialect=self.dialect)
            forbidden=(exp.Insert,exp.Update,exp.Delete,exp.Merge,exp.Create,exp.Drop,exp.Alter,exp.Into,exp.Lock)
            if any(tree.find(t) for t in forbidden):raise ValueError('Mutating/locking query denied')
            from ehrqa.sql_validator import DENIED_FUNCTIONS
            denied=DENIED_FUNCTIONS|{'load_extension','readfile','writefile','sqlite_readfile','sqlite_writefile'}
            for f in tree.find_all(exp.Func):
                name=(f.name if isinstance(f,exp.Anonymous) else f.sql_name()).lower()
                if name in denied:raise ValueError('Unsafe function: '+name)
            ctes={x.alias_or_name.lower() for x in tree.find_all(exp.CTE)}
            tables=set()
            for t in tree.find_all(exp.Table):
                if t.name.lower() in ctes:continue
                if self.dialect=='bigquery':
                    if t.name not in self.tables:raise ValueError('Unknown table: '+t.sql())
                elif t.catalog or t.db not in ('','public') or t.name not in self.tables:raise ValueError('Unknown/external table: '+t.sql())
                tables.add(t.name)
            if not tables:raise ValueError('SQL must read the database, not guess a literal answer')
            qualified=qualify(tree.copy(),dialect=self.dialect,schema=self.tables,expand_stars=False,
                infer_schema=False,validate_qualify_columns=True,quote_identifiers=False,identify=False,allow_partial_qualification=False)
            refs=set()
            for scope in traverse_scope(qualified):
                for c in scope.columns:
                    parent=scope
                    while parent is not None:
                        source=parent.sources.get(c.table)
                        if isinstance(source,exp.Table):
                            if self.has_ref(source.name+'.'+c.name):refs.add(source.name+'.'+c.name)
                            break
                        parent=parent.parent
            # Patient IDs are not allowed to leak in from a demonstration.
            qnums=set(re.findall(r'\b\d+\b',question))
            for pred in tree.find_all(exp.EQ):
                left,right=pred.this,pred.expression
                if isinstance(right,exp.Column):left,right=right,left
                if isinstance(left,exp.Column) and left.name=='subject_id' and isinstance(right,exp.Literal) and str(right.this).isdigit() and str(right.this) not in qnums:
                    raise ValueError('Introduced patient identifier absent from original question')
            for pred in tree.find_all(exp.In):
                if isinstance(pred.this,exp.Column) and pred.this.name=='subject_id':
                    for value in pred.expressions:
                        if isinstance(value,exp.Literal) and str(value.this).isdigit() and str(value.this) not in qnums:
                            raise ValueError('Introduced patient identifier in IN list')
            # Composite dictionary keys must be honored in every explicit JOIN.
            for a,b in [('diagnoses_icd','d_icd_diagnoses'),('procedures_icd','d_icd_procedures')]:
                if a in tables and b in tables and self.has_ref(a+'.icd_version') and self.has_ref(b+'.icd_version'):
                    from ehrqa.sql_validator import _missing_join_key
                    if _missing_join_key(tree,a,b,'icd_version'):raise ValueError('Missing composite icd_version JOIN')
            projections=[e.sql(dialect=self.dialect) for e in tree.expressions] if isinstance(tree,exp.Select) else []
            result.update(valid=True,tables=sorted(tables),used_refs=sorted(refs),output_columns=projections,
                ast_sql=tree.sql(dialect=self.dialect),has_distinct=bool(tree.find(exp.Distinct)),
                has_order=bool(tree.find(exp.Order)),has_limit=bool(tree.find(exp.Limit)))
        except Exception as e:result['errors'].append(str(e)[:500])
        return result
