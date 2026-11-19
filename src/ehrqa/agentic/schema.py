"""Profile-specific schema, relationship grounding and read-only SQL inspection."""
from collections import deque
from dataclasses import dataclass, field
import re

from sqlglot import exp, parse, parse_one
from sqlglot.optimizer.qualify import qualify
from sqlglot.optimizer.scope import Scope, traverse_scope
from sqlglot.optimizer.normalize_identifiers import normalize_identifiers


def _direct_column_origin(scope, column, seen=frozenset()):
    """Return the physical table occurrence and name of a direct column."""
    if not isinstance(column, exp.Column) or not column.table:
        return None
    source = scope.sources.get(column.table)
    if isinstance(source, exp.Table):
        return source, column.name
    if not isinstance(source, Scope) or source in seen:
        return None
    return _projection_origin(source, column.name, seen | {source})


def _projection_origin(source, name, seen, position=None):
    """Origin of output column ``name`` of a SELECT or of every branch of a set operation."""
    if isinstance(source.expression, exp.SetOperation):
        branches = list(source.set_operation_scopes)
        first = source.expression
        while isinstance(first, exp.SetOperation):
            first = first.this
        if not branches or not isinstance(first, exp.Select):
            return None
        names = [item.alias_or_name for item in first.selects]
        if position is None:
            if names.count(name) != 1:
                return None
            position = names.index(name)
        index = position
        origins = [_projection_origin(b, name, seen | {b}, position=index) for b in branches]
        if any(o is None for o in origins) or len({(o[0].name, o[1]) for o in origins}) != 1:
            return None
        return origins[0]
    if not isinstance(source.expression, exp.Select):
        return None
    selects = source.expression.selects
    if position is not None:
        if position >= len(selects):
            return None
        projections = [selects[position]]
    else:
        projections = [item for item in selects if item.alias_or_name == name]
    if len(projections) != 1:
        return None
    return _direct_column_origin(source, projections[0].unalias(), seen)


def _join_conjuncts(predicate):
    if isinstance(predicate, exp.Paren):
        yield from _join_conjuncts(predicate.this)
    elif isinstance(predicate, exp.And):
        yield from _join_conjuncts(predicate.this)
        yield from _join_conjuncts(predicate.expression)
    elif isinstance(predicate, exp.EQ):
        yield predicate


def _missing_join_key(scopes, event, dictionary, tables_by_scope):
    """Require the two keys within the same conjunctive JOIN and source pair."""
    keyed_tables = {event, dictionary}
    if not keyed_tables <= set().union(*tables_by_scope.values()):
        return False
    found = False
    for scope in scopes:
        if not isinstance(scope.expression, exp.Select):
            continue
        visible = set()
        from_ = scope.expression.args.get('from_')
        if from_:
            visible.add(from_.this.alias_or_name)
        source_tables = {
            alias: {source.name} if isinstance(source, exp.Table) else tables_by_scope[source]
            for alias, (_, source) in scope.selected_sources.items()
        }
        for join in scope.expression.args.get('joins', ()):
            incoming = join.this.alias_or_name
            right_tables = source_tables.get(incoming, set())
            left_tables = set().union(*(source_tables.get(alias, set()) for alias in visible))
            # Only the JOIN that first pairs the two tables needs the composite key;
            # a side that already holds both was paired (and checked) in its own scope.
            relevant = ((event in left_tables and dictionary in right_tables
                         and dictionary not in left_tables and event not in right_tables)
                        or (dictionary in left_tables and event in right_tables
                            and event not in left_tables and dictionary not in right_tables))
            if relevant:
                keys_by_pair = {}
                for eq in _join_conjuncts(join.args.get('on')):
                    left, right = eq.this, eq.expression
                    if not isinstance(left, exp.Column) or not isinstance(right, exp.Column):
                        continue
                    if left.table == incoming:
                        left, right = right, left
                    if right.table != incoming or left.table not in visible:
                        continue
                    a, b = _direct_column_origin(scope, left), _direct_column_origin(scope, right)
                    if (a and b and {a[0].name, b[0].name} == keyed_tables and a[1] == b[1]):
                        pair = (left.table, right.table, id(a[0]), id(b[0]))
                        keys_by_pair.setdefault(pair, set()).add(a[1])
                if not any({'icd_code', 'icd_version'} <= keys for keys in keys_by_pair.values()):
                    return True
                found = True
            visible.add(incoming)
    # No explicit JOIN pairs the two tables (e.g. EXISTS / IN subqueries): the
    # JOIN rule does not apply; correlated predicates are checked separately.
    return False


def _missing_correlated_version(tree):
    """An AND-group equating two icd_code columns must also equate icd_version."""
    for where in tree.find_all(exp.Where):
        eqs = list(_join_conjuncts(where.this))
        pairs = {frozenset((e.this.sql(), e.expression.sql())): (e.this.name, e.expression.name)
                 for e in eqs if isinstance(e.this, exp.Column) and isinstance(e.expression, exp.Column)
                 and e.this.table and e.expression.table and e.this.table != e.expression.table}
        codes = [k for k, names in pairs.items() if names == ('icd_code', 'icd_code')]
        versions = [k for k, names in pairs.items() if names == ('icd_version', 'icd_version')]
        for code in codes:
            tables = {ref.split('.')[0] for ref in code}
            if not any({ref.split('.')[0] for ref in v} == tables for v in versions):
                return True
    return False


def _literal_value(node):
    while isinstance(node, exp.Paren):
        node = node.this
    if isinstance(node, exp.Boolean):
        return ('bool', bool(node.this))
    if isinstance(node, exp.Literal):
        return ('str', node.this) if node.is_string else ('num', float(node.this))
    return None


def _constant_false(node):
    """True when a filter can never hold, independent of the data."""
    while isinstance(node, exp.Paren):
        node = node.this
    if isinstance(node, exp.Boolean):
        return node.this is False or str(node.this).lower() == 'false'
    if isinstance(node, exp.And):
        return _constant_false(node.this) or _constant_false(node.expression)
    if isinstance(node, exp.Or):
        return _constant_false(node.this) and _constant_false(node.expression)
    if isinstance(node, exp.Not):
        inner = node.this
        while isinstance(inner, exp.Paren):
            inner = inner.this
        return isinstance(inner, exp.Boolean) and str(inner.this).lower() == 'true'
    if isinstance(node, (exp.EQ, exp.NEQ)):
        left, right = _literal_value(node.this), _literal_value(node.expression)
        if left is None or right is None:
            return False
        return (left == right) is isinstance(node, exp.NEQ)
    return False


def _scope_tables(scopes):
    tables_by_scope = {}
    for scope in scopes:
        tables = {source.name for _, source in scope.selected_sources.values()
                  if isinstance(source, exp.Table)}
        dependencies = [source for _, source in scope.selected_sources.values()
                        if isinstance(source, Scope)]
        tables_by_scope[scope] = tables.union(
            *(tables_by_scope[child] for child in (*dependencies, *scope.set_operation_scopes)))
    return tables_by_scope

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
    def from_records(cls, records, dialect='bigquery'):
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

    def canonical_table(self, name):
        """Schema spelling of a table name, or None (exact match; see BirdSchema)."""
        return name if name in self.tables else None

    def canonical_ref(self, ref):
        return ref

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
            from ehrqa.text2sql.security import DENIED_FUNCTIONS
            denied=DENIED_FUNCTIONS
            for f in tree.find_all(exp.Func):
                name=(f.name if isinstance(f,exp.Anonymous) else f.sql_name()).lower()
                if name in denied:raise ValueError('Unsafe function: '+name)
            ctes={x.alias_or_name.lower() for x in tree.find_all(exp.CTE)}
            tables=set()
            for t in tree.find_all(exp.Table):
                if t.name.lower() in ctes:continue
                if self.dialect=='bigquery':
                    if t.name not in self.tables:raise ValueError('Unknown table: '+t.sql())
                elif t.catalog or t.db not in ('','public') or self.canonical_table(t.name) is None:raise ValueError('Unknown/external table: '+t.sql())
                tables.add(self.canonical_table(t.name) or t.name)
            if not tables:raise ValueError('SQL must read the database, not guess a literal answer')
            qualified=qualify(tree.copy(),dialect=self.dialect,schema=self.tables,expand_stars=True,
                infer_schema=False,validate_qualify_columns=True,quote_identifiers=False,identify=False,allow_partial_qualification=False)
            refs=set()
            scopes = traverse_scope(qualified)
            for scope in scopes:
                for c in scope.columns:
                    parent=scope
                    while parent is not None:
                        source=parent.sources.get(c.table)
                        if isinstance(source,exp.Table):
                            if self.has_ref(source.name+'.'+c.name):refs.add(self.canonical_ref(source.name+'.'+c.name))
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
            tables_by_scope = _scope_tables(scopes)
            for a,b in [('diagnoses_icd','d_icd_diagnoses'),('procedures_icd','d_icd_procedures')]:
                if self.has_ref(a+'.icd_version') and self.has_ref(b+'.icd_version'):
                    if _missing_join_key(scopes,a,b,tables_by_scope) or _missing_correlated_version(tree):raise ValueError('Missing composite icd_version JOIN')
            # A placeholder filter (WHERE FALSE, 1=0) silently empties a cohort.
            # Unreferenced CTEs cannot change the result and are ignored.
            referenced={t.name.lower() for t in tree.find_all(exp.Table)}
            def used(node):
                cte=node.find_ancestor(exp.CTE)
                return cte is None or cte.alias_or_name.lower() in referenced
            for clause in (*tree.find_all(exp.Where), *tree.find_all(exp.Having)):
                if used(clause) and _constant_false(clause.this):raise ValueError('Constant-false filter: '+clause.this.sql(dialect=self.dialect))
            for join in tree.find_all(exp.Join):
                on=join.args.get('on')
                if on is not None and used(join) and _constant_false(on):raise ValueError('Constant-false filter: '+on.sql(dialect=self.dialect))
            projections=[e.sql(dialect=self.dialect) for e in tree.expressions] if isinstance(tree,exp.Select) else []
            result.update(valid=True,tables=sorted(tables),used_refs=sorted(refs),output_columns=projections,
                ast_sql=tree.sql(dialect=self.dialect),has_distinct=bool(tree.find(exp.Distinct)),
                has_order=bool(tree.find(exp.Order)),has_limit=bool(tree.find(exp.Limit)))
        except Exception as e:result['errors'].append(self._with_closest_names(str(e))[:500])
        return result

    def _with_closest_names(self,message):
        """Append the closest real schema names to an unknown-name error (metadata only)."""
        import difflib
        table=re.search(r'Unknown table: `?([^`\s]+)`?',message)
        column=(re.search(r"[Cc]olumn '?\"?([A-Za-z_][\w]*)'?\"? could not be resolved",message)
                or re.search(r'Unknown column: `?"?([A-Za-z_][\w]*)',message))
        if table:
            name=table.group(1).split('.')[-1].strip('"`')
            close=difflib.get_close_matches(name,list(self.tables),n=3,cutoff=0.5)
        elif column:
            name=column.group(1)
            names=sorted({c for cols in self.tables.values() for c in cols})
            close=difflib.get_close_matches(name,names,n=3,cutoff=0.6)
            close=[f'{t}.{c}' for c in close for t,cols in self.tables.items() if c in cols][:6]
        else:
            return message
        return message+(' Closest schema names: '+', '.join(close) if close else '')
