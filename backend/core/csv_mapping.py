"""Saved CSV header mappings shared by configuration and ingestion."""
import csv
import io
REQUIRED={'sales':['VIN'],'service':['CustomerID','VIN'],'finance':['FinanceNumber','CustomerID','VIN','LenderName'],'marketing':['LeadID','VIN'],'parts':['PartNumber']}
NONEMPTY={'sales':['VIN'],'service':[],'finance':['FinanceNumber'],'marketing':['LeadID'],'parts':['PartNumber']}
def validate_mapping(mapping):
 if len(mapping)>100:raise ValueError('Use at most 100 mapped columns')
 if any(not k.strip() or not v.strip() or k!=k.strip() or v!=v.strip() or len(k)>100 or len(v)>100 for k,v in mapping.items()):raise ValueError('Column names must be non-empty, trimmed and at most 100 characters')
 if len(set(mapping.values()))!=len(mapping):raise ValueError('Each destination column must be unique')
def mapped_csv(file_bytes,department,mapping):
 validate_mapping(mapping)
 reader=csv.DictReader(io.StringIO(file_bytes.decode('utf-8-sig')))
 fields=reader.fieldnames or []
 if not fields or len(set(fields))!=len(fields):raise ValueError('CSV headers must be present and unique')
 missing=set(mapping)-set(fields)
 if missing:raise ValueError('Mapped source columns are missing: '+', '.join(sorted(missing)))
 targets=[mapping.get(f,f) for f in fields]
 if len(set(targets))!=len(targets):raise ValueError('Mapping collides with an existing destination column')
 missing=set(REQUIRED[department])-set(targets)
 if missing:raise ValueError('Required columns are missing: '+', '.join(sorted(missing)))
 output=io.StringIO(newline='');writer=csv.DictWriter(output,fieldnames=targets);writer.writeheader()
 count=0
 for number,row in enumerate(reader,2):
  if None in row or any(v is None for v in row.values()):raise ValueError(f'Row {number} has a different number of columns')
  mapped={mapping.get(k,k):v for k,v in row.items()}
  if any(not mapped[k].strip() for k in NONEMPTY[department]):raise ValueError(f'Row {number} is missing a required value')
  writer.writerow(mapped);count+=1
 if not count:raise ValueError('CSV contains no data rows')
 return output.getvalue().encode('utf-8')
