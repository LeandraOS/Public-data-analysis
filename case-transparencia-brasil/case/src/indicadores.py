"""
indicadores.py — Etapa 5: indicadores calculáveis de forma recorrente.

Critérios de projeto de cada indicador:

1. Robustez — a fórmula não pode ser dominada por um registro errado. Todos
   usam mediana/quantis em vez de média, e todos são calculados sobre o
   escopo comparável definido em `preparacao.marcar_e_definir_escopo`.
2. Comparabilidade — o denominador é sempre um benchmark do MESMO item, no
   MESMO período. Preço de medicamento não é comparável entre moléculas nem
   entre anos.
3. Estabilidade sob coleta incremental — o indicador de um período fechado
   não deve mudar quando o período seguinte chega. Onde isso não é possível
   (a fonte retifica registros retroativamente), o indicador é versionado
   pela data de extração.
4. Acionabilidade — cada indicador aponta um ente, um item ou um mercado
   específico, não apenas um agregado nacional.

A escolha da MEDIANA como preço de referência não é arbitrária: é o
parâmetro previsto na regulamentação de pesquisa de preços da administração
federal (IN SEGES/ME nº 65/2021, art. 6º, que admite média, mediana ou menor
preço dos parâmetros pesquisados, justificando a mediana quando há valores
discrepantes). Isso torna o indicador legível pelo próprio gestor público.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


# ==========================================================================
# IND-01 — Índice de Preço Relativo (IPR)
# ==========================================================================


def ind01_indice_preco_relativo(dfp: pd.DataFrame, janela: str = "anoCompra") -> pd.DataFrame:
    """Razão entre o preço pago e o preço mediano nacional do mesmo item-período.

    Nome         : Índice de Preço Relativo (IPR)
    Objetivo     : medir, de forma comparável entre medicamentos e entre
                   períodos, se um ente comprou acima ou abaixo do preço
                   praticado no país para o mesmo produto.
    Fórmula      : IPR(i) = preco_unitario(i) / mediana{preco_unitario | mesmo
                   codigoItemCatalogo, mesma unidade de fornecimento,
                   mesmo período}
                   IPR agregado do ente = mediana dos IPR de seus itens.
    Variáveis    : precoUnitario, codigoItemCatalogo, nomeUnidadeFornecimento,
                   dataCompra, codigoUasg
    Granularidade: item (nativa); agregável a UASG, órgão, município, UF, esfera
    Periodicidade: mensal já é viável; trimestral é o recomendado, porque o
                   n mensal por medicamento é pequeno e a mediana ficaria
                   instável.
    Leitura      : IPR = 1,00 é o preço típico; 1,30 significa 30% acima.
    Limitações   : (a) o benchmark é endógeno — se todo o mercado paga caro, o
                   IPR não detecta; (b) não controla quantidade, e compras
                   pequenas são legitimamente mais caras (ver IND-02);
                   (c) exige n mínimo no grupo de referência.
    """
    d = dfp.copy()
    grupo = ["codigoItemCatalogo", "nomeUnidadeFornecimento", janela]
    d["preco_referencia"] = d.groupby(grupo, observed=True)["precoUnitario"].transform("median")
    d["n_referencia"] = d.groupby(grupo, observed=True)["precoUnitario"].transform("size")
    d["IPR"] = d["precoUnitario"] / d["preco_referencia"]
    d.loc[d["n_referencia"] < 10, "IPR"] = np.nan  # n mínimo para benchmark estável
    return d


def ind01_agregado(d_ipr: pd.DataFrame, por=("nomeUasg", "estado"), n_min=5) -> pd.DataFrame:
    return (d_ipr.dropna(subset=["IPR"])
            .groupby(list(por), observed=True)
            .agg(n_itens=("IPR", "size"), IPR_mediano=("IPR", "median"),
                 IPR_p75=("IPR", lambda s: s.quantile(0.75)),
                 valor_total=("valorTotalItem", "sum"))
            .query(f"n_itens >= {n_min}")
            .sort_values("IPR_mediano", ascending=False)
            .round(3))


# ==========================================================================
# IND-02 — Índice de Preço Ajustado por Escala (IPAE)
# ==========================================================================


def ind02_indice_ajustado_escala(dfp: pd.DataFrame, elasticidade: float) -> pd.DataFrame:
    """IPR corrigido pelo efeito legítimo do volume sobre o preço.

    Nome         : Índice de Preço Ajustado por Escala (IPAE)
    Objetivo     : separar sobrepreço de efeito de escala. Um município que
                   compra 500 comprimidos paga mais que um estado que compra
                   5 milhões — e isso não é má gestão. O IPAE compara o ente
                   com o preço esperado para uma compra do MESMO tamanho.
    Fórmula      : preco_esperado(i) = mediana_item_periodo x (q(i)/q_mediana)^β
                   IPAE(i) = preco_unitario(i) / preco_esperado(i)
                   onde β é a elasticidade preço-quantidade estimada na Etapa 4.
    Variáveis    : precoUnitario, quantidade, codigoItemCatalogo, dataCompra
                   + β (parâmetro estimado, versionado junto ao indicador)
    Granularidade: item; agregável a ente, município, UF
    Periodicidade: trimestral, com β reestimado anualmente
    Limitações   : (a) β é uma associação, não um efeito causal — o ajuste
                   remove o gradiente observado, não o "efeito escala
                   verdadeiro"; (b) β é estimado da própria base, o que gera
                   dependência circular (mitigável estimando β em janela
                   anterior à de aplicação); (c) forma funcional imposta
                   (potência); (d) não captura diferenças de qualidade,
                   prazo de entrega ou logística regional.
    """
    d = dfp.copy()
    grupo = ["codigoItemCatalogo", "nomeUnidadeFornecimento", "anoCompra"]
    ref_preco = d.groupby(grupo, observed=True)["precoUnitario"].transform("median")
    ref_qtd = d.groupby(grupo, observed=True)["quantidade"].transform("median")
    d["preco_esperado"] = ref_preco * (d["quantidade"] / ref_qtd) ** elasticidade
    d["IPAE"] = d["precoUnitario"] / d["preco_esperado"]
    d["excesso_ajustado_R$"] = ((d["precoUnitario"] - d["preco_esperado"])
                                .clip(lower=0) * d["quantidade"])
    return d


# ==========================================================================
# IND-03 — Taxa de Contratação por Dispensa (TCD)
# ==========================================================================


def ind03_taxa_dispensa(df: pd.DataFrame, n_min=3) -> pd.DataFrame:
    """Participação da dispensa de licitação nas aquisições de medicamentos do ente.

    Nome         : Taxa de Contratação por Dispensa (TCD)
    Objetivo     : monitorar o uso da exceção legal à licitação. A dispensa é
                   prevista para baixo valor e urgência (Lei 14.133/2021,
                   art. 75); uso recorrente para medicamentos de uso contínuo
                   e demanda previsível sinaliza falha de planejamento — e,
                   por P3, está associado a preço maior.
    Fórmula      : TCD_itens  = itens com modalidade = dispensa / total de itens
                   TCD_valor  = valor por dispensa / valor total
                   (as duas versões são reportadas juntas: divergência grande
                   entre elas indica dispensas concentradas em poucos itens
                   de alto valor, o que é mais grave)
    Variáveis    : modalidade, valorTotalItem, codigoUasg, dataCompra
    Granularidade: UASG / órgão / município / UF / esfera
    Periodicidade: mensal ou trimestral (indicador de contagem, estável)
    Limitações   : (a) o código de modalidade não está documentado no
                   dicionário fornecido e a decodificação é inferida — deve
                   ser confirmada na tabela de domínio da API antes de
                   publicação; (b) parte das dispensas é legítima e o
                   indicador não distingue o fundamento legal invocado
                   (art. 75, I a XVIII); (c) a base cobre uma classe CATMAT,
                   logo a taxa não representa o perfil geral de compras do ente.
    """
    d = df.assign(_disp=df["modalidade"].eq("6"))
    return (d.groupby(["nomeUasg", "estado", "esferaDesc"], observed=True)
            .agg(n_itens=("_disp", "size"), n_dispensas=("_disp", "sum"),
                 valor_total=("valorTotalItem", "sum"),
                 valor_dispensa=("valorTotalItem", lambda s: s[d.loc[s.index, "_disp"]].sum()))
            .assign(TCD_itens_pct=lambda x: 100 * x["n_dispensas"] / x["n_itens"],
                    TCD_valor_pct=lambda x: 100 * x["valor_dispensa"] / x["valor_total"])
            .query(f"n_itens >= {n_min}")
            .sort_values("TCD_itens_pct", ascending=False)
            .round(2))


# ==========================================================================
# IND-04 — Concentração de fornecedores (HHI)
# ==========================================================================


def ind04_hhi(df: pd.DataFrame, por=("codigoItemCatalogo", "descricaoItem", "anoCompra")) -> pd.DataFrame:
    """Índice de Herfindahl-Hirschman da participação em valor por grupo econômico.

    Nome         : HHI de Fornecimento
    Objetivo     : medir dependência do poder público em relação a poucos
                   fornecedores para um mesmo medicamento. Concentração alta
                   eleva risco de desabastecimento e reduz pressão
                   competitiva sobre o preço.
    Fórmula      : HHI = Σ s_j² x 10.000, com s_j = participação da raiz de
                   CNPJ j no valor total do item no período.
                   Reportado com CR1 e CR4 (participação do maior e dos
                   quatro maiores).
    Variáveis    : niFornecedor (raiz), valorTotalItem, codigoItemCatalogo, dataCompra
    Granularidade: item x período; também calculável por item x UF
    Periodicidade: anual (o HHI trimestral fica instável com poucos contratos)
    Limitações   : (a) mede concentração das compras observadas, não do
                   mercado — participantes derrotados na licitação não
                   aparecem na base; (b) a raiz de CNPJ agrupa filiais mas
                   não identifica grupos econômicos com CNPJs de raízes
                   distintas (exigiria base de controle societário); (c)
                   distribuidoras e fabricantes são tratados no mesmo plano,
                   embora a concentração relevante para desabastecimento
                   esteja na produção.
    """
    def _calc(g):
        s = g.groupby("raizCnpj", observed=True)["valorTotalItem"].sum()
        s = (s / s.sum()).sort_values(ascending=False)
        return pd.Series({
            "n_grupos": len(s), "HHI": float((s ** 2).sum() * 10_000),
            "CR1_pct": float(100 * s.iloc[0]), "CR4_pct": float(100 * s.head(4).sum()),
            "valor_total": float(g["valorTotalItem"].sum()),
        })

    return (df.groupby(list(por), observed=True)[["raizCnpj", "valorTotalItem"]]
            .apply(_calc).reset_index().round(1))


# ==========================================================================
# Cálculo consolidado
# ==========================================================================


def calcular_todos(df_total: pd.DataFrame, dfp: pd.DataFrame, elasticidade: float) -> dict:
    d_ipr = ind01_indice_preco_relativo(dfp)
    d_ipae = ind02_indice_ajustado_escala(dfp, elasticidade)
    return {
        "IND01_item": d_ipr,
        "IND01_por_ente": ind01_agregado(d_ipr),
        "IND01_por_uf": ind01_agregado(d_ipr, por=("estado",), n_min=20),
        "IND02_item": d_ipae,
        "IND02_por_ente": (d_ipae.groupby(["nomeUasg", "estado"], observed=True)
                           .agg(n=("IPAE", "size"), IPAE_mediano=("IPAE", "median"),
                                excesso_ajustado=("excesso_ajustado_R$", "sum"))
                           .query("n >= 5").sort_values("IPAE_mediano", ascending=False).round(3)),
        "IND03": ind03_taxa_dispensa(df_total),
        "IND04": ind04_hhi(df_total),
    }
