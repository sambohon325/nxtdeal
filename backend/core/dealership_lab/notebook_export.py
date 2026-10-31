"""Self-contained, escaped review copies of exact saved notebook revisions."""
from html import escape
from fastapi import HTTPException
from . import service as lab, notebooks


def render(value):
    if isinstance(value,dict):
        return '<dl>'+''.join('<dt>'+escape(k.replace('_',' ').title())+'</dt><dd>'+render(v)+'</dd>' for k,v in value.items())+'</dl>'
    if isinstance(value,list):
        return '<ol>'+''.join('<li>'+render(v)+'</li>' for v in value)+'</ol>' if value else '<p>None recorded</p>'
    if value is None:return 'Unknown / unavailable'
    if value == '':return 'Not recorded'
    return escape(str(value))


def table(headers, rows, caption):
    return '<div class="table-wrap"><table><caption>'+escape(caption)+'</caption><thead><tr>'+''.join(
        '<th scope="col">'+escape(h)+'</th>' for h in headers)+'</tr></thead><tbody>'+''.join(
        '<tr>'+''.join('<td>'+render(v)+'</td>' for v in row)+'</tr>' for row in rows)+'</tbody></table></div>'


def amount(value):
    # Display rounding only. The complete saved record below retains precision.
    return f'{value:,.2f}' if type(value) in (int,float) else value


def review_copy(book):
    """Readable chapters derived only from this exact saved revision."""
    measures=book.get('measures',[])
    currency=book.get('currency','Unknown currency')
    def label(row):
        unit=currency if row.get('unit')=='currency' else row.get('unit','')
        return str(row.get('label',row.get('key','Measure'))) + (f' ({unit})' if unit else '')
    parts=['<section><h2>Decision & follow-through</h2>',render({
        'question':book.get('question'), 'objective':book.get('objective'),
        'action':book.get('action'), 'responsible':book.get('responsible'),
        'due':book.get('due'), 'notes':book.get('notes')}),'</section>',
        '<section><h2>Frozen model comparison</h2><p>'+render(book.get('evidence_note'))+'</p>',
        table(['Measure','Starting plan','Proposed plan','Your target'],
              [[label(m),amount(m.get('baseline')),amount(m.get('proposed')),amount(m.get('target'))] for m in measures],
              f"Saved expectations across {book.get('months','unknown')} months; targets are separate user entries"),
        '<h3>Reported figures & sources</h3>',
        table(['Measure','Manual baseline','Reported follow-up','Source / period'],
              [[label(m),amount(m.get('manual')),amount(m.get('followup')),m.get('source')] for m in measures],
              'User-reported values; not independently verified'),
        '<h3>Measure definitions</h3>',render({m.get('label',m.get('key','Measure')):m.get('definition') for m in measures}),'</section>']
    if book.get('kind')=='procedure':
        parts+=['<section><h2>Procedure & review responsibilities</h2>',render({
            'steps':book.get('steps'),'exceptions':book.get('exceptions'),
            'reviewer':book.get('reviewer'),'review_due':book.get('review_due'),
            'saved_location':{k:book.get('location',{}).get(k) for k in ('country','region','city')}}),
            '<h3>Review checklist</h3>',table(['Review item','Status','Evidence / reference'],
                [[c.get('title'),c.get('status'),dict(evidence=c.get('evidence'),reference=c.get('source'))]
                 for c in book.get('controls',[])], 'Saved review states; not compliance certification'),'</section>']
    parts+=['<section><h2>Budget allowances</h2><p>Separate planning entries, not additions to modeled costs. Hours and rates are not automatically booked as cash expense.</p>',
            render(dict(allowances=book.get('costs'),notes=book.get('cost_notes'))),'</section>',
            '<section><h2>Checkpoint action plan</h2>',
            table(['Checkpoint','Action & target','Reported outcome & evidence','Status'],
                [[f"Day {c.get('days','unknown')}",dict(action=c.get('action'),target=c.get('target')),
                  dict(actual=c.get('actual'),evidence=c.get('evidence')),c.get('status')]
                 for c in book.get('checkpoints',[])], 'Original saved day labels are retained, including legacy schedules'),'</section>',
            '<section><h2>Modeled checkpoint outlook</h2>']
    for projection in book.get('projections',[]):
        parts+=['<h3>Day '+escape(str(projection.get('days','unknown')))+'</h3>']
        if not projection.get('available'):
            parts+=['<p>Unavailable: this saved comparison does not provide this checkpoint. No extrapolation has been added.</p>']
        else:
            parts+=[table(['Measure','Starting plan','Proposed plan','Difference'],
                [[label(m),amount(m.get('baseline')),amount(m.get('proposed')),amount(m.get('delta'))]
                 for m in projection.get('measures',[])], 'Model expectations at this saved checkpoint')]
    parts+=['</section><section><h2>Evidence provenance</h2>',render({k:book.get(k) for k in
        ('run_id','run_created','workspace_id','engine_commit','currency','months','edition','revision','status')}),
        '<p>The appendix retains every saved field at full precision. This copy does not use current model defaults or refresh historical results.</p></section>']
    return ''.join(parts)


def document(key, actor, revision):
    with lab.LOCK:
        current=notebooks.get(key,actor)
        if revision==current.attributes['revision']:
            book=lab.serial(current)
        else:
            saved=next((v for v in lab.items(notebooks.HISTORY) if v.attributes['owner']==actor and v.attributes['notebook_id']==key and v.attributes['revision']==revision),None)
            if not saved:raise HTTPException(404,'Saved notebook revision not found')
            book=lab.serial(saved)
    book['id']=key
    book.pop('notebook_id',None)
    title=escape(book['title'])
    identity=f"{escape(key)} · edition {book['edition']} · revision {book['revision']} · {escape(book['status'])}"
    # Render every persisted field, including manual values, source periods and
    # legacy checkpoint migrations. No current-model reconstruction or scripts.
    html='''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'">
<title>'''+title+'''</title><style>body{font:15px/1.55 system-ui,sans-serif;color:#172b3a;max-width:850px;margin:36px auto;padding:0 24px}h1{line-height:1.2}h2{border-top:2px solid #247c8c;padding-top:16px;margin-top:32px}table{width:100%;border-collapse:collapse;font-size:13px;table-layout:fixed}caption{text-align:left;font-weight:600;padding:8px 0}th,td{padding:8px;border:1px solid #ccd6dd;text-align:left;vertical-align:top;overflow-wrap:anywhere;white-space:pre-wrap}th{background:#eef5f8}thead{display:table-header-group}.table-wrap{overflow-x:auto}td dl{display:block}td dt{margin-top:6px}section{margin-bottom:28px}dt{font-weight:650;overflow-wrap:anywhere}dd{margin:0;min-width:0;white-space:pre-wrap;overflow-wrap:anywhere}li{padding:8px 0;border-bottom:1px solid #ccd6dd}dl{margin:0;display:grid;grid-template-columns:minmax(110px,25%) minmax(0,1fr);gap:8px 16px}dd>dl,dd>ol{margin-top:0}ol{padding-left:20px}dd>ol{margin-bottom:0}@media(max-width:560px){body{margin:20px auto;padding:0 16px}dl{display:block}dt{margin-top:12px}dd{margin-left:8px}h1{font-size:26px}}p{overflow-wrap:anywhere}.note{padding:16px;background:#eef5f8}@media print{body{font-size:10pt;margin:0;padding:0}h1,h2,dt{break-after:avoid}dl{display:block}dt{margin-top:6px}dd{margin-left:12px}li{break-inside:auto}thead{display:table-header-group}tr{break-inside:avoid}table{font-size:9pt}.table-wrap{overflow:visible}.appendix{break-before:page}@page{margin:18mm}}</style><body><h1>'''+title+'</h1><p>'+identity+'''</p><p class="note">Saved review copy. Use your browser's Print command to print or save as PDF. Model expectations are not reported actuals. Unknown values remain unknown; zero is a recorded value. Budget allowances are separate from model projections. Procedure locks record personal review, not operational approval or legal certification. Historical checkpoints retain their original day labels.</p>'''+review_copy(book)+'<section class="appendix"><h2>Complete saved record</h2>'+render(book)+'</section>'+'</body></html>'
    return dict(filename=f'nxtdeal-notebook-{key}-e{book["edition"]}-r{revision}.html',html=html,revision=revision,edition=book['edition'])
