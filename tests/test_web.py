from html.parser import HTMLParser
from pathlib import Path
import re
class Page(HTMLParser):
    def __init__(self):super().__init__();self.ids=[];self.labels=[];self.assets=[]
    def handle_starttag(self,tag,attrs):
        a=dict(attrs)
        if 'id' in a:self.ids.append(a['id'])
        if tag=='label' and 'for' in a:self.labels.append(a['for'])
        if tag=='script' and 'src' in a:self.assets.append(a['src'])
        if tag=='link' and a.get('rel')=='stylesheet':self.assets.append(a['href'])
def test_static_ui_contract():
    root=Path(__file__).resolve().parent.parent;page=Page();page.feed((root/'web/index.html').read_text());js=(root/'web/app.js').read_text()
    assert len(page.ids)==len(set(page.ids))
    assert set(page.labels).issubset(page.ids)
    # Some controls are deliberately created only when a station/dialog opens.
    generated={'scenarioChoice','actionNote','outcomeNote','outcomeChoice','obsTime','obsNote'}
    assert set(re.findall(r"\$\('([^']+)'\)",js)).issubset(set(page.ids)|generated)
    assert 'innerHTML' not in js
    for path in page.assets:assert (root/'web'/path.removeprefix('/assets/')).is_file()
