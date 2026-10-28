"""Evidence-bound equality scopes for freshness instances; no implicit selector coercion."""
from __future__ import annotations
import hashlib,json,re
from collections import defaultdict

def identity(scope):
    key={k:scope[k] for k in ('field','equals')}
    return 'R09_'+hashlib.sha256(json.dumps(key,sort_keys=True,ensure_ascii=False).encode()).hexdigest()[:12]

def parse_scope(quote,cid):
    match=re.search(r'^\s*(?:(?:[A-Za-z]\d+|\d+)[.、]\s*|[-*]\s+)?(?:仅对|适用于|For)\s+([A-Za-z][A-Za-z0-9_]*)\s*=\s*"([^"\n]+)"',quote,re.I)
    return {'field':match[1],'equals':match[2],'requirement_id':cid} if match else None

def enum_values(dictionary,field):
    value=dictionary.get(field,{}).get('enum_values',[])
    if isinstance(value,str):
        try:value=json.loads(value)
        except ValueError:return []
    return value if isinstance(value,list) else []

def validate_scopes(rules,requirements,header,dictionary):
    """Returns structured config rejections. Unscoped legacy kernel inputs retain their contract."""
    byid={q['requirement_id']:q for q in requirements};problems=[];groups=defaultdict(list)
    for rule in rules:
        if rule.get('rule_type')!='freshness':
            if 'scope' in rule:problems.append({'code':'INPUT_SCHEMA_INVALID','target':rule.get('rule_id'),'detail':'Only freshness supports a record scope in v0.6'})
            continue
        groups['freshness'].append(rule);scope=rule.get('scope');refs=rule.get('requirement_ids') or []
        conditional=[parse_scope(byid[c]['source_quote'],c) for c in refs if c in byid]
        conditional=[c for c in conditional if c]
        error=None
        selector_signal=any(re.search(r'[A-Za-z][A-Za-z0-9_]*\s*=\s*"',byid[c]['source_quote']) for c in refs if c in byid)
        if selector_signal and not conditional:error='Unrecognized or negated source selector is not executable'
        elif not scope:
            if conditional:error='Conditional freshness clause requires its explicit scope'
        elif not isinstance(scope,dict) or set(scope)!={'field','equals','requirement_id'}:error='Scope needs exactly field, equals, requirement_id'
        elif any(not isinstance(v,str) or not v for v in scope.values()):error='Scope values must be nonempty strings'
        elif scope['requirement_id'] not in refs:error='Scope is not bound to this rule clause'
        elif scope not in conditional:error='Scope lacks an exact positive source marker: 仅对 field="value" / For field="value"'
        elif scope['field'] not in header or scope['field'] not in dictionary:error='Scope field must exist in the header and dictionary'
        elif dictionary[scope['field']].get('data_type')!='string':error='Scope field must have string type'
        elif scope['equals'] not in enum_values(dictionary,scope['field']):error='Scope value must be a declared dictionary enum'
        if error:problems.append({'code':'INPUT_SCHEMA_INVALID','target':rule.get('rule_id'),'detail':error})
    group=groups['freshness']
    if len(group)>1 and any(r.get('scope') for r in group):
        scopes=[r.get('scope') for r in group]
        valid=all(isinstance(s,dict) and set(s)=={'field','equals','requirement_id'} and all(isinstance(v,str) for v in s.values()) for s in scopes)
        if not valid or len({s['field'] for s in scopes})!=1 or len({s['equals'] for s in scopes})!=len(scopes):
            problems.append({'code':'INPUT_SCHEMA_INVALID','target':'approved-rules.yaml','detail':'Freshness instances require disjoint enum values of the same scope field; mixed global/scoped rules or overlap are not inferred'})
    return problems

def population(rule,header,rows,dictionary):
    scope=rule.get('scope')
    if not scope:return {line for line,_ in rows},set(),set()
    field=scope['field'];index=header.index(field);allowed=enum_values(dictionary,field)
    eligible=set();unknown=set();excluded=set()
    for line,row in rows:
        value=row[index] if index<len(row) else None
        if value not in allowed:eligible.add(line);unknown.add(line)
        elif value==scope['equals']:eligible.add(line)
        else:excluded.add(line)
    return eligible,unknown,excluded
