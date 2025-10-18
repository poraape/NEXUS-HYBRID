from jinja2 import Template
HTML_TPL = """
<!doctype html><html lang="pt-br"><head><meta charset="utf-8"/>
<title>{{ title }}</title>
<style>body{font-family:Arial,sans-serif;padding:24px}table{border-collapse:collapse;width:100%}
th,td{border:1px solid #ddd;padding:6px;font-size:14px}th{background:#f0f0f0}</style>
</head><body>
<h1>{{ title }}</h1>
<h2>KPIs</h2>
<table><tr><th>Métrica</th><th>Valor</th></tr>
{% for k in kpis %}<tr><td>{{k.label}}</td><td>{{k.value}}</td></tr>{% endfor %}
</table>
<h2>Inconsistências</h2>
<table><tr><th>Campo</th><th>Código</th><th>Severidade</th><th>Descrição</th></tr>
{% for i in inconsistencies %}<tr><td>{{i.field}}</td><td>{{i.code}}</td><td>{{i.severity}}</td><td>{{i.message}}</td></tr>{% endfor %}
</table></body></html>
"""
def build_html(dataset: dict):
    tpl = Template(HTML_TPL)
    html = tpl.render(title=dataset.get("title","Relatório Fiscal"),
                      kpis=dataset.get("kpis",[]),
                      inconsistencies=dataset.get("compliance",{}).get("inconsistencies",[]))
    return html, "relatorio.html"
