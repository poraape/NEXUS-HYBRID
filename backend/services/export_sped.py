from io import BytesIO

def build_sped_efd(dataset: dict):
    lines = ["# SPED/EFD PROTÓTIPO (não-oficial)", f"# TITLE={dataset.get('title','Relatorio')}"]
    for k in dataset.get("kpis", []):
        lines.append(f"|KPI|{k.get('label')}|{k.get('value')}|")
    for i in dataset.get("compliance",{}).get("inconsistencies",[]):
        lines.append(f"|INC|{i.get('severity')}|{i.get('field')}|{i.get('code')}|{i.get('message')}|")
    content = "\n".join(lines).encode("utf-8")
    return content, "sped_efd_prototipo.txt"
