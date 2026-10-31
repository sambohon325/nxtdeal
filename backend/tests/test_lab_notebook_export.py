from copy import deepcopy
from core.dealership_lab.notebook_export import review_copy


def test_review_chapters_keep_reported_figures_distinct_and_unknowns_visible():
    book=dict(kind='workbook',months=2,currency='CAD',question='Test a cost',
        measures=[dict(label='Cash',unit='currency',baseline=0,proposed=None,target=100,
                       manual=None,followup=0,source='Synthetic September',definition='Monthly change')],
        checkpoints=[dict(days=365,action='Annual review',actual='Recorded annual outcome')],
        projections=[dict(days=120,available=False,measures=[])])
    before=deepcopy(book)
    html=review_copy(book)
    assert book==before
    assert 'Cash (CAD)' in html and '<td>0.00</td>' in html
    assert 'Unknown / unavailable' in html
    assert 'Reported figures & sources' in html
    assert 'User-reported values; not independently verified' in html
    assert 'Day 365' in html and 'Day 120' in html
    assert 'No extrapolation has been added' in html
    assert 'Synthetic September' in html
    assert 'Budget allowances' in html
    assert 'Procedure & review responsibilities' not in html


def test_procedure_chapters_escape_all_saved_text_and_do_not_link_untrusted_urls():
    book=dict(kind='procedure',steps='<img src=x onerror=bad()>',exceptions='<script>bad()</script>',
        controls=[dict(title='Untrusted <b>title</b>',status='open',evidence='Evidence',
                       source={'url':'javascript:bad()','title':'Untrusted source'})])
    html=review_copy(book)
    assert '<img' not in html and '<script' not in html and '<b>' not in html
    assert '&lt;img' in html and '&lt;script&gt;' in html
    assert 'href=' not in html and 'javascript:bad()' in html
    assert 'Saved review states; not compliance certification' in html
