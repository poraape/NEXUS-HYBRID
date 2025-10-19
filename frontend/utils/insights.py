from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional

import pandas as pd
import streamlit as st


def _to_float(value: Any) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):  # pragma: no cover - defensive
        return 0.0


def _format_currency(value: float) -> str:
    return f"R$ {value:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def show_incremental_insights(results: Iterable[Dict[str, Any]]) -> None:
    results_list: List[Dict[str, Any]] = list(results)
    if not results_list:
        st.info("Nenhum resultado incremental disponível até o momento.")
        return

    rows = []
    for index, result in enumerate(results_list, start=1):
        totals = result.get("totals") or {}
        rows.append(
            {
                "Arquivo": result.get("source") or f"Upload {index}",
                "Total NF": _to_float(totals.get("vNF")),
                "Produtos": _to_float(totals.get("vProd")),
                "ICMS": _to_float(totals.get("vICMS")),
            }
        )

    df = pd.DataFrame(rows)

    st.subheader("📊 Insights Individuais e Comparativos")

    display_df = df.copy()
    for column in ("Total NF", "Produtos", "ICMS"):
        display_df[column] = display_df[column].map(_format_currency)
    st.dataframe(display_df, use_container_width=True)

    if len(df) > 1:
        numeric = df.drop(columns=["Arquivo"]).apply(pd.to_numeric, errors="coerce").fillna(0.0)
        diff = numeric.diff().fillna(0.0)
        diff.insert(0, "Arquivo", df["Arquivo"])

        diff_display = diff.copy()
        for column in ("Total NF", "Produtos", "ICMS"):
            diff_display[column] = diff_display[column].map(_format_currency)

        st.markdown("#### Diferenças entre uploads consecutivos")
        st.dataframe(diff_display, use_container_width=True)

        maior = df.loc[df["Total NF"].idxmax()]
        menor = df.loc[df["Total NF"].idxmin()]
        st.markdown(f"📈 **Maior valor:** {maior['Arquivo']} ({_format_currency(maior['Total NF'])})")
        st.markdown(f"📉 **Menor valor:** {menor['Arquivo']} ({_format_currency(menor['Total NF'])})")


def render_discrepancies_panel(compare_result: Optional[Dict[str, Any]]) -> None:
    """Render a panel with inter-document discrepancies."""
    st.subheader("🧭 Painel de Discrepâncias Interdocumentais")

    if not compare_result:
        st.info("Nenhum resultado de comparação disponível ainda.")
        return

    discrepancies = compare_result.get("discrepancies") or []
    insights = compare_result.get("insights") or []
    summary = compare_result.get("summary") or {}

    with st.expander("Resumo (contagens por CFOP, NCM, CST)", expanded=True):
        st.json(summary)

    if insights:
        st.markdown("**Insights automáticos**:")
        for tip in insights:
            st.markdown(f"- {tip}")

    if discrepancies:
        st.markdown("**Discrepâncias detectadas (A vs B):**")
        for item in discrepancies[:200]:
            a_src = item.get("a_source") or "Documento A"
            b_src = item.get("b_source") or "Documento B"
            st.markdown(f"- **{a_src}** ↔ **{b_src}**")
            st.json(item.get("diffs") or {})
    else:
        st.success("Sem discrepâncias materiais entre os documentos processados.")
